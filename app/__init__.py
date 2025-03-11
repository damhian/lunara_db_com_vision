import datetime
import asyncio
import logging
import ffmpeg
import threading
import multiprocessing
from multiprocessing import Process
from datetime import timedelta
from functools import cache
from flask import Flask, jsonify, request
from app.db import SessionLocal, engine, Base
from sqlalchemy.exc import OperationalError
from tenacity import retry, stop_after_attempt, wait_fixed
from app.models import MsCCTV
from app.models import MsROI

cache = {}
CACHE_EXPIRATION = timedelta(minutes=6)

async def test_stream_async(stream_url):
    try:
        # Run FFmpeg asynchronously to probe the stream
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", stream_url, "-t", "5", "-f", "null", "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        # Wait for the process to complete (timeout after 5 seconds)
        await asyncio.wait_for(process.wait(), timeout=5)
        
        # Check the return code
        if process.returncode == 0:
            return "Running"
        else:
            # Log the FFmpeg error output
            stderr = await process.stderr.read()
            logging.error(f"FFmpeg error for stream {stream_url}: {stderr.decode()}")
            return "Not running"
    except asyncio.TimeoutError:
        logging.error(f"FFmpeg timeout for stream {stream_url}")
        return "Not running"
    except Exception as e:
        logging.error(f"Unexpected error for stream {stream_url}: {str(e)}")
        return "Not running"

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
async def update_cctv_status_cache():
    while True:
        session = SessionLocal()
        try: 
            cctvs = session.query(MsCCTV).all()
            cctv_status = await fetch_cctv_status(cctvs)
            cache.clear()
            # Update the cache with new statuses
            for cctv, status in cctv_status:
                cache[cctv.Stream_url] = {
                    "status": status,
                    "expires": datetime.datetime.now() + CACHE_EXPIRATION,
                    "cctv_data": {
                        "id": str(cctv.Id),
                        "cctv_name": cctv.CCTV_Name,
                        "ruas_name": cctv.Ruas_Name,
                        "stream_url": cctv.Stream_url,
                        "latitude": cctv.Lat,
                        "longitude": cctv.Long,
                        "bujt": cctv.BUJT,
                        "bujt_name": cctv.BUJT_NAME,
                        "created_at": cctv.Created_at.strftime("%a, %d %b %Y %H:%M:%S GMT"),
                        "updated_at": cctv.Updated_at.strftime("%a, %d %b %Y %H:%M:%S GMT"),
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
        cache_key = cctv.Stream_url
        cached_status = cache.get(cache_key)
        
        if cached_status and datetime.datetime.now() < cached_status["expires"]:
            status = cached_status["status"]
        else:
            tasks.append((cctv, asyncio.create_task(test_stream_async(cctv.Stream_url))))
            
    results = []
    for cctv, task in tasks:
        status = await task
        
        cache[cctv.Stream_url] = {"status": status, "expires": datetime.datetime.now() + CACHE_EXPIRATION}
        results.append((cctv, status))  

    for cctv in cctvs:
        if cctv.Stream_url in cache and not any(task[0] == cctv for task in tasks):
            results.append((cctv, cache[cctv.Stream_url]["status"]))

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
        logging.info(f"Status filter: {status_filter}")
        session = SessionLocal()
        try:
            cctvs = session.query(MsCCTV).all()
            cctv_statuses = await fetch_cctv_status(cctvs)
            results = [
                {
                    cctv.CCTV_Name : 
                    {
                        "id": str(cctv.Id),
                        "ruas_name": cctv.Ruas_Name,
                        "stream_url": cctv.Stream_url,
                        "latitude": cctv.Lat,
                        "longitude": cctv.Long,
                        "bujt": cctv.BUJT,
                        "bujt_name": cctv.BUJT_NAME,
                        "status": status,
                    }
                }
                
                for cctv, status in cctv_statuses
                if not status_filter or status.lower() == status_filter.lower()
            ]
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
        logging.info(f"Status filter: {status_filter}")
        
        try: 
            results = [
                {
                    entry["cctv_data"]["cctv_name"]: {
                        "id": entry["cctv_data"]["id"],
                        "ruas_name": entry["cctv_data"]["ruas_name"],
                        "stream_url": entry["cctv_data"]["stream_url"],
                        "latitude": entry["cctv_data"]["latitude"],
                        "longitude": entry["cctv_data"]["longitude"],
                        "bujt": entry["cctv_data"]["bujt"],
                        "bujt_name": entry["cctv_data"]["bujt_name"],
                        "status": entry["status"],
                    }
                }
                for entry in cache.values()
                if "cctv_data" in entry and (not status_filter or entry["status"].lower() == status_filter.lower())
            ]        
            logging.info(f"Filtered results: {results}")
            return jsonify(results)
        except Exception as e: 
            logging.error(f"Error fetching CCTV status: {str(e)}")
            return jsonify({"error": str(e)}), 500
            
    @app.route("/api/cctv/roi/<cctv_id>", methods=["POST"])
    def update_cctv_roi(cctv_id):
        session = SessionLocal()
        try:
            cctv = session.query(MsCCTV).filter(MsCCTV.Id == cctv_id).first()
            if not cctv:
                return jsonify({"error": "CCTV not found"}), 404
            data = request.json
            if "roi" not in data or "label" not in data:
                return jsonify({"error": "ROI and Label data are required"}), 400
            
            # Update the CCTV ROI
            cctv.ROI = data["roi"]
            
            # Add new ROI data to MsROI
            new_roi = MsROI(
                Id_CCTV=cctv_id,
                CCTV_Name=cctv.CCTV_Name,
                Label=data["label"],
                ROI=data["roi"],
                Created_at=datetime.datetime.now(),
                Updated_at=datetime.datetime.now()
            )
            session.add(new_roi)
            
            session.commit()
            return jsonify(cctv.to_dict())
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            session.close()

    @app.route("/api/cctv/roi/<roi_id>", methods=["PUT"])
    def edit_cctv_roi(roi_id):
        session = SessionLocal()
        try:
            roi = session.query(MsROI).filter(MsROI.Id == roi_id).first()
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

    @app.route("/api/cctv/roi/<roi_id>", methods=["DELETE"])
    def delete_cctv_roi(roi_id):
        session = SessionLocal()
        try:
            roi = session.query(MsROI).filter(MsROI.Id == roi_id).first()
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