import io
import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from PIL import Image, ImageOps, UnidentifiedImageError
from evidence import intake as evidence_intake, verify as evidence_verify, list_evidence, record_action
from werkzeug.utils import secure_filename

load_dotenv()
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024
CORS(app, resources={r"/api/*": {"origins": [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:4173", "http://127.0.0.1:4173"
]}})

SERPAPI_IMAGE_URL = "https://serpapi.com/image"
SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"
ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp", "image/tiff", "image/bmp"}
PROVIDER_MAX_BYTES = 500 * 1024


def prepare_image(file_bytes: bytes) -> bytes:
    """Convert supported raster input to a JPEG payload under SerpApi's 500 KB limit."""
    try:
        with Image.open(io.BytesIO(file_bytes)) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("The uploaded file could not be decoded as a supported image.") from exc

    image.thumbnail((2200, 2200), Image.Resampling.LANCZOS)
    for _ in range(12):
        for quality in (88, 82, 76, 70, 64, 58, 52, 46):
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=quality, optimize=True)
            data = output.getvalue()
            if len(data) <= PROVIDER_MAX_BYTES:
                return data
        image.thumbnail((int(image.width * 0.82), int(image.height * 0.82)), Image.Resampling.LANCZOS)
    raise ValueError("Could not prepare this image below the provider's 500 KB upload limit.")


def provider_error(response):
    try:
        data = response.json()
        return data.get("error") or data.get("message") or response.text[:400]
    except ValueError:
        return response.text[:400]



AI_PIPELINE = None
AI_MODEL_ID = os.getenv("AI_MODEL_ID", "umm-maybe/AI-image-detector")

def get_ai_pipeline():
    global AI_PIPELINE
    if AI_PIPELINE is None:
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError("AI model dependencies are not installed. Run: py -3.11 -m pip install -r requirements-ai.txt") from exc
        AI_PIPELINE = pipeline("image-classification", model=AI_MODEL_ID, device=-1)
    return AI_PIPELINE

@app.post("/api/analyze")
def analyze_image():
    uploaded=request.files.get("image")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error":"Select an image to analyse."}),400
    raw=uploaded.read()
    if not raw: return jsonify({"error":"The uploaded image is empty."}),400
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im=ImageOps.exif_transpose(im).convert("RGB")
            outputs=get_ai_pipeline()(im)
    except RuntimeError as exc: return jsonify({"error":str(exc)}),503
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError): return jsonify({"error":"Could not decode this image."}),400
    except Exception as exc:
        app.logger.exception("AI inference failed")
        return jsonify({"error":"AI model inference failed. Check model download, dependencies and backend logs."}),502
    ranked=sorted(outputs,key=lambda x:float(x.get('score',0)),reverse=True)
    if not ranked: return jsonify({"error":"The model returned no classification scores."}),502
    top=ranked[0]; label=str(top.get('label','unknown')); score=round(float(top.get('score',0))*100,2)
    ai_like=any(token in label.lower() for token in ('fake','artificial','ai','generated','synthetic'))
    return jsonify({"provider":"Hugging Face Transformers","model":AI_MODEL_ID,"classification":label,"confidence":score,"scores":[{"label":x.get('label'),'confidence':round(float(x.get('score',0))*100,2)} for x in ranked],"assessment":"AI-like" if ai_like else "Real-like / model class: "+label,"filename":secure_filename(uploaded.filename),"limitations":"Model prediction only; not a validated forensic conclusion. This model is an older proof-of-concept trained for artistic images and may perform poorly on photographs, screenshots and newer generators. No pixel-level localization or morph detection is performed."})

@app.post("/api/evidence")
def create_evidence():
    uploaded=request.files.get('image')
    if uploaded is None or not uploaded.filename: return jsonify({"error":"Choose an image file."}),400
    raw=uploaded.read()
    if not raw: return jsonify({"error":"The uploaded file is empty."}),400
    source=request.form.get('source','').strip(); method=request.form.get('method','').strip(); examiner=request.form.get('examiner','Local examiner').strip()
    if not source or not method: return jsonify({"error":"Source and acquisition method are required."}),400
    try: record=evidence_intake(raw,uploaded.filename,source,method,examiner)
    except Exception:
        app.logger.exception('Evidence intake failed'); return jsonify({"error":"Evidence could not be safely stored."}),500
    return jsonify(record),201

