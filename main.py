import os
import requests
from flask import Flask, request, jsonify, redirect
from PIL import Image
import io
import time
from threading import Lock

app = Flask(__name__)

# OAuth Configuration
BOX_CLIENT_ID = os.environ.get('BOX_CLIENT_ID', 'c2gilm77s5ucihj6qpytqbcb6o3ct8al')
BOX_CLIENT_SECRET = os.environ.get('BOX_CLIENT_SECRET', 'wzX3mQpNNgKYJwZ3U1Fki06pfcaXcTho')
BOX_REFRESH_TOKEN = os.environ.get('BOX_REFRESH_TOKEN')
OCR_API_KEY = os.environ.get('OCR_API_KEY')

BOX_API_BASE_URL = "https://api.box.com/2.0"
BOX_AUTH_URL = "https://api.box.com/oauth2/token"
MAX_FILE_SIZE_BYTES = 1024 * 1024

# Token storage (in-memory)
token_data = {
    'access_token': None,
    'expires_at': 0
}
token_lock = Lock()

def get_access_token():
    """Get a valid access token, refreshing if necessary"""
    with token_lock:
        # Check if current token is still valid (with 5 min buffer)
        if token_data['access_token'] and time.time() < (token_data['expires_at'] - 300):
            return token_data['access_token']
        
        # Refresh the token
        print("Refreshing Box access token...")
        try:
            response = requests.post(BOX_AUTH_URL, data={
                'grant_type': 'refresh_token',
                'refresh_token': BOX_REFRESH_TOKEN,
                'client_id': BOX_CLIENT_ID,
                'client_secret': BOX_CLIENT_SECRET
            })
            response.raise_for_status()
            
            token_response = response.json()
            token_data['access_token'] = token_response['access_token']
            token_data['expires_at'] = time.time() + token_response.get('expires_in', 3600)
            
            print(f"Token refreshed successfully. Expires in {token_response.get('expires_in', 3600)} seconds")
            return token_data['access_token']
            
        except Exception as e:
            print(f"ERROR refreshing token: {e}")
            raise Exception(f"Failed to refresh Box access token: {e}")

# ===== TEMPORARY SETUP ENDPOINTS (Remove after getting refresh token) =====

@app.route('/oauth/start', methods=['GET'])
def oauth_start():
    """Step 1: Redirect user to Box authorization page"""
    auth_url = (
        f"https://account.box.com/api/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={BOX_CLIENT_ID}"
        f"&redirect_uri=https://veticdb.onrender.com/oauth/callback"
    )
    return redirect(auth_url)

@app.route('/oauth/callback', methods=['GET'])
def oauth_callback():
    """Step 2: Exchange authorization code for refresh token"""
    code = request.args.get('code')
    
    if not code:
        return jsonify({"error": "No authorization code received"}), 400
    
    try:
        # Exchange code for tokens
        response = requests.post(BOX_AUTH_URL, data={
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': BOX_CLIENT_ID,
            'client_secret': BOX_CLIENT_SECRET
        })
        response.raise_for_status()
        
        tokens = response.json()
        
        return jsonify({
            "success": True,
            "message": "✅ Authorization successful! Copy the refresh_token below and add it to your BOX_REFRESH_TOKEN environment variable in Render.",
            "refresh_token": tokens.get('refresh_token'),
            "access_token": tokens.get('access_token'),
            "expires_in": tokens.get('expires_in'),
            "instructions": [
                "1. Copy the refresh_token value above",
                "2. Go to Render Dashboard > Your Service > Environment",
                "3. Add new environment variable: BOX_REFRESH_TOKEN = [paste the refresh token]",
                "4. Remove these temporary endpoints (/oauth/start and /oauth/callback) from your code",
                "5. Redeploy your service"
            ]
        })
        
    except Exception as e:
        return jsonify({
            "error": "Failed to exchange code for tokens",
            "details": str(e)
        }), 500

# ===== END TEMPORARY SETUP ENDPOINTS =====

@app.route('/list-folder', methods=['POST'])
def list_folder_items():
    data = request.get_json()
    if not data or 'folder_id' not in data:
        return jsonify({"error": "folder_id is required."}), 400
    
    folder_id = data['folder_id']
    
    try:
        access_token = get_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        
        response = requests.get(
            f"{BOX_API_BASE_URL}/folders/{folder_id}/items",
            headers=headers
        )
        
        if response.status_code == 401:
            token_data['expires_at'] = 0
            access_token = get_access_token()
            headers = {"Authorization": f"Bearer {access_token}"}
            response = requests.get(
                f"{BOX_API_BASE_URL}/folders/{folder_id}/items",
                headers=headers
            )
        
        response.raise_for_status()
        
        items = response.json().get('entries', [])
        item_list = [
            {
                "id": item.get('id'),
                "name": item.get('name'),
                "type": item.get('type')
            }
            for item in items
        ]
        return jsonify({"entries": item_list})
        
    except Exception as e:
        return jsonify({
            "error": "Failed to list folder items.",
            "details": str(e)
        }), 500

@app.route('/process-invoice', methods=['POST'])
def process_invoice_from_box():
    data = request.get_json()
    if not data or 'filename' not in data or 'parent_folder_id' not in data:
        return jsonify({
            "error": "Both 'filename' and 'parent_folder_id' are required."
        }), 400
    
    filename = data['filename']
    parent_folder_id = data['parent_folder_id']
    
    try:
        access_token = get_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        
        list_response = requests.get(
            f"{BOX_API_BASE_URL}/folders/{parent_folder_id}/items",
            headers=headers
        )
        
        if list_response.status_code == 401:
            token_data['expires_at'] = 0
            access_token = get_access_token()
            headers = {"Authorization": f"Bearer {access_token}"}
            list_response = requests.get(
                f"{BOX_API_BASE_URL}/folders/{parent_folder_id}/items",
                headers=headers
            )
        
        list_response.raise_for_status()
        
        items = list_response.json()['entries']
        file_id = next(
            (item['id'] for item in items 
             if item['type'] == 'file' and item['name'] == filename),
            None
        )
        
        if file_id is None:
            return jsonify({
                "error": f"File '{filename}' not found in folder ID '{parent_folder_id}'."
            }), 404

        download_response = requests.get(
            f"{BOX_API_BASE_URL}/files/{file_id}/content",
            headers=headers
        )
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
        ocr_files = {"file": (filename, image_content)}
        ocr_response = requests.post(
            "https://api.ocr.space/parse/image",
            data=ocr_payload,
            files=ocr_files
        )
        ocr_response.raise_for_status()
        ocr_result = ocr_response.json()
        
        if ocr_result.get('IsErroredOnProcessing'):
            return jsonify({
                "error": "OCR processing failed.",
                "details": ocr_result.get('ErrorMessage')
            }), 500
        
        extracted_text = ocr_result['ParsedResults'][0]['ParsedText']
        return jsonify({"extracted_text": extracted_text})

    except Exception as e:
        return jsonify({
            "error": "An internal server error occurred.",
            "details": str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    try:
        if not BOX_REFRESH_TOKEN:
            return jsonify({
                "status": "setup_required",
                "message": "Visit /oauth/start to set up OAuth"
            }), 200
        
        access_token = get_access_token()
        return jsonify({
            "status": "healthy",
            "token_valid": bool(access_token)
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
