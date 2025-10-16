import os
import requests
from flask import Flask, request, jsonify
from PIL import Image
import io

# Import the Box SDK components
from boxsdk import JWTAuth, Client

# Initialize the Flask web application
app = Flask(__name__)

# --- JWT Configuration ---
# This block reads the entire JSON configuration from a single, multi-line
# environment variable named 'BOX_JWT_CONFIG' that you set in Render.
JWT_CONFIG_JSON = os.environ.get('BOX_JWT_CONFIG')

# Check if the secret is present
if not JWT_CONFIG_JSON:
    # This will cause a clean error during startup if the secret is missing.
    raise ValueError("CRITICAL ERROR: The BOX_JWT_CONFIG environment variable is not set.")

# Create an in-memory file-like object for the SDK to read the config from
config_file = io.StringIO(JWT_CONFIG_JSON)
auth = JWTAuth.from_settings_file(config_file)
client = Client(auth)

# --- Other Secrets and Constants ---
OCR_API_KEY = os.environ.get('OCR_API_KEY')
MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1 MB

# --- Skill 1: List Contents of a Folder ---
@app.route('/list-folder', methods=['POST'])
def list_folder_items():
    data = request.get_json()
    if not data or 'folder_id' not in data:
        return jsonify({"error": "folder_id is required."}), 400
    folder_id = data['folder_id']

    try:
        # Use the SDK to get items from the folder
        items = client.folder(folder_id=folder_id).get_items()
        # Format the response to be clean for the AI
        item_list = [{"id": item.id, "name": item.name, "type": item.type} for item in items]
        return jsonify({"entries": item_list})
    except Exception as e:
        return jsonify({"error": "Failed to list folder items.", "details": str(e)}), 500

# --- Skill 2: Process a File by its ID ---
@app.route('/process-file', methods=['POST'])
def process_file_by_id():
    data = request.get_json()
    if not data or 'file_id' not in data:
        return jsonify({"error": "file_id is required."}), 400
    file_id = data['file_id']

    try:
        # 1. Download file content using the SDK
        image_content = client.file(file_id).content()

        # 2. Resize image if it's too large for the OCR service's free tier
        if len(image_content) > MAX_FILE_SIZE_BYTES:
            img = Image.open(io.BytesIO(image_content))
            scale_factor = (MAX_FILE_SIZE_BYTES / len(image_content)) ** 0.5
            new_width = int(img.width * scale_factor)
            new_height = int(img.height * scale_factor)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            image_content = buffer.getvalue()

        # 3. Send the content to the OCR service
        ocr_payload = {"apikey": OCR_API_KEY}
        ocr_files = {"file": (f"{file_id}.png", image_content)}
        ocr_response = requests.post("https://api.ocr.space/parse/image", data=ocr_payload, files=ocr_files)
        ocr_response.raise_for_status()
        ocr_result = ocr_response.json()

        if ocr_result.get('IsErroredOnProcessing'):
            return jsonify({"error": "OCR processing failed.", "details": ocr_result.get('ErrorMessage')}), 500
        
        extracted_text = ocr_result['ParsedResults'][0]['ParsedText']
        
        # 4. Return the final extracted text
        return jsonify({"extracted_text": extracted_text})
        
    except Exception as e:
        return jsonify({"error": "An internal server error occurred while processing the file.", "details": str(e)}), 500

# This block allows for local testing but is ignored by Gunicorn on Render
if __name__ == '__main__':
    # Render provides the PORT environment variable
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