@app.get("/api/evidence")
def get_evidence(): return jsonify({"items":list_evidence()})

@app.post("/api/evidence/<evidence_id>/verify")
def verify_evidence(evidence_id):
    result=evidence_verify(evidence_id)
    if result is None: return jsonify({"error":"Evidence ID not found."}),404
    return jsonify(result)

@app.post("/api/evidence/<evidence_id>/actions")
def add_evidence_action(evidence_id):
    data=request.get_json(silent=True) or {}
    action=str(data.get('action','')).strip(); examiner=str(data.get('examiner','Local examiner')).strip(); notes=str(data.get('notes','')).strip()
    if not action: return jsonify({"error":"Action description is required."}),400
    result=record_action(evidence_id,action,examiner,notes)
    if result is None: return jsonify({"error":"Evidence ID not found."}),404
    return jsonify(result),201

@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "MASKX image trace backend", "provider_configured": bool(os.getenv("SERPAPI_API_KEY"))})


@app.post("/api/trace")
def trace_image():
    api_key = os.getenv("SERPAPI_API_KEY", "").strip()
    if not api_key:
        return jsonify({"error": "SerpApi API key is missing. Add SERPAPI_API_KEY to backend/.env and restart the backend."}), 503

    uploaded = request.files.get("image")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "No image file was received. Select an image and try again."}), 400
    if uploaded.mimetype not in ALLOWED_MIMES:
        return jsonify({"error": "Unsupported image type. Use JPG, PNG, WEBP, TIFF or BMP."}), 415

    raw = uploaded.read()
    if not raw:
        return jsonify({"error": "The uploaded image is empty."}), 400

    try:
        prepared = prepare_image(raw)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        upload_response = requests.post(
            SERPAPI_IMAGE_URL,
            files={"image": ("maskx-evidence.jpg", prepared, "image/jpeg")},
            data={"api_key": api_key},
            timeout=45,
        )
        if not upload_response.ok:
            return jsonify({"error": f"Image upload provider error: {provider_error(upload_response)}"}), 502
        upload_data = upload_response.json()
        image_id = upload_data.get("image_id")
        if not image_id:
            return jsonify({"error": "The image provider did not return an image ID."}), 502

        search_response = requests.get(
            SERPAPI_SEARCH_URL,
            params={"engine": "google_lens", "image_id": image_id, "api_key": api_key, "type": "visual_matches", "hl": "en", "country": "in"},
            timeout=90,
        )
        if not search_response.ok:
            return jsonify({"error": f"Google Lens search failed: {provider_error(search_response)}"}), 502
        data = search_response.json()
        if data.get("error"):
            return jsonify({"error": data["error"]}), 502

        visual_matches = data.get("visual_matches") or []
        related_content = data.get("related_content") or []
        exact_matches = data.get("exact_matches") or []
        metadata = data.get("search_metadata") or {}

        return jsonify({
            "provider": "SerpApi / Google Lens",
            "search_status": metadata.get("status", "Success"),
            "searched_at": datetime.now(timezone.utc).isoformat(),
            "uploaded_filename": uploaded.filename,
            "prepared_image_bytes": len(prepared),
            "visual_matches": visual_matches,
            "exact_matches": exact_matches,
            "related_content": related_content,
            "total_visual_matches": len(visual_matches),
        })
    except requests.Timeout:
        return jsonify({"error": "The image-search provider timed out. Please try again."}), 504
    except requests.RequestException as exc:
        app.logger.exception("Provider request failed")
        return jsonify({"error": "Could not reach the image-search provider. Check the backend internet connection."}), 502
    except ValueError:
        return jsonify({"error": "The image-search provider returned invalid JSON."}), 502


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "Image is larger than the 20 MB MASKX upload limit."}), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
