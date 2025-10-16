import os
import requests
from flask import Flask, request, jsonify

# This is a temporary diagnostic version of the main.py file.
# It completely removes the Pillow and OCR.space components to isolate the Box API connection.

app = Flask(__name__)

# Load the Developer Token secret
BOX_ACCESS_TOKEN = os.environ.get('BOX_ACCESS_TOKEN')
BOX_API_BASE_URL = "https://api.box.com/2.0"

@app.route('/process-invoice', methods=['POST'])
def process_invoice_from_box_diagnostic():
    data = request.get_json()
    if not data or 'filename' not in data or 'parent_folder_id' not in data:
        return jsonify({"error": "Both 'filename' and 'parent_folder_id' are required."}), 400
    
    filename = data['filename']
    parent_folder_id = data['parent_folder_id']

    try:
        # Prepare headers for Box API calls
        headers = {"Authorization": f"Bearer {BOX_ACCESS_TOKEN}"}
        
        # --- STEP 1: Find the file in Box ---
        list_response = requests.get(f"{BOX_API_BASE_URL}/folders/{parent_folder_id}/items", headers=headers)
        if list_response.status_code == 401:
            return jsonify({"error": "Box API returned 401 Unauthorized while listing folder contents. The BOX_ACCESS_TOKEN is invalid or expired."}), 500
        list_response.raise_for_status()
        
        items = list_response.json()['entries']
        file_id = None
        for item in items:
            if item['type'] == 'file' and item['name'] == filename:
                file_id = item['id']
                break
        
        if file_id is None:
            return jsonify({"error": f"File '{filename}' not found in folder ID '{parent_folder_id}'."}), 404

        # --- STEP 2: Download the file content from Box ---
        download_response = requests.get(f"{BOX_API_BASE_URL}/files/{file_id}/content", headers=headers)
        if download_response.status_code == 401:
            return jsonify({"error": "Box API returned 401 Unauthorized while downloading the file. The BOX_ACCESS_TOKEN is invalid or expired."}), 500
        download_response.raise_for_status()
        
        image_content = download_response.content
        
        # --- STEP 3: Return a success message instead of calling OCR ---
        file_size = len(image_content)
        return jsonify({
            "status": "DIAGNOSTIC_SUCCESS",
            "message": "Successfully downloaded file from Box.",
            "file_size_bytes": file_size
        })

    except Exception as e:
        # This will catch any other errors
        return jsonify({"error": "An internal server error occurred during the Box API interaction.", "details": str(e)}), 500

# This block allows for local testing and will NOT be used by Gunicorn on Render.
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
