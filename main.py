import os
from flask import Flask, request, jsonify
from PIL import Image
import io

# Import the Box SDK
from boxsdk import JWTAuth, Client

app = Flask(__name__)

# --- JWT Configuration ---
# You will get this JSON file from the Box Dev Console
# and add its content as a single, multi-line secret in Render.
JWT_CONFIG_JSON = os.environ.get('BOX_JWT_CONFIG')
if not JWT_CONFIG_JSON:
    raise ValueError("BOX_JWT_CONFIG secret not found!")

# Use an in-memory file-like object for the config
config_file = io.StringIO(JWT_CONFIG_JSON)
auth = JWTAuth.from_settings_file(config_file)
client = Client(auth)

# --- Other Secrets ---
OCR_API_KEY = os.environ.get('OCR_API_KEY')
MAX_FILE_SIZE_BYTES = 1024 * 1024

# --- NEW ENDPOINT FOR LISTING FOLDER ITEMS ---
@app.route('/list-folder', methods=['POST'])
def list_folder_items():
    data = request.get_json()
    if not data or 'folder_id' not in data:
        return jsonify({"error": "folder_id is required."}), 400
    folder_id = data['folder_id']

    try:
        items = client.folder(folder_id=folder_id).get_items()
        item_list = [{"id": item.id, "name": item.name, "type": item.type} for item in items]
        return jsonify({"entries": item_list})
    except Exception as e:
        return jsonify({"error": "Failed to list folder items.", "details": str(e)}), 500

# --- UPDATED ENDPOINT TO PROCESS A FILE BY ID ---
@app.route('/process-file', methods=['POST'])
def process_file_by_id():
    data = request.get_json()
    if not data or 'file_id' not in data:
        return jsonify({"error": "file_id is required."}), 400
    file_id = data['file_id']

    try:
        # Download, resize, and OCR
        image_content = client.file(file_id).content()

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
