import datetime
import asyncio
import logging
import ffmpeg
import threading
import multiprocessing
import requests
import os
from contextlib import contextmanager
from multiprocessing import Process
from datetime import timedelta, datetime
from functools import cache
from flask import Flask, jsonify, request
from .db import SessionLocal, engine, Base
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import joinedload
from tenacity import retry, stop_after_attempt, wait_fixed
from .models import MsCCTV
from .models import MsROI

# Configuration
CACHE_EXPIRATION = timedelta(minutes=6)
STREAM_CHECK_TIMEOUT = 15
MAX_CONCURRENT_CHECKS = 2  # Adjust based on CPU cores
FFMPEG_THREADS_PER_PROCESS = 2  # Recommended: 1-2 threads per FFmpeg process

cache = {}
cache_lock = threading.Lock()
stream_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)

# Logging setup
def setup_logging():
    log_dir = "stream_logs"
    os.makedirs(log_dir, exist_ok=True)
    log_filename = os.path.join(log_dir, f"stream_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )
    logging.info(f"Logging initialized to {log_filename}")

setup_logging()

# Database context manager
@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Optimized stream testing
async def test_stream_async(stream_url):
    process = None
    try:
        logging.debug(f"Testing stream: {stream_url}")
        
        ffmpeg_command = [
            "ffmpeg",
            "-loglevel", "error",
            "-threads", str(FFMPEG_THREADS_PER_PROCESS),
            "-i", stream_url,
            "-t", "5",
            "-cpu-used", "2",
            "-frames:v", "15",
            "-f", "null", "-"
        ]

        process = await asyncio.create_subprocess_exec(
            *ffmpeg_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            return_code = await asyncio.wait_for(process.wait(), timeout=STREAM_CHECK_TIMEOUT)
            if return_code == 0:
                return "online"
            return "offline"
        except asyncio.TimeoutError:
            logging.warning(f"Timeout checking {stream_url}")
            raise

    except Exception as e:
        logging.error(f"Error checking stream {stream_url}: {str(e)}")
        return "offline"
    finally:
        if process and process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=2)
            except:
                pass
            
async def fetch_cctv_status(cctvs):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)
    
    async def process_cctv(cctv):
        async with semaphore:
            try:
                if not cctv.stream_url:
                    return (cctv, "invalid")
                    
                with cache_lock:
                    cached = cache.get(cctv.stream_url)
                    if cached and datetime.now() < cached["expires"]:
                        return (cctv, cached["status"])
                
                status = await test_stream_async(cctv.stream_url)
                
                with cache_lock:
                    cache[cctv.stream_url] = {
                        "status": status,
                        "expires": datetime.now() + CACHE_EXPIRATION
                    }
                
                return (cctv, status)
            except Exception as e:
                logging.error(f"Error processing {cctv.stream_url}: {e}")
                return (cctv, "error")
    
    return await asyncio.gather(*[process_cctv(c) for c in cctvs])

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def update_cctv_status_cache():
    while True:
        start_time = datetime.now()
        update_count = 0
        try:
            with get_db() as db:
                # Get all CCTV data with relationships
                cctvs = db.query(MsCCTV).options(
                    joinedload(MsCCTV.rois)
                ).all()
                
                # Process in batches with progress tracking
                batch_size = min(MAX_CONCURRENT_CHECKS * 2, 20)  # Cap at 20
                total_batches = (len(cctvs) + batch_size - 1) // batch_size
                
                for batch_num, i in enumerate(range(0, len(cctvs), batch_size)):
                    batch = cctvs[i:i + batch_size]
                    
                    # Process batch
                    batch_statuses = await fetch_cctv_status(batch)
                    
                    # Update cache
                    with cache_lock:
                        for cctv, status in batch_statuses:
                            cache[cctv.stream_url] = {
                                "status": status,
                                "expires": datetime.now() + CACHE_EXPIRATION,
                                "cctv_data": {
                                    "id": str(cctv.id),
                                    "nama_lokasi": cctv.nama_lokasi,
                                    "nama_cctv": cctv.nama_cctv,
                                    "stream_url": cctv.stream_url,
                                    "nama_pengelola": cctv.nama_pengelola,
                                    "protocol": cctv.protocol,
                                    "latitude": float(cctv.latitude) if cctv.latitude else None,
                                    "longitude": float(cctv.longitude) if cctv.longitude else None,
                                    "source": cctv.source,
                                    "tag_kategori": cctv.tag_kategori,
                                    "matra": cctv.matra,
                                    "nama_kabupaten_kota": cctv.nama_kabupaten_kota,
                                    "nama_provinsi": cctv.nama_provinsi,
                                    "status": cctv.status,  # Original status from DB
                                    "created_at": cctv.created_at.isoformat(),
                                    "updated_at": cctv.updated_at.isoformat(),
                                    "rois": [{
                                        "id": str(roi.id),
                                        "label": roi.label,
                                        "coordinates": roi.roi,
                                        "created_at": roi.created_at.isoformat(),
                                        "updated_at": roi.updated_at.isoformat()
                                    } for roi in cctv.rois]
                                }
                            }
                            update_count += 1
                    
                    # Progress logging
                    if batch_num % 5 == 0:  # Log every 5 batches
                        logging.info(
                            f"Batch {batch_num+1}/{total_batches} processed, "
                            f"{update_count}/{len(cctvs)} items updated"
                        )
                    
                    # Throttle between batches
                    await asyncio.sleep(0.5)  # Reduced delay
                
                logging.info(
                    f"Cache update completed. {update_count} items updated in "
                    f"{(datetime.now() - start_time).total_seconds():.2f} seconds"
                )
                
        except OperationalError as e:
            logging.error(f"Database error during cache update: {str(e)}")
            await asyncio.sleep(60)  # Longer wait for DB errors
        except Exception as e:
            logging.error(f"Unexpected error during cache update: {str(e)}", exc_info=True)
            await asyncio.sleep(30)
        finally:
            # Ensure we don't update too frequently even if errors occur
            elapsed = (datetime.now() - start_time).total_seconds()
            remaining_wait = max(300 - elapsed, 10)  # At least 10 seconds
            await asyncio.sleep(remaining_wait)

