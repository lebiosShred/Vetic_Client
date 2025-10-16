import os
import requests
from flask import Flask, request, jsonify
from PIL import Image
import io

app = Flask(__name__)
BOX_ACCESS_TOKEN = os.environ.get('BOX_ACCESS_TOKEN')
OCR_API_KEY = os.environ.get('OCR_API_KEY')
BOX_API_BASE_URL = "https://api.box.com/2.0"
MAX_FILE_SIZE_BYTES = 1024 * 1024

@app.route('/find-file', methods=['POST'])
def find_file_in_box():
    # ... (code is the same as before)
    data = request.get_json()
    if not data or 'filename' not in data:
        return jsonify({"error": "Filename is required."}), 400
    filename = data['filename']
    try:
        search_headers = {"Authorization": f"Bearer {BOX_ACCESS_TOKEN}"}
        search_params = {"query": filename, "type": "file", "limit": 1}
        search_response = requests.get(f"{BOX_API_BASE_URL}/search", headers=search_headers, params=search_params)
        search_response.raise_for_status()
        results = search_response.json()
        if not results['entries']:
            return jsonify({"error": f"File '{filename}' not found."}), 404
        file_info = results['entries'][0]
        return jsonify({
            "file_id": file_info['id'],
            "filename": file_info['name'],
            "parent_folder_id": file_info['parent']['id']
        })
    except Exception as e:
        return jsonify({"error": "An error occurred while searching for the file.", "details": str(e)}), 500

@app.route('/process-file', methods=['POST'])
def process_file_by_id():
    # ... (code is the same as before)
    data = request.get_json()
    if not data or 'file_id' not in data:
        return jsonify({"error": "file_id is required."}), 400
    file_id = data['file_id']
    try:
        download_headers = {"Authorization": f"Bearer {BOX_ACCESS_TOKEN}"}
        download_response = requests.get(f"{BOX_API_BASE_URL}/files/{file_id}/content", headers=download_headers)
        download_response.raise_for_status()
        image_content = download_response.content
        if len(image_content) > MAX_FILE_SIZE_BYTES:
            img = Image.open(io.BytesIO(image_content))
            scale_factor = (MAX_FILE_SIZE_BYTES / len(image_content)) ** 0.5
            new_width = int(img.width * scale_factor)
            new_height = int(img.height * scale_factor)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            image_content = buffer.getvalue()
        ocr_payload = {"apikey": OCR_API_KEY}
        ocr_files = {"file": (f"{file_id}.png", image_content)}
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
    app.run(host='0.0.0.0', port=8080)
