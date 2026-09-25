from fastapi import FastAPI, File, UploadFile, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import onnxruntime as ort
import numpy as np
from PIL import Image
import io
import os
import sqlite3
import json
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
from pathlib import Path
from pydantic import BaseModel

async def delete_file_later(filepath: str, delay: int = 30):
    await asyncio.sleep(delay)
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except OSError:
        pass

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DETECTIONS_DIR = STATIC_DIR / "detections"

# Ensure static directories exist
DETECTIONS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = str(BASE_DIR / "detections.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS detections (
            id TEXT PRIMARY KEY,
            device_serial TEXT,
            pest_name TEXT,
            confidence REAL,
            all_scores TEXT,
            image_filename TEXT,
            timestamp TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS device_streams (
            device_serial TEXT PRIMARY KEY,
            stream_url TEXT,
            status TEXT,
            last_updated TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS stream_requests (
            device_serial TEXT PRIMARY KEY,
            requested_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Initialize DB on import
init_db()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static folder so images can be downloaded/served
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Load model once when server starts
session = ort.InferenceSession(str(BASE_DIR / "rice_pest_model.onnx"))

CLASS_NAMES = {
    0: "Army Worm",
    1: "Brown Plant Hopper",
    2: "Golden Apple Snail",
    3: "Rice Black Bug",
    4: "Rice Bugs",
    5: "Rice Leaf Caterpillar",
    6: "Rice Leaf Hopper",
    7: "Rice Leaf Roller",
    8: "Rice Stem Borer"
}

CONFIDENCE_THRESHOLD = 50.0

def preprocess(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.resize((224, 224))
    img = np.array(img).astype(np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406])
    std  = np.array([0.229, 0.224, 0.225])
    img = (img - mean) / std
    img = img.transpose(2, 0, 1)
    img = np.expand_dims(img, axis=0).astype(np.float32)
    return img

@app.get("/")
def root():
    return {"status": "online", "model": "rice_pest_mobilenetv3"}

# ── 1. Manual Scan Upload Endpoint (from Mobile UI) ──
@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    image_bytes = await file.read()
    input_tensor = preprocess(image_bytes)

    inputs = {session.get_inputs()[0].name: input_tensor}
    outputs = session.run(None, inputs)

    scores = outputs[0][0]
    exp_scores = np.exp(scores - np.max(scores))
    probs = exp_scores / exp_scores.sum()

    pred_idx = int(np.argmax(probs))
    confidence = float(probs[pred_idx]) * 100

    pest_name = CLASS_NAMES[pred_idx]
    if confidence < CONFIDENCE_THRESHOLD:
        pest_name = "No Pest Detected"

    all_scores = {
        CLASS_NAMES[i]: round(float(probs[i]) * 100, 2)
        for i in range(len(CLASS_NAMES))
    }

    return {
        "pest": pest_name,
        "confidence": round(confidence, 2),
        "all_scores": all_scores
    }

# ── 2. ESP32 Raw Upload Endpoint ──
@app.post("/predict")
async def predict(request: Request):
    # Read raw binary body bytes
    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty request body")

    device_serial = request.headers.get("X-Device-Serial", "UNKNOWN_DEVICE")

    # Run inference
    input_tensor = preprocess(image_bytes)
    inputs = {session.get_inputs()[0].name: input_tensor}
    outputs = session.run(None, inputs)

    scores = outputs[0][0]
    exp_scores = np.exp(scores - np.max(scores))
    probs = exp_scores / exp_scores.sum()

    pred_idx = int(np.argmax(probs))
    confidence = float(probs[pred_idx]) * 100
    pest_name = CLASS_NAMES[pred_idx]

    # If confidence is below threshold, discard the image and return early
    if confidence < CONFIDENCE_THRESHOLD:
        return {
            "status": "discarded",
            "message": f"Confidence below threshold ({CONFIDENCE_THRESHOLD}%). Image discarded.",
            "pest": pest_name,
            "confidence": round(confidence, 2)
        }

    # Save physical file to static server directory
    timestamp_str = datetime.utcnow().isoformat()
    filename = f"{device_serial}_{uuid.uuid4().hex}.jpg"
    file_path = DETECTIONS_DIR / filename
    with open(file_path, "wb") as f:
        f.write(image_bytes)

    # Save metadata to SQLite
    record_id = str(uuid.uuid4())
    all_scores_json = json.dumps({
        CLASS_NAMES[i]: round(float(probs[i]) * 100, 2)
        for i in range(len(CLASS_NAMES))
    })

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO detections (id, device_serial, pest_name, confidence, all_scores, image_filename, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (record_id, device_serial, pest_name, round(confidence, 2), all_scores_json, filename, timestamp_str))
    conn.commit()

    # Keep only latest 50 records per device to prevent storage exhaustion
    c.execute('SELECT image_filename FROM detections WHERE device_serial = ? ORDER BY timestamp DESC LIMIT -1 OFFSET 50', (device_serial,))
    old_files = c.fetchall()
    for (old_file,) in old_files:
        try:
            os.remove(str(DETECTIONS_DIR / old_file))
        except OSError:
            pass
    c.execute('DELETE FROM detections WHERE id IN (SELECT id FROM detections WHERE device_serial = ? ORDER BY timestamp DESC LIMIT -1 OFFSET 50)', (device_serial,))
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "id": record_id,
        "pest": pest_name,
        "confidence": round(confidence, 2)
    }

# ── 3. Mobile Sync Endpoint ──
@app.get("/detections/{serial}")
async def get_detections(serial: str, background_tasks: BackgroundTasks):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT id, device_serial, pest_name, confidence, all_scores, image_filename, timestamp 
        FROM detections 
        WHERE device_serial = ? 
        ORDER BY timestamp DESC
    ''', (serial,))
    rows = c.fetchall()

    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "device_serial": row["device_serial"],
            "pest_name": row["pest_name"],
            "confidence": row["confidence"],
            "all_scores": json.loads(row["all_scores"]),
            "timestamp": row["timestamp"],
            "image_url": f"/static/detections/{row['image_filename']}"
        })
        
        # Schedule physical file deletion to allow the client to download the image first
        filename = row["image_filename"]
        if filename:
            file_path = str(DETECTIONS_DIR / filename)
            background_tasks.add_task(delete_file_later, file_path, 30)

    # Delete database records immediately so they won't be sent again
    if len(rows) > 0:
        c.execute('DELETE FROM detections WHERE device_serial = ?', (serial,))
        conn.commit()

    conn.close()
    return results

# ── 4. Device Live Stream Registration Endpoints ──
class StreamUrlPayload(BaseModel):
    stream_url: Optional[str] = None
    status: Optional[str] = "online"
    timestamp: Optional[str] = None

@app.post("/devices/{serial}/stream-url")
async def register_stream_url(serial: str, payload: StreamUrlPayload):
    now = payload.timestamp or datetime.now(timezone.utc).isoformat()
    status = payload.status or "online"

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO device_streams (device_serial, stream_url, status, last_updated)
        VALUES (?, ?, ?, ?)
    ''', (serial, payload.stream_url, status, now))
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "device_serial": serial,
        "stream_url": payload.stream_url,
        "last_updated": now
    }

