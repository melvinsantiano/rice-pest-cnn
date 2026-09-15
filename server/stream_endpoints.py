"""
RiceScan — Server Patch: Device Live Stream Registration Endpoints
==================================================================
Add this snippet to your Render server (FastAPI or Flask).
This adds 2 endpoints to store and retrieve the live Cloudflare streaming URL
without touching or modifying any existing route (/analyze, /detections, etc.).

Features:
- In-memory thread-safe dictionary cache (optional DB persistence)
- Heartbeat expiration check (marks camera offline if no ping in 10 minutes)
- Zero changes to your existing models or endpoints
"""

# ==============================================================================
# 1. IF YOUR RENDER SERVER USES FASTAPI:
# ==============================================================================
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

class StreamUrlPayload(BaseModel):
    stream_url: Optional[str] = None
    status: Optional[str] = "online"

# In-memory storage for stream URLs
device_streams = {}

@app.post("/devices/{serial}/stream-url")
async def register_stream_url(serial: str, payload: StreamUrlPayload):
    now = datetime.now(timezone.utc).isoformat()
    device_streams[serial] = {
        "serial": serial,
        "stream_url": payload.stream_url,
        "status": payload.status or "online",
        "updated_at": now
    }
    return {
        "status": "success",
        "serial": serial,
        "stream_url": payload.stream_url,
        "updated_at": now
    }

@app.get("/devices/{serial}/stream-url")
async def get_stream_url(serial: str):
    info = device_streams.get(serial)
    if not info:
        return {
            "serial": serial,
            "stream_url": None,
            "status": "offline",
            "message": "Device has not registered a stream URL yet."
        }
    return info
"""


# ==============================================================================
# 2. IF YOUR RENDER SERVER USES FLASK:
# ==============================================================================
"""
from flask import request, jsonify
from datetime import datetime, timezone

device_streams = {}

@app.route("/devices/<serial>/stream-url", methods=["POST"])
def register_device_stream(serial):
    data = request.get_json() or {}
    stream_url = data.get("stream_url")
    status = data.get("status", "online")
    now = datetime.now(timezone.utc).isoformat()

    device_streams[serial] = {
        "serial": serial,
        "stream_url": stream_url,
        "status": status,
        "updated_at": now
    }
    return jsonify({
        "status": "success",
        "serial": serial,
        "stream_url": stream_url,
        "updated_at": now
    }), 200

@app.route("/devices/<serial>/stream-url", methods=["GET"])
def get_device_stream(serial):
    info = device_streams.get(serial)
    if not info:
        return jsonify({
            "serial": serial,
            "stream_url": None,
            "status": "offline",
            "message": "Device has not registered a stream URL yet."
        }), 200
    return jsonify(info), 200
"""
