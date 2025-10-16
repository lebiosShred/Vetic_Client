import os
import requests
from flask import Flask, request, jsonify
from PIL import Image
import io

app = Flask(__name__)

# NOTE: We have REMOVED the line that reads BOX_ACCESS_TOKEN from the environment.

# Other secrets and constants
OCR_API_KEY = os.environ.get('OCR_API_KEY')
BOX_API_BASE_URL = "https://api.box.com/2.0"
MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1 MB

@app.route('/process-invoice', methods=['POST'])
def process_invoice_from_box():
    # --- CRITICAL CHANGE: Get the token from the incoming request header ---
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "Authorization header is missing. This skill must be linked to a Box connection in Watsonx."}), 401
    
    # The header will be passed by Watsonx, e.g., "Bearer <the_token>"
    headers = {"Authorization": auth_header}

    data = request.get_json()
    if not data or 'filename' not in data or 'parent_folder_id' not in data:
        return jsonify({"error": "Both 'filename' and 'parent_folder_id' are required."}), 400
    
    filename = data['filename']
    parent_folder_id = data['parent_folder_id']
    file_id = None

    try:
        # 1. List items in the parent folder using the PASSED token
        list_response = requests.get(f"{BOX_API_BASE_URL}/folders/{parent_folder_id}/items", headers=headers)
        list_response.raise_for_status()
        
        items = list_response.json()['entries']
        file_id = next((item['id'] for item in items if item['type'] == 'file' and item['name'] == filename), None)
        
        if file_id is None:
            return jsonify({"error": f"File '{filename}' not found in folder ID '{parent_folder_id}'."}), 404

        # 2. Download the file content using the PASSED token
        download_response = requests.get(f"{BOX_API_BASE_URL}/files/{file_id}/content", headers=headers)
        download_response.raise_for_status()
        
        image_content = download_response.content

        # 3. Resize if needed
        if len(image_content) > MAX_FILE_SIZE_BYTES:
            img = Image.open(io.BytesIO(image_content))
            scale_factor = (MAX_FILE_SIZE_BYTES / len(image_content)) ** 0.5
            new_width = int(img.width * scale_factor)
            new_height = int(img.height * scale_factor)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            image_content = buffer.getvalue()

        # 4. Pass to OCR (This part is unchanged)
        ocr_payload = {"apikey": OCR_API_KEY}
        ocr_files = {"file": (filename, image_content)}
        ocr_response = requests.post("https://api.ocr.space/parse/image", data=ocr_payload, files=ocr_files)
        ocr_response.raise_for_status()

        ocr_result = ocr_response.json()
        if ocr_result.get('IsErroredOnProcessing'):
            return jsonify({"error": "OCR processing failed.", "details": ocr_result.get('ErrorMessage')}), 500
            
        extracted_text = ocr_result['ParsedResults'][0]['ParsedText']

        # 5. Return final text
        return jsonify({"extracted_text": extracted_text})

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            return jsonify({"error": "The token passed by Watsonx was rejected by Box (401 Unauthorized). Check the native Box connection in Watsonx."}), 500
        return jsonify({"error": "An HTTP error occurred while communicating with Box.", "details": str(e)}), 500
    except Exception as e:
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
