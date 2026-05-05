# Rice Pest CNN & API Server

This repository contains the backend and machine learning infrastructure for the **Rice Pest Classification System**, built for a thesis project. It takes images of rice pests and returns the predicted pest name along with confidence scores.

---

## 🛠️ Technology Stack
* **Machine Learning:** PyTorch, MobileNetV3 (Transfer Learning)
* **Model Format:** ONNX (Open Neural Network Exchange)
* **Backend Server:** Python, FastAPI, Uvicorn, ONNX Runtime
* **Deployment:** GitHub, Render (Cloud Platform)

---

## 📖 Phase 1: How We Built the CNN Model
The model was trained entirely on Google Colab using a free T4 GPU to ensure fast training times.

1. **Dataset Organization:** 
   * Collected 2,150 images across 4 classes: Asiatic Rice Borer, Paddy Stem Maggot, Rice Leaf Caterpillar, and Rice Leaf Roller.
   * Formatted and normalized all filenames.
2. **Data Augmentation (Fixing Imbalance):**
   * The initial dataset was imbalanced (ranging from 325 to 745 images per class). 
   * We wrote an augmentation script (rotating, flipping, adjusting brightness) to generate extra images for the minority classes until all 4 classes had exactly **700 images** in the training set.
3. **Training Strategy:**
   * Used **MobileNetV3**, pre-trained on ImageNet. This is highly efficient for mobile/IoT use-cases.
   * Modified the final classifier layer to output exactly 4 classes.
   * Trained for 20 Epochs using the Adam optimizer.
4. **Evaluation:**
   * The model achieved a **99.08% Test Accuracy**.
   * Out of 327 unseen test images, only 3 were misclassified.
5. **ONNX Export:**
   * Exported the `.pth` PyTorch model into a single self-contained `.onnx` file (approx. 6MB) so the server can run predictions without needing the heavy PyTorch library.

---

## 🌐 Phase 2: The Server and Deployment
Instead of placing the AI inside the mobile app, we hosted it as a Cloud API. This keeps the mobile app lightweight and allows ESP32 IoT cameras to use the exact same AI.

1. **FastAPI Backend:**
   * We built a `main.py` server using FastAPI.
   * The server loads the `.onnx` model into memory once upon startup via `onnxruntime`.
   * It exposes a `POST /analyze` endpoint that accepts image files, preprocesses them (resize to 224x224, normalize), runs the inference, and returns JSON.
2. **Local Testing:**
   * Validated locally using `uvicorn main:app --reload`.
3. **Cloud Deployment (Render):**
   * Pushed the code to GitHub.
   * Linked the repository to **Render (Free Tier)**.
   * Render automatically installs dependencies from `requirements.txt` (using Python 3.11 specified in `runtime.txt`) and launches the web service.

---

## 🚀 Future Upgrades: How to Update the CNN
When you gather a new dataset (e.g., adding a 5th pest like "Brown Planthopper", or just adding 1,000 new images to improve accuracy), follow these steps to upgrade the server safely:

### 1. Update the Dataset & Colab
1. Upload the new images to the `dataset` folder in your Google Drive.
2. Open the `training/train.ipynb` notebook in Google Colab.
3. Re-run the cells:
   * The augmentation cell will automatically balance the new images.
   * If you added a **5th class**, change the final layer from `4` to `5` in the Colab code (`nn.Linear(..., 5)`).
4. Re-train the model until you get high validation accuracy.
5. Re-run the ONNX export cell to generate a new `rice_pest_model.onnx`.

### 2. Update the Server Code
1. Download the new `rice_pest_model.onnx` from Google Drive.
2. Replace the old `.onnx` file inside the `server/` folder on your laptop.
3. Open `server/main.py`:
   * If you added a new pest class, update the `CLASS_NAMES` dictionary to include the new ID and name.
   * If you only added images to existing classes, you don't need to change any Python code!
4. Test locally using `uvicorn` to ensure it works.

### 3. Push to Production
1. Open terminal and run:
   ```bash
   git add .
   git commit -m "Upgrade: Retrained CNN model with new dataset"
   git push
   ```
2. Render will detect the GitHub push, automatically download the new `.onnx` file, and restart the server with the new, smarter AI. No app store updates required for your users!
