import os
import requests
from flask import Flask, request, jsonify
from PIL import Image
import io

app = Flask(__name__)

# Load the Developer Token secret
BOX_ACCESS_TOKEN = os.environ.get('BOX_ACCESS_TOKEN')

# Other secrets and constants
OCR_API_KEY = os.environ.get('OCR_API_KEY')
BOX_API_BASE_URL = "https://api.box.com/2.0"
MAX_FILE_SIZE_BYTES = 1024 * 1024

@app.route('/process-invoice', methods=['POST'])
def process_invoice_from_box():
    data = request.get_json()
    if not data or 'filename' not in data or 'parent_folder_id' not in data:
        return jsonify({"error": "Both 'filename' and 'parent_folder_id' are required."}), 400
    
    filename = data['filename']
    parent_folder_id = data['parent_folder_id']

    try:
        # Use the Developer Token in the Authorization header for all Box API calls
        headers = {"Authorization": f"Bearer {BOX_ACCESS_TOKEN}"}

        # 1. List items in the parent folder
        list_response = requests.get(f"{BOX_API_BASE_URL}/folders/{parent_folder_id}/items", headers=headers)
        list_response.raise_for_status()
        
        items = list_response.json()['entries']
        file_id = None
        for item in items:
            if item['type'] == 'file' and item['name'] == filename:
                file_id = item['id']
                break
        
        if file_id is None:
            return jsonify({"error": f"File '{filename}' not found in folder ID '{parent_folder_id}'."}), 404

        # 2. Download the file content
        download_response = requests.get(f"{BOX_API_BASE_URL}/files/{file_id}/content", headers=headers)
        download_response.raise_for_status()
        
        image_content = download_response.content

        # 3. Resize if needed
        if len(image_content) > MAX_FILE_SIZE_BYTES:
            img = Image.open(io.BytesIO(image_content))
            # ... (resize logic is the same)
            scale_factor = (MAX_FILE_SIZE_BYTES / len(image_content)) ** 0.5
            new_width = int(img.width * scale_factor)
            new_height = int(img.height * scale_factor)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            image_content = buffer.getvalue()

        # 4. Pass to OCR
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

    except Exception as e:
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)```

#### Step 2: Revert Your `Dockerfile`

Remove the complex build steps, as they are no longer needed. Use this simpler version.

```dockerfile
# Start from a standard, official Python 3.9 base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port that Gunicorn will run on
EXPOSE 10000

# The command to run when the container starts
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "120", "main:app"]
