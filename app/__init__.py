import datetime
import asyncio
import logging
import ffmpeg
import threading
import multiprocessing
import requests
from multiprocessing import Process
from datetime import timedelta
from functools import cache
from flask import Flask, jsonify, request
from .db import SessionLocal, engine, Base
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import joinedload
from tenacity import retry, stop_after_attempt, wait_fixed
from .models import MsCCTV
from .models import MsROI

cache = {}
cache_lock = threading.Lock()
CACHE_EXPIRATION = timedelta(minutes=6)

async def test_stream_async(stream_url):
    try:
        process = None
        
        # Run FFmpeg asynchronously to probe the stream
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", stream_url, "-t", "5", "-f", "null", "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await asyncio.wait_for(process.wait(), timeout=5)

        if process.returncode == 0:
            return "online"
        else:
            stderr = await process.stderr.read()
            logging.error(f"FFmpeg error for stream {stream_url}: {stderr.decode()}")
            return "offline"

    except asyncio.TimeoutError:
        logging.error(f"FFmpeg timeout for stream {stream_url}")
        if process and process.returncode is None:
            process.terminate()  # Kill the process if it's still running
        return "offline"

    except Exception as e:
        logging.error(f"Unexpected error for stream {stream_url}: {str(e)}")
        return "offline"

    finally:
        if process and process.returncode is None:
            process.terminate()  # Ensure FFmpeg is terminated
            await process.wait()  # Wait for termination

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def update_cctv_status_cache():
    while True:
        session = SessionLocal()
        try: 
            cctvs = session.query(MsCCTV).options(joinedload(MsCCTV.rois)).all()
            cctv_status = await fetch_cctv_status(cctvs)
            cache.clear()
            # Update the cache with new statuses
            for cctv, status in cctv_status:
                cache[cctv.stream_url] = {
                    "status": status,
                    "expires": datetime.datetime.now() + CACHE_EXPIRATION,
                    "cctv_data": {
                        "id": str(cctv.id),
                        "nama_lokasi": cctv.nama_lokasi,
                        "nama_cctv": cctv.nama_cctv,
                        "stream_url": cctv.stream_url,
                        "nama_pengelola": cctv.nama_pengelola,
                        "protocol": cctv.protocol,
                        "latitude": cctv.latitude,
                        "longitude": cctv.longitude,
                        "source": cctv.source,
                        "tag_kategori": cctv.tag_kategori,
                        "matra": cctv.matra,
                        "nama_kabupaten_kota": cctv.nama_kabupaten_kota,
                        "nama_provinsi": cctv.nama_provinsi,
                        "status": cctv.status,
                        "created_at": cctv.created_at.strftime("%a, %d %b %Y %H:%M:%S GMT"),
                        "updated_at": cctv.updated_at.strftime("%a, %d %b %Y %H:%M:%S GMT"),
                        "rois": [roi.to_dict() for roi in cctv.rois]
                    }
                }
            logging.info("CCTV status cache updated")
        except Exception as e:
            logging.error(f"Error updating CCTV status cache: {str(e)}")
        finally:
            session.close()
        await asyncio.sleep(300)  # Sleep for 5 minutes before the next update

async def fetch_cctv_status(cctvs):
    tasks = []
    for cctv in cctvs:
        if not cctv.stream_url:
            continue
        
        cache_key = cctv.stream_url
        with cache_lock:
            cached_status = cache.get(cache_key)
        
        if cached_status and datetime.datetime.now() < cached_status["expires"]:
            status = cached_status["status"]
        else:
            tasks.append((cctv, asyncio.create_task(test_stream_async(cctv.stream_url))))
            
    results = []
    for cctv, task in tasks:
        status = await task
        with cache_lock:
            cache[cctv.stream_url] = {"status": status, "expires": datetime.datetime.now() + CACHE_EXPIRATION}
        results.append((cctv, status))  

    for cctv in cctvs:
        with cache_lock:
            if cctv.stream_url in cache and not any(task[0] == cctv for task in tasks):
                results.append((cctv, cache[cctv.stream_url]["status"]))

    return results

def start_background_task():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(update_cctv_status_cache()) 

def create_app():
    app = Flask(__name__)
    app.config.from_object("app.config.Config")

    # Initialize the database
    with app.app_context():
        Base.metadata.create_all(bind=engine)
        
    # Start the background task in a separate thread
    threading.Thread(target=start_background_task, daemon=True).start()
    
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
            
    @app.route("/api/cctv/status/query", methods=["GET"])
    async def get_cctv_status_query():
        status_filter = request.args.get("status")
        limit = request.args.get("limit", type=int)
        logging.info(f"Status filter: {status_filter}")
        session = SessionLocal()
        try:
            cctvs = session.query(MsCCTV).options(joinedload(MsCCTV.rois)).all()
            cctv_statuses = await fetch_cctv_status(cctvs)
            
            results = [
                {
                    cctv.nama_cctv : 
                    {
                        "id": str(cctv.id),
                        "nama_lokasi": cctv.nama_lokasi,
                        "stream_url": cctv.stream_url,
                        "nama_pengelola": cctv.nama_pengelola,
                        "protocol": cctv.protocol,
                        "latitude": cctv.latitude,
                        "longitude": cctv.longitude,
                        "source": cctv.source,
                        "tag_kategori": cctv.tag_kategori,
                        "matra": cctv.matra,
                        "nama_kabupaten_kota": cctv.nama_kabupaten_kota,
                        "nama_provinsi": cctv.nama_provinsi,
                        "status": status,
                        "rois" : [roi.to_dict() for roi in cctv.rois]
                    }
                }
                
                for cctv, status in cctv_statuses
                if not status_filter or status.lower() == status_filter.lower()
            ]
            
            if limit and limit > 0: 
                results = results[:limit]
            
            logging.info(f"Filtered results: {results}")
            return jsonify(results)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            session.close()
    
    #cache
    @app.route("/api/cctv/status", methods=["GET"])
    async def get_cctv_status():
        status_filter = request.args.get("status")
        limit = request.args.get("limit", type=int)
        logging.info(f"Status filter: {status_filter}, Limit: {limit}")
        
        try: 
            results = [
                {
                    entry["cctv_data"]["nama_cctv"]: {
                        "id": entry["cctv_data"]["id"],
                        "nama_lokasi": entry["cctv_data"]["nama_lokasi"],
                        "stream_url": entry["cctv_data"]["stream_url"],
                        "nama_pengelola": entry["cctv_data"]["nama_pengelola"],
                        "protocol": entry["cctv_data"]["protocol"],
                        "latitude": entry["cctv_data"]["latitude"],
                        "longitude": entry["cctv_data"]["longitude"],
                        "source": entry["cctv_data"]["source"],
                        "tag_kategori": entry["cctv_data"]["tag_kategori"],
                        "matra": entry["cctv_data"]["matra"],
                        "nama_kabupaten_kota": entry["cctv_data"]["nama_kabupaten_kota"],
                        "nama_provinsi": entry["cctv_data"]["nama_provinsi"],
                        "status": entry["status"],
                        "rois": entry["cctv_data"]["rois"] 
                    }
                }
                for entry in cache.values()
                if "cctv_data" in entry and (not status_filter or entry["status"].lower() == status_filter.lower())
            ]
            
            if limit and limit > 0:
                results = results[:limit]
                    
            logging.info(f"Filtered results: {results}")
            return jsonify(results)
        except Exception as e: 
            logging.error(f"Error fetching CCTV status: {str(e)}")
            return jsonify({"error": str(e)}), 500
      
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