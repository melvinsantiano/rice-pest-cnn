# Server & Mobile App Integration Guide (Monitor System)

This document explains what needs to be updated on the central Render Server API and the Mobile App to fully support the combined RiceScan capture and live monitor system.

## 1. Central Server (Render.com)

The Raspberry Pi will now send its live stream URL to the server every 5 minutes when it's online. The server needs a way to store this and serve it to the mobile app.

### A. New API Endpoints Required

You need to add two routes to your Render API server:

#### `POST /devices/<serial>/stream-url`
- **Purpose**: Called by the Raspberry Pi to register its live Cloudflare tunnel URL.
- **Request Body (JSON)**:
  ```json
  {
    "stream_url": "https://random-word.trycloudflare.com",
    "status": "online",
    "timestamp": "2026-09-15T12:00:00Z"
  }
  ```
- **Action**: Store this `stream_url` and `status` in the database for the corresponding device.

#### `GET /devices/<serial>/stream-url`
- **Purpose**: Called by the Mobile App when the user taps "Monitor" to see the live feed.
- **Response (JSON)**:
  ```json
  {
    "device_serial": "RPI4-1234ABCD",
    "stream_url": "https://random-word.trycloudflare.com",
    "status": "online",
    "last_updated": "2026-09-15T12:00:00Z"
  }
  ```

---

## 2. Mobile App (Flutter / React Native / Android / iOS)

When the user navigates to the "Live Monitor" screen for a specific node in the field, the app should perform the following sequence:

### A. Fetch the Stream URL
Call the `GET /devices/<serial>/stream-url` endpoint mentioned above to retrieve the active Cloudflare Tunnel URL.

### B. Display the Video Feed
There are two ways to display the stream in the app:

**Option 1: Native Image Stream (Recommended for custom UIs)**
The MJPEG stream is fundamentally a sequence of JPEG images. You can use an image widget and point it directly to the `.mjpg` path.
- **URL**: `<stream_url>/stream.mjpg`
- Example in Flutter:
  ```dart
  Image.network("https://random-word.trycloudflare.com/stream.mjpg")
  ```

**Option 2: Web View (Quickest implementation)**
The Raspberry Pi serves a formatted HTML dashboard specifically designed for mobile screens. You can embed a WebView pointing to the base URL or `/monitor`.
- **URL**: `<stream_url>/` or `<stream_url>/monitor`

### C. Handle Stream Lag & Disconnects
- Cellular connections in fields can drop. Implement a timeout (e.g., 10 seconds) on the stream connection. 
- If the stream drops, show a "Reconnecting..." UI and try fetching the URL from the server again, as the Pi might have obtained a new Cloudflare URL after a reboot.

---

## 3. Production Considerations
- **Authentication**: Currently, the `/stream.mjpg` endpoint is public. For strict production, you should add a token validation in `monitor.py` on the Pi, and the mobile app should pass that token (e.g., `?token=YOUR_SECRET`) when requesting the stream.
- **Data Costs**: MJPEG over cellular uses significant bandwidth. Ensure the SIM cards on the Pi devices have sufficient data plans for continuous monitoring, and encourage users not to leave the monitor open indefinitely.

## 4. Hardware Node Production Setup (Cloudflare Named Tunnels)
By default, the Raspberry Pi uses Cloudflare **Quick Tunnels** (URLs ending in `trycloudflare.com`). These are excellent for testing but are actively rate-limited by Cloudflare and are not meant for continuous production streaming.

For a true production deployment, you must configure a **Named Tunnel**:
1. SSH into the Raspberry Pi.
2. Run `cloudflared tunnel login` and authenticate with a free Cloudflare account via the provided link.
3. Create a tunnel: `cloudflared tunnel create ricescan-node1`
4. Route the tunnel to a permanent subdomain you own: `cloudflared tunnel route dns ricescan-node1 stream-node1.yourdomain.com`
5. Edit `config.py` in the `ricescan-client` directory and set your fixed URL, or let the server use the permanent URL directly.
6. The client now uses **Waitress**, a production-grade WSGI server, to handle multiple concurrent stream viewers safely.
