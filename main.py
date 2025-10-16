import os
import requests
from flask import Flask, request, jsonify
from PIL import Image, ImageOps
import io
import tempfile
import cv2
import numpy as np

# Choose an advanced OCR library
# e.g. EasyOCR or PaddleOCR
from easyocr import Reader  # pip install easyocr

app = Flask(__name__)

BOX_ACCESS_TOKEN = os.environ.get('BOX_ACCESS_TOKEN')
BOX_API_BASE_URL = "https://api.box.com/2.0"
MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1 MB

# Initialize OCR reader (English, you can add more langs)
ocr_reader = Reader(['en'], gpu=False)  # set gpu=True if you have GPU support

def preprocess_image_for_ocr(image_bytes: bytes) -> bytes:
    """
    Preprocess image with OpenCV / PIL to improve OCR quality:
    - convert to grayscale
    - denoise / blur
    - adaptive thresholding or contrast enhancement
    - deskew / rotation correction (if needed)
    """
    # Load into OpenCV
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        # fallback to PIL
        pil = Image.open(io.BytesIO(image_bytes))
        pil = pil.convert("L")
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        return buf.getvalue()

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Denoise / blur
    gray = cv2.fastNlMeansDenoising(gray, h=30)

    # Adaptive thresholding
    thr = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        15,
        10
    )

    # Optionally deskew: compute rotation and rotate
    # (skipped here for simplicity)

    # Convert back to bytes (PNG)
    is_success, buffer = cv2.imencode(".png", thr)
    if not is_success:
        return image_bytes
    return buffer.tobytes()

@app.route('/list-folder', methods=['POST'])
def list_folder_items():
    data = request.get_json()
    if not data or 'folder_id' not in data:
        return jsonify({"error": "folder_id is required."}), 400
    folder_id = data['folder_id']
    headers = {"Authorization": f"Bearer {BOX_ACCESS_TOKEN}"}
    try:
        response = requests.get(f"{BOX_API_BASE_URL}/folders/{folder_id}/items", headers=headers)
        if response.status_code == 401:
            return jsonify({"error": "Box API Unauthorized"}), 500
        response.raise_for_status()
        items = response.json().get('entries', [])
        item_list = [{"id": item.get('id'), "name": item.get('name'), "type": item.get('type')} for item in items]
        return jsonify({"entries": item_list})
    except Exception as e:
        return jsonify({"error": "Failed to list folder items.", "details": str(e)}), 500

@app.route('/process-invoice', methods=['POST'])
def process_invoice_from_box():
    data = request.get_json()
    if not data or 'filename' not in data or 'parent_folder_id' not in data:
        return jsonify({"error": "Both 'filename' and 'parent_folder_id' are required."}), 400

    filename = data['filename']
    parent_folder_id = data['parent_folder_id']
    headers = {"Authorization": f"Bearer {BOX_ACCESS_TOKEN}"}

    try:
        # Step 1: List files in parent folder
        list_response = requests.get(f"{BOX_API_BASE_URL}/folders/{parent_folder_id}/items", headers=headers)
        if list_response.status_code == 401:
            return jsonify({"error": "Box API Unauthorized"}), 500
        list_response.raise_for_status()

        items = list_response.json().get('entries', [])
        file_id = next((item['id'] for item in items if item['type'] == 'file' and item['name'] == filename), None)
        if file_id is None:
            return jsonify({"error": f"File '{filename}' not found."}), 404

        # Step 2: Download the file
        download_response = requests.get(f"{BOX_API_BASE_URL}/files/{file_id}/content", headers=headers)
        download_response.raise_for_status()
        file_bytes = download_response.content

        # Step 3: If it's PDF, convert pages to images (you can use pdf2image)  
        # (for simplicity, assuming image input; but you can add PDF handling)

        # Step 4: If too large, downscale
        if len(file_bytes) > MAX_FILE_SIZE_BYTES:
            img = Image.open(io.BytesIO(file_bytes))
            scale = (MAX_FILE_SIZE_BYTES / len(file_bytes)) ** 0.5
            new_w = int(img.width * scale)
            new_h = int(img.height * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            file_bytes = buf.getvalue()

        # Step 5: Preprocess image for better OCR quality
        prep_bytes = preprocess_image_for_ocr(file_bytes)

        # Step 6: Run OCR with EasyOCR
        results = ocr_reader.readtext(
            prep_bytes,
            detail=0,  # only extract text lines (no bounding boxes); set detail=1 if you need boxes
            paragraph=False
        )
        # results is a list of strings (each line)

        extracted_text = "\n".join(results)
        return jsonify({"extracted_text": extracted_text})

    except Exception as e:
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
