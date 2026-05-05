from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import onnxruntime as ort
import numpy as np
from PIL import Image
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load model once when server starts
session = ort.InferenceSession("rice_pest_model.onnx")

CLASS_NAMES = {
    0: "Asiatic Rice Borer",
    1: "Paddy Stem Maggot",
    2: "Rice Leaf Caterpillar",
    3: "Rice Leaf Roller"
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
            for i in range(4)
        }
    }
    