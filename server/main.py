from fastapi import FastAPI, File, UploadFile, Request, HTTPException
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
from datetime import datetime
from pathlib import Path

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
    1: "Asiatic Rice Borer",
    2: "Brown Plant Hopper",
    3: "Paddy Stem Maggot",
    4: "Rice Gall Midge",
    5: "Rice Leaf Caterpillar",
    6: "Rice Leaf Hopper",
    7: "Rice Leaf Roller",
    8: "Rice Shell Pest",
    9: "Rice Water Weevil",
    10: "Thrips",
    11: "White Backed Plant Hopper",
    12: "Yellow Rice Borer"
}

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

    return {
        "pest": CLASS_NAMES[pred_idx],
        "confidence": round(confidence, 2),
        "all_scores": {
            CLASS_NAMES[i]: round(float(probs[i]) * 100, 2)
            for i in range(len(CLASS_NAMES))
        }
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
def get_detections(serial: str):
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
    conn.close()

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
    return results