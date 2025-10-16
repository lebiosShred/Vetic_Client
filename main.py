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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)```

#### Step 2: Push, Redeploy, and Rerun the Test

1.  **Push the Change:** Commit and push this new `main.py` file to your GitHub repository. (You do not need to change your `requirements.txt` or `Dockerfile` for this test).
2.  **Redeploy:** Go to your Render dashboard and trigger a **"Manual Deploy" -> "Deploy latest commit"**. Wait for the service to go "Live".
3.  **Run the Prompt:** Go back to Watsonx and run your prompt:
    > **extract details for Hatvet_invoice-min.png**

#### Step 3: Analyze the Result

There are only two possible outcomes now:

*   **Outcome A (Most Likely):** You see the **exact same `401 Unauthorized` error.** If this happens, it is **100% definitive proof** that the problem is with the `BOX_ACCESS_TOKEN` and its state on the Render service, because the code never attempted to contact OCR.space. The only solution in this case is the "hard reset" token refresh I outlined previously.

*   **Outcome B (Less Likely):** The agent responds with a success message like:
    > `{"status": "DIAGNOSTIC_SUCCESS", "message": "Successfully downloaded file from Box.", "file_size_bytes": 618152}`
    If you see this, it means your suspicion was correct! The Box authentication is working, and the problem was indeed in the handoff to OCR.space (likely an invalid `OCR_API_KEY`).

This test will give us our final, undeniable answer and tell us exactly which credential we need to focus on.