def start_background_task():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(update_cctv_status_cache()) 
    except Exception as e:
        logging.critical(f"Critical error in background task: {e}", exc_info=True)
    finally:
        loop.close()

def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    # Initialize the database
    with app.app_context():
        Base.metadata.create_all(bind=engine)
        
    bg_thread = threading.Thread(
        target = start_background_task,
        daemon = True,
        name = "CacheCCTVStatusThread"
    )
    
    bg_thread.start()
    
    @app.route("/hello")
    def index():
        return "Hello, World!"
    
    @app.route("/api/cctv")
    def get_all_cctv():
        session = SessionLocal()
        try:
            results = session.query(MsCCTV).all()
            return jsonify([row.to_dict() for row in results])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            session.close()
            
    def serialize_cctv(cctv, status=None):
        """Helper to ensure consistent serialization across both endpoints"""
        base_data = {
            "id": str(cctv.id),
            "nama_lokasi": cctv.nama_lokasi,
            "nama_cctv": cctv.nama_cctv,
            "stream_url": cctv.stream_url,
            "nama_pengelola": cctv.nama_pengelola,
            "protocol": cctv.protocol,
            "latitude": float(cctv.latitude) if cctv.latitude else None,
            "longitude": float(cctv.longitude) if cctv.longitude else None,
            "source": cctv.source,
            "tag_kategori": cctv.tag_kategori,
            "matra": cctv.matra,
            "nama_kabupaten_kota": cctv.nama_kabupaten_kota,
            "nama_provinsi": cctv.nama_provinsi,
            "status": status if status is not None else cctv.status,
            "created_at": cctv.created_at.isoformat() if cctv.created_at else None,
            "updated_at": cctv.updated_at.isoformat() if cctv.updated_at else None,
            "rois": [roi.to_dict() for roi in getattr(cctv, 'rois', [])]
        }
        return {cctv.nama_cctv: base_data}
            
    @app.route("/api/cctv/status/query", methods=["GET"])
    async def get_cctv_status_query():
        status_filter = request.args.get("status")
        limit = request.args.get("limit", type=int)
        
        try:
            with get_db() as session:
                # Get full objects including relationships
                query = session.query(MsCCTV).options(joinedload(MsCCTV.rois))
                
                if status_filter:
                    query = query.filter(MsCCTV.status.ilike(f"%{status_filter}%"))
                
                if limit:
                    query = query.limit(limit)
                
                cctvs = query.all()
                cctv_statuses = await fetch_cctv_status(cctvs)
                
                results = {}
                for cctv, status in cctv_statuses:
                    results.update(serialize_cctv(cctv, status))
                
                return jsonify(results)
                
        except Exception as e:
            logging.error(f"Query error: {str(e)}", exc_info=True)
            return jsonify({"error": "Internal server error"}), 500
    
    #cache
    @app.route("/api/cctv/status", methods=["GET"])
    async def get_cctv_status():
        status_filter = request.args.get("status")
        limit = request.args.get("limit", type=int)
        
        try:
            with cache_lock:
                # Directly use the cached data structure
                filtered = {
                    url: {
                        **data["cctv_data"],
                        "current_status": data["status"]  # Add current status
                    }
                    for url, data in cache.items()
                    if "cctv_data" in data and (
                        not status_filter or 
                        data["status"].lower() == status_filter.lower()
                    )
                }
                
                if limit and limit > 0:
                    filtered = dict(list(filtered.items())[:limit])
                
                return jsonify(filtered)
                
        except Exception as e:
            logging.error(f"Cache error: {str(e)}", exc_info=True)
            return jsonify({"error": "Internal server error"}), 500
      
    @app.route("/api/cctv/roi/<id_cctv>", methods=["POST"])
    def update_cctv_roi(id_cctv):
        session = SessionLocal()
        try:
            cctv = session.query(MsCCTV).filter(MsCCTV.id == id_cctv).first()
            if not cctv:
                return jsonify({"error": "CCTV not found"}), 404
            data = request.json
            if "roi" not in data or "label" not in data:
                return jsonify({"error": "ROI and Label data are required"}), 400
            
            # Update the CCTV ROI
            cctv.ROI = data["roi"]
            
            # Add new ROI data to MsROI
            new_roi = MsROI(
                id_cctv=id_cctv,
                nama_cctv=cctv.nama_cctv,
                label=data["label"],
                roi=data["roi"],
                created_at=datetime.datetime.now(),
                updated_at=datetime.datetime.now()
            )
            session.add(new_roi)
            
            session.commit()
            return jsonify(cctv.to_dict())
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            session.close()

    @app.route("/api/cctv/roi/<id_roi>", methods=["PUT"])
    def edit_cctv_roi(id_roi):
        session = SessionLocal()
        try:
            roi = session.query(MsROI).filter(MsROI.id == id_roi).first()
            if not roi:
                return jsonify({"error": "ROI not found"}), 404
            data = request.json
            if "roi" not in data or "label" not in data:
                return jsonify({"error": "ROI and Label data are required"}), 400
            
            # Update the ROI data
            roi.ROI = data["roi"]
            roi.Label = data["label"]
            roi.Updated_at = datetime.datetime.now()
            
            session.commit()
            return jsonify(roi.to_dict())
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            session.close()

    @app.route("/api/cctv/roi/<id_roi>", methods=["DELETE"])
    def delete_cctv_roi(id_roi):
        session = SessionLocal()
        try:
            roi = session.query(MsROI).filter(MsROI.id == id_roi).first()
            if not roi:
                return jsonify({"error": "ROI not found"}), 404
            
            session.delete(roi)
            session.commit()
            return jsonify({"message": "ROI deleted successfully"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            session.close()
        
    return app