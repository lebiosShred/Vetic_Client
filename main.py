import os
import requests
from flask import Flask, request, jsonify
from PIL import Image
import io

app = Flask(__name__)

# Load secrets from the environment
BOX_ACCESS_TOKEN = os.environ.get('BOX_ACCESS_TOKEN')
OCR_API_KEY = os.environ.get('OCR_API_KEY')

# Constants
BOX_API_BASE_URL = "https://api.box.com/2.0"
MAX_FILE_SIZE_BYTES = 1024 * 1024

@app.route('/process-invoice', methods=['POST'])
def process_invoice_from_box():
    data = request.get_json()
    if not data or 'filename' not in data or 'parent_folder_id' not in data:
        return jsonify({"error": "Both 'filename' and 'parent_folder_id' are required."}), 400
    
    filename = data['filename']
    parent_folder_id = data['parent_folder_id']
    
    headers = {"Authorization": f"Bearer {BOX_ACCESS_TOKEN}"}
    file_id = None

    # --- STEP 1: Find the file in Box ---
    try:
        list_response = requests.get(f"{BOX_API_BASE_URL}/folders/{parent_folder_id}/items", headers=headers)
        if list_response.status_code == 401:
            return jsonify({"error": "Box API Authentication Failed (401). Check your BOX_ACCESS_TOKEN.", "details": "This happened while trying to list folder contents."}), 500
        list_response.raise_for_status()
        
        items = list_response.json()['entries']
        for item in items:
            if item['type'] == 'file' and item['name'] == filename:
                file_id = item['id']
                break
        
        if file_id is None:
            return jsonify({"error": f"File '{filename}' not found in folder ID '{parent_folder_id}'."}), 404
    except Exception as e:
        return jsonify({"error": "An error occurred while trying to find the file in Box.", "details": str(e)}), 500

    # --- STEP 2: Download the file from Box ---
    try:
        download_response = requests.get(f"{BOX_API_BASE_URL}/files/{file_id}/content", headers=headers)
        if download_response.status_code == 401:
            return jsonify({"error": "Box API Authentication Failed (401). Check your BOX_ACCESS_TOKEN.", "details": "This happened while trying to download the file content."}), 500
        download_response.raise_for_status()
        
        image_content = download_response.content
    except Exception as e:
        return jsonify({"error": "An error occurred while downloading the file from Box.", "details": str(e)}), 500
    
    # --- STEP 3: Resize if needed (no external call) ---
    try:
        if len(image_content) > MAX_FILE_SIZE_BYTES:
            img = Image.open(io.BytesIO(image_content))
            scale_factor = (MAX_FILE_SIZE_BYTES / len(image_content)) ** 0.5
            new_width = int(img.width * scale_factor)
            new_height = int(img.height * scale_factor)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            image_content = buffer.getvalue()
    except Exception as e:
        return jsonify({"error": "An error occurred during image resizing.", "details": str(e)}), 500

    # --- STEP 4: Send to OCR.space ---
    try:
        ocr_payload = {"apikey": OCR_API_KEY}
        ocr_files = {"file": (filename, image_content)}
        ocr_response = requests.post("https://api.ocr.space/parse/image", data=ocr_payload, files=ocr_files)
        
        # OCR.space can return a 200 OK but still have an auth error in the JSON body
        ocr_result = ocr_response.json()
        if ocr_result.get('IsErroredOnProcessing') and "Invalid API Key" in ocr_result.get('ErrorMessage', [''])[0]:
             return jsonify({"error": "OCR.space API Authentication Failed. Check your OCR_API_KEY.", "details": ocr_result['ErrorMessage']}), 500
        
        ocr_response.raise_for_status()
        
        if ocr_result.get('IsErroredOnProcessing'):
            return jsonify({"error": "OCR processing failed.", "details": ocr_result.get('ErrorMessage')}), 500
            
        extracted_text = ocr_result['ParsedResults'][0]['ParsedText']
        return jsonify({"extracted_text": extracted_text})
    except Exception as e:
        return jsonify({"error": "An error occurred while communicating with the OCR service.", "details": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
