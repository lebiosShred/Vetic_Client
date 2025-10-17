import os
import requests
from flask import Flask, request, jsonify
from PIL import Image
import io

app = Flask(__name__)

# This service uses a manually refreshed Developer Token. This is the most reliable method for this account type.
BOX_ACCESS_TOKEN = os.environ.get('BOX_ACCESS_TOKEN')
OCR_API_KEY = os.environ.get('OCR_API_KEY')
BOX_API_BASE_URL = "https://api.box.com/2.0"
MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1 MB

# --- Endpoint for Listing Folder Contents ---
@app.route('/list-folder', methods=['POST'])
def list_folder_items():
    data = request.get_json()
    if not data or 'folder_id' not in data:
        return jsonify({"error": "folder_id is required."}), 400
    folder_id = data['folder_id']
    
    try:
        headers = {"Authorization": f"Bearer {BOX_ACCESS_TOKEN}"}
        response = requests.get(f"{BOX_API_BASE_URL}/folders/{folder_id}/items", headers=headers)
        if response.status_code == 401:
            return jsonify({"error": "Box API returned 401 Unauthorized. The BOX_ACCESS_TOKEN is invalid or has expired."}), 500
        response.raise_for_status()
        
        items = response.json().get('entries', [])
        item_list = [{"id": item.get('id'), "name": item.get('name'), "type": item.get('type')} for item in items]
        return jsonify({"entries": item_list})
    except Exception as e:
        return jsonify({"error": "Failed to list folder items.", "details": str(e)}), 500

# --- The Endpoint for Processing a File ---
@app.route('/process-invoice', methods=['POST'])
def process_invoice_from_box():
    data = request.get_json()
    if not data or 'filename' not in data or 'parent_folder_id' not in data:
        return jsonify({"error": "Both 'filename' and 'parent_folder_id' are required."}), 400
    
    filename = data['filename']
    parent_folder_id = data['parent_folder_id']
    headers = {"Authorization": f"Bearer {BOX_ACCESS_TOKEN}"}
    
    try:
        # Step 1: Find File
        list_response = requests.get(f"{BOX_API_BASE_URL}/folders/{parent_folder_id}/items", headers=headers)
        if list_response.status_code == 401:
             return jsonify({"error": "Box API returned 401 Unauthorized. The BOX_ACCESS_TOKEN is invalid or has expired."}), 500
        list_response.raise_for_status()
        
        items = list_response.json()['entries']
        file_id = next((item['id'] for item in items if item['type'] == 'file' and item['name'] == filename), None)
        
        if file_id is None:
            return jsonify({"error": f"File '{filename}' not found in folder ID '{parent_folder_id}'."}), 404

        # Step 2: Download File
        download_response = requests.get(f"{BOX_API_BASE_URL}/files/{file_id}/content", headers=headers)
        download_response.raise_for_status()
        image_content = download_response.content

        # Step 3: Resize (if needed)
        if len(image_content) > MAX_FILE_SIZE_BYTES:
            img = Image.open(io.BytesIO(image_content))
            scale_factor = (MAX_FILE_SIZE_BYTES / len(image_content)) ** 0.5
            new_width = int(img.width * scale_factor)
            new_height = int(img.height * scale_factor)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            image_content = buffer.getvalue()

        # Step 4: OCR
        ocr_payload = {"apikey": OCR_API_KEY}
        ocr_files = {"file": (filename, image_content)}
        ocr_response = requests.post("https://api.ocr.space/parse/image", data=ocr_payload, files=ocr_files)
        ocr_response.raise_for_status()
        ocr_result = ocr_response.json()
        
        if ocr_result.get('IsErroredOnProcessing'):
            return jsonify({"error": "OCR processing failed.", "details": ocr_result.get('ErrorMessage')}), 500
        
        extracted_text = ocr_result['ParsedResults'][0]['ParsedText']
        return jsonify({"extracted_text": extracted_text})

    except Exception as e:
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