@app.get("/devices/{serial}/stream-url")
async def get_stream_url(serial: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT device_serial, stream_url, status, last_updated
        FROM device_streams
        WHERE device_serial = ?
    ''', (serial,))
    row = c.fetchone()
    conn.close()

    if not row:
        return {
            "device_serial": serial,
            "stream_url": None,
            "status": "offline",
            "last_updated": None
        }

    status = row["status"] or "online"
    if row["last_updated"]:
        try:
            updated_str = row["last_updated"].replace("Z", "+00:00")
            updated_dt = datetime.fromisoformat(updated_str)
            if updated_dt.tzinfo is None:
                updated_dt = updated_dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - updated_dt > timedelta(minutes=10):
                status = "offline"
        except Exception:
            pass

    return {
        "device_serial": row["device_serial"],
        "stream_url": row["stream_url"],
        "status": status,
        "last_updated": row["last_updated"]
    }

# ── 5. On-Demand Stream Request Endpoints ──
@app.post("/devices/{serial}/request-stream")
async def request_stream(serial: str):
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO stream_requests (device_serial, requested_at)
        VALUES (?, ?)
    ''', (serial, now))
    conn.commit()
    conn.close()
    return {"status": "requested"}

@app.get("/devices/{serial}/request-stream")
async def check_stream_request(serial: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT device_serial, requested_at
        FROM stream_requests
        WHERE device_serial = ?
    ''', (serial,))
    row = c.fetchone()

    if not row or not row["requested_at"]:
        conn.close()
        return {"requested": False}

    requested = True
    try:
        req_str = row["requested_at"].replace("Z", "+00:00")
        req_dt = datetime.fromisoformat(req_str)
        if req_dt.tzinfo is None:
            req_dt = req_dt.replace(tzinfo=timezone.utc)
        # Auto-expire requests older than 2 minutes (120 seconds)
        if datetime.now(timezone.utc) - req_dt > timedelta(minutes=2):
            c.execute('DELETE FROM stream_requests WHERE device_serial = ?', (serial,))
            conn.commit()
            requested = False
    except Exception:
        pass

    conn.close()
    return {"requested": requested}

@app.delete("/devices/{serial}/request-stream")
async def clear_stream_request(serial: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM stream_requests WHERE device_serial = ?', (serial,))
    conn.commit()
    conn.close()
    return {"status": "cleared"}