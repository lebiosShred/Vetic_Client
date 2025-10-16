import os
import requests
from flask import Flask, request, jsonify
from PIL import Image
import io

# Flask app initialization
app = Flask(__name__)

# Load secrets from Render's environment variables
BOX_ACCESS_TOKEN = os.environ.get('BOX_ACCESS_TOKEN')
OCR_API_KEY = os.environ.get('OCR_API_KEY')

# Constants
BOX_API_BASE_URL = "https://api.box.com/2.0"
MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1 MB

@app.route('/process-invoice', methods=['POST'])
def process_invoice_from_box():
    """
    An all-in-one endpoint to find a file in a specific Box folder, 
    download it, resize if needed, and perform OCR.
    """
    # Get the JSON data from the request
    data = request.get_json()
    if not data or 'filename' not in data or 'parent_folder_id' not in data:
        return jsonify({"error": "Both 'filename' and 'parent_folder_id' are required."}), 400
    
    filename = data['filename']
    parent_folder_id = data['parent_folder_id']

    try:
        # 1. List items in the parent folder to find the file's ID (INSTANT AND RELIABLE)
        list_headers = {"Authorization": f"Bearer {BOX_ACCESS_TOKEN}"}
        list_response = requests.get(f"{BOX_API_BASE_URL}/folders/{parent_folder_id}/items", headers=list_headers)
        list_response.raise_for_status() # Raise an exception for bad status codes
        
        items = list_response.json()['entries']
        file_id = None
        for item in items:
            if item['type'] == 'file' and item['name'] == filename:
                file_id = item['id']
                break
        
        if file_id is None:
            return jsonify({"error": f"File '{filename}' not found in folder ID '{parent_folder_id}'."}), 404

        # 2. Download the file content from Box
        download_headers = {"Authorization": f"Bearer {BOX_ACCESS_TOKEN}"}
        download_response = requests.get(f"{BOX_API_BASE_URL}/files/{file_id}/content", headers=download_headers)
        download_response.raise_for_status()
        
        image_content = download_response.content

        # 3. Resize the image if it exceeds the 1MB limit for OCR.space free tier
        if len(image_content) > MAX_FILE_SIZE_BYTES:
            img = Image.open(io.BytesIO(image_content))
            scale_factor = (MAX_FILE_SIZE_BYTES / len(image_content)) ** 0.5
            new_width = int(img.width * scale_factor)
            new_height = int(img.height * scale_factor)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            
            buffer = io.BytesIO()
            img.save(buffer, format='PNG') # Save as PNG, adjust if using other formats
            image_content = buffer.getvalue()

        # 4. Pass the (potentially resized) content to OCR.space
        ocr_payload = {"apikey": OCR_API_KEY}
        ocr_files = {"file": (filename, image_content)}
        ocr_response = requests.post("https://api.ocr.space/parse/image", data=ocr_payload, files=ocr_files)
        ocr_response.raise_for_status()

        ocr_result = ocr_response.json()
        if ocr_result.get('IsErroredOnProcessing'):
            return jsonify({"error": "OCR processing failed.", "details": ocr_result.get('ErrorMessage')}), 500
            
        extracted_text = ocr_result['ParsedResults'][0]['ParsedText']

        # 5. Return the final, successful result
        return jsonify({"extracted_text": extracted_text})

    except requests.exceptions.RequestException as e:
        # Handle API errors (e.g., bad request, auth issues)
        return jsonify({"error": "An API communication error occurred.", "details": str(e)}), 500
    except Exception as e:
        # Handle any other unexpected errors
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500

# This block is for local testing and will NOT be used by Render.
if __name__ == '__main__':
    # The host must be '0.0.0.0' to be accessible within a container environment
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))