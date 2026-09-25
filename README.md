# Rice Pest CNN & API Server

This repository contains the backend and machine learning infrastructure for the **Rice Pest Classification System**, built for a thesis project. It takes images of rice pests and returns the predicted pest name along with confidence scores.

---

## 🛠️ Technology Stack
* **Machine Learning:** PyTorch, MobileNetV3 (Transfer Learning & Fine-Tuning)
* **Model Format:** ONNX (Open Neural Network Exchange)
* **Backend Server:** Python, FastAPI, Uvicorn, ONNX Runtime
* **Deployment:** GitHub, Render (Cloud Platform)

---

## 🌾 Supported Pest Classes (9 Active Classes)
The system supports classification and detection for 9 rice pest species:
1. **Army Worm** (`army_worm`)
2. **Brown Plant Hopper** (`brown_plant_hopper`)
3. **Golden Apple Snail** (`golden_apple_snail`)
4. **Rice Black Bug** (`rice_black_bug`)
5. **Rice Bugs** (`rice_bugs`)
6. **Rice Leaf Caterpillar** (`rice_leaf_caterpillar`)
7. **Rice Leaf Hopper** (`rice_leaf_hopper`)
8. **Rice Leaf Roller** (`rice_leaf_roller`)
9. **Rice Stem Borer** (`rice_stem_borer`)

---

## 📖 Phase 1: How We Built the Enhanced CNN Model
The model was trained on Google Colab using GPU acceleration for fast training and convergence.

1. **Dataset Organization & Preprocessing:** 
   * Standardized to 224x224 RGB inputs with ImageNet normalization:
     - Mean: `[0.485, 0.456, 0.406]`
     - Std: `[0.229, 0.224, 0.225]`
2. **Data Augmentation:**
   * Utilized random horizontal flipping, rotation (-25° to +25°), brightness adjustment (0.7 to 1.3), and contrast enhancement to balance minority classes and prevent overfitting.
3. **Training Strategy:**
   * Used **MobileNetV3**, pre-trained on ImageNet for lightweight and low-latency inference on mobile & edge IoT devices.
   * Optimized with Adam optimizer and learning rate scheduling (`StepLR`).
4. **ONNX Export:**
   * Exported to a self-contained ONNX model (`rice_pest_model.onnx`) with dynamic batching support `[batch_size, 3, 224, 224] -> [batch_size, 9]`, eliminating the heavy PyTorch runtime dependency in production.

---

## 🌐 Phase 2: The Server and Deployment
Instead of running heavy models on mobile or edge devices, inference is served via a Cloud API. This allows lightweight mobile clients and ESP32 IoT camera nodes to access real-time inference.

1. **FastAPI Backend (`server/main.py`):**
   * Loads `rice_pest_model.onnx` into memory on startup via `onnxruntime.InferenceSession`.
   * **`POST /analyze`**: Accepts multipart image uploads (e.g. from mobile app), runs inference, and returns predicted pest, confidence percentage, and active pest scores (filtered with a **60% threshold**).
   * **`POST /predict`**: Accepts raw binary image bytes from ESP32 IoT cameras, applies **60% confidence threshold** and active pest gating, stores records in SQLite (`detections.db`), and saves detection images to `static/detections/`.
   * **`GET /detections/{serial}`**: Mobile sync endpoint that fetches detections for a specific device serial and schedules automatic file cleanup.
2. **Local Testing:**
   * Run server locally:
     ```bash
     cd server
     uvicorn main:app --reload
     ```
3. **Cloud Deployment (Render):**
   * Push updates to GitHub repository.
   * Render automatically installs dependencies from `requirements.txt` (using Python specified in `runtime.txt`) and launches the web service.

---

## 🚀 How to Update the Model in the Future
1. Place the new `rice_pest_model.onnx` into both `model/` and `server/` directories.
2. If new pest classes are introduced, verify that `CLASS_NAMES` in `server/main.py` matches the alphabetical order of the dataset class folders.
3. Commit and push changes to GitHub. Render will rebuild and deploy the new model automatically.
