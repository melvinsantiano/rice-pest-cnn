# Server & Mobile App Integration Guide (On-Demand Monitor System)

This document explains what needs to be updated on the central Render Server API and the Mobile App to support the on-demand RiceScan live monitor system.

## How It Works (On-Demand Flow)

```
User taps "Monitor"
        │
        ▼
 App: POST /devices/<serial>/request-stream   ← "I want to watch"
        │
        ▼
 App: shows loading spinner
 App: polls GET /devices/<serial>/stream-url every 3s
        │                                          ┌──────────────────────────┐
        │       meanwhile, on the Pi...            │ Pi polls every 5s:       │
        │                                          │ GET /request-stream      │
        │                                          │ Sees requested=true      │
        │                                          │ Starts Cloudflare tunnel │
        │                                          │ POST /stream-url (URL)   │
        │                                          └──────────────────────────┘
        ▼
 App: GET /stream-url → gets the live URL
 App: loads <url>/stream.mjpg → stream is live!
        │
        ▼
 User leaves Monitor screen
 No viewers for 30 seconds → Pi auto-stops tunnel
```

> **Key benefit**: The Cloudflare tunnel and camera stream only run when someone is actually watching. No wasted bandwidth, no wasted resources.

---

## 1. Central Server (Render.com)

### A. Existing Endpoints (no changes needed)

#### `POST /devices/<serial>/stream-url`
- **Called by**: Raspberry Pi (when tunnel starts)
- **Request Body**:
  ```json
  {
    "stream_url": "https://random-word.trycloudflare.com",
    "status": "online",
    "timestamp": "2026-09-15T12:00:00Z"
  }
  ```
- **Action**: Store `stream_url` and `status` for the device.

#### `GET /devices/<serial>/stream-url`
- **Called by**: Mobile App (to fetch the tunnel URL)
- **Response**:
  ```json
  {
    "device_serial": "100000007cc91af4",
    "stream_url": "https://random-word.trycloudflare.com",
    "status": "online",
    "last_updated": "2026-09-15T12:00:00Z"
  }
  ```

### B. NEW Endpoints Required

#### `POST /devices/<serial>/request-stream`
- **Called by**: Mobile App (when user taps "Monitor")
- **Action**: Set a `monitor_requested = true` flag for this device.
- **Request Body**: None required (empty POST is fine).
- **Response**: `200 OK`
- **Example server logic (FastAPI)**:
  ```python
  monitor_requests = {}  # device_serial -> timestamp

  @app.post("/devices/{serial}/request-stream")
  def request_stream(serial: str):
      monitor_requests[serial] = datetime.utcnow().isoformat()
      return {"status": "requested"}
  ```

#### `GET /devices/<serial>/request-stream`
- **Called by**: Raspberry Pi (polls every 5 seconds)
- **Action**: Check if a monitor session has been requested for this device.
- **Response**:
  ```json
  { "requested": true }
  ```
  or
  ```json
  { "requested": false }
  ```
- **Example server logic (FastAPI)**:
  ```python
  @app.get("/devices/{serial}/request-stream")
  def check_stream_request(serial: str):
      requested = serial in monitor_requests
      return {"requested": requested}
  ```

#### `DELETE /devices/<serial>/request-stream`
- **Called by**: Raspberry Pi (to acknowledge/clear the request after starting the tunnel)
- **Action**: Remove the `monitor_requested` flag so it doesn't re-trigger.
- **Response**: `200 OK`
- **Example server logic (FastAPI)**:
  ```python
  @app.delete("/devices/{serial}/request-stream")
  def clear_stream_request(serial: str):
      monitor_requests.pop(serial, None)
      return {"status": "cleared"}
  ```

> **Tip**: You should auto-expire requests older than 2 minutes, so stale requests from a user who closed the app don't trigger the Pi unnecessarily.

---

## 2. Mobile App (Flutter / React Native / Android / iOS)

### A. When User Taps "Monitor"

1. **Request the stream**: `POST /devices/<serial>/request-stream`
2. **Show a loading screen** with a message like _"Connecting to field camera..."_
3. **Poll for the stream URL**: `GET /devices/<serial>/stream-url` every **3 seconds**
4. **Once `status` is `"online"` and `stream_url` is not empty**, load the stream
5. **Timeout**: If no URL after **45 seconds**, show an error: _"Device may be offline. Check that the RiceScan node has power and internet."_

### B. Display the Video Feed

**Option 1: Native Image Stream (Recommended)**
```dart
// Flutter
Image.network("${streamUrl}/stream.mjpg")
```

**Option 2: WebView**
```dart
WebView(initialUrl: streamUrl)
```

### C. When User Leaves Monitor Screen

- Stop polling / close the stream connection.
- No explicit "stop" call needed — the Pi auto-stops after 30 seconds of no viewers.

### D. Handle Errors

| Scenario | What to show |
|----------|-------------|
| `status: "offline"` | "Camera is offline" |
| Timeout (45s) | "Could not reach field camera. Check power & internet." |
| Stream drops mid-view | "Reconnecting..." → re-poll `GET /stream-url` |

---

## 3. Production Considerations

- **Authentication**: The `/stream.mjpg` endpoint is currently public. For production, add token validation in `monitor.py` and pass the token from the app (e.g. `?token=SECRET`).
- **Data Costs**: MJPEG over cellular uses significant bandwidth. Warn users not to leave the monitor open for extended periods.
- **Auto-stop**: The Pi automatically tears down the tunnel after 30 seconds with no active viewers, so bandwidth is only used when someone is watching.

## 4. Hardware Node Production Setup (Cloudflare Named Tunnels)

By default, the Raspberry Pi uses Cloudflare **Quick Tunnels** (`trycloudflare.com`). These are rate-limited and not suited for continuous production use.

For production, configure a **Named Tunnel**:
1. SSH into the Pi
2. `cloudflared tunnel login`
3. `cloudflared tunnel create ricescan-node1`
4. `cloudflared tunnel route dns ricescan-node1 stream-node1.yourdomain.com`
5. Update `config.py` with the fixed URL

---

## 5. Deploying the Node to Production (Raspberry Pi)

The client code comes with a production-grade WSGI server (`Waitress`) for the monitor stream and a `systemd` service for background execution. 

To deploy the node into production mode on the Raspberry Pi:

1. **Run the Setup Script**
   This installs all dependencies (`cloudflared`, `waitress`, etc.), configures DNS, and registers the background service:
   ```bash
   cd /home/ricescan/ricescan-client
   sudo bash setup.sh
   ```

2. **Manage the Background Service**
   The `ricescan` service will now start automatically on boot and restart if it crashes.
   ```bash
   # View live logs
   sudo journalctl -u ricescan -f
   
   # Stop the service
   sudo systemctl stop ricescan
   
   # Restart the service
   sudo systemctl restart ricescan
   ```
