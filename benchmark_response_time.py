import urllib.request
import glob
import time
import os
import statistics
import json

URL = "https://rice-pest-cnn.onrender.com/analyze"
boundary = "----TestBoundaryPestCNN777"

# Gather 30 test images from different pest folders
images = glob.glob("dataset/*/*.jpg")
# Select 30 distributed images
step = max(1, len(images) // 30)
selected_images = images[::step][:30]

print(f"Running benchmark on {len(selected_images)} images against {URL}...")

times = []
results = []

for idx, img_path in enumerate(selected_images, 1):
    with open(img_path, "rb") as f:
        file_bytes = f.read()

    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{os.path.basename(img_path)}"\r\n'.encode("utf-8"))
    body.extend(b"Content-Type: image/jpeg\r\n\r\n")
    body.extend(file_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        URL,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp_data = resp.read()
            elapsed = time.perf_counter() - t0
            times.append(elapsed)
            data_json = json.loads(resp_data.decode("utf-8"))
            pest = data_json.get("pest", "Unknown")
            conf = data_json.get("confidence", 0)
            print(f"[{idx:02d}/30] {os.path.basename(img_path)}: {elapsed:.3f}s -> {pest} ({conf}%)")
    except Exception as e:
        print(f"[{idx:02d}/30] Error on {img_path}: {e}")

if times:
    print("\n" + "="*50)
    print("BENCHMARK SUMMARY (30 TRIALS)")
    print("="*50)
    print(f"Mean Response Time : {statistics.mean(times):.4f} seconds")
    print(f"Median Response Time: {statistics.median(times):.4f} seconds")
    print(f"Min Response Time   : {min(times):.4f} seconds")
    print(f"Max Response Time   : {max(times):.4f} seconds")
    print(f"Standard Deviation  : {statistics.stdev(times):.4f} seconds")
    print("="*50)
