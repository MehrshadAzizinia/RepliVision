from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
from google_drive_storage import GoogleDrivePointCloudStorage
from io import BytesIO
import os
import logging
import json # Added for items.txt management

app = Flask(__name__)

# Enhanced CORS configuration
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "DELETE", "OPTIONS", "PUT"], # Allow PUT for updates
        "allow_headers": ["Content-Type"]
    }
})

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure for large file uploads
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['UPLOAD_FOLDER'] = '/tmp'

# --- START: Significant changes to GoogleDrivePointCloudStorage ---
# In a real app, this would be in its own file. Here we modify it directly.

class RefactoredGoogleDriveStorage(GoogleDrivePointCloudStorage):
    
    def __init__(self):
        super().__init__()
        self.items_metadata = {}
        self._load_items_metadata()

    def _load_items_metadata(self):
        """Loads items.txt from Google Drive and parses it as JSON."""
        logger.info("Attempting to load items.txt from Google Drive...")
        items_file_id = self.metadata_cache.get('items.txt', {}).get('file_id')
        
        if not items_file_id:
            logger.warning("items.txt not found in metadata cache. Assuming it doesn't exist yet.")
            self.items_metadata = {}
            return

        try:
            request_obj = self.service.files().get_media(fileId=items_file_id)
            buffer = BytesIO()
            from googleapiclient.http import MediaIoBaseDownload
            downloader = MediaIoBaseDownload(buffer, request_obj)
            
            done = False
            while not done:
                _, done = downloader.next_chunk()
            
            buffer.seek(0)
            content = buffer.read().decode('utf-8')
            self.items_metadata = json.loads(content)
            logger.info(f"Successfully loaded and parsed items.txt. Found {len(self.items_metadata)} items.")
        except Exception as e:
            logger.error(f"Failed to load or parse items.txt: {e}. Using empty items list.", exc_info=True)
            self.items_metadata = {}

    def _save_items_metadata(self):
        """Saves the current items metadata to items.txt in Google Drive."""
        logger.info("Saving items metadata to items.txt...")
        items_file_id = self.metadata_cache.get('items.txt', {}).get('file_id')
        
        from googleapiclient.http import MediaFileUpload
        
        json_content = json.dumps(self.items_metadata, indent=2)
        
        # Save to a temporary local file first
        with open("/tmp/items.txt", "w") as f:
            f.write(json_content)
        
        file_metadata = {'name': 'items.txt', 'mimeType': 'text/plain'}
        media = MediaFileUpload("/tmp/items.txt", mimetype='text/plain', resumable=True)
        
        try:
            if items_file_id:
                # Update existing file
                updated_file = self.service.files().update(
                    fileId=items_file_id,
                    body=file_metadata,
                    media_body=media,
                    fields='id,name'
                ).execute()
                logger.info(f"Updated existing items.txt with ID: {updated_file.get('id')}")
            else:
                # Create new file
                file_metadata['parents'] = [self.folder_id]
                created_file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id,name'
                ).execute()
                logger.info(f"Created new items.txt with ID: {created_file.get('id')}")
                # Important: update metadata cache so we can find it next time
                self.metadata_cache['items.txt'] = {'file_id': created_file.get('id'), 'type': 'metadata'}
                self._save_metadata() # Save the main metadata.json
        except Exception as e:
            logger.error(f"Failed to save items.txt to Google Drive: {e}", exc_info=True)

    def list_menu_items(self):
        """Merges PLY file info with items.txt metadata."""
        ply_files = self.list_ply_files()
        menu_items = []
        
        # Ensure all PLY files have a corresponding entry in items_metadata
        # This is a safety check; upload/delete should handle this.
        needs_save = False
        for name, info in ply_files.items():
            if name not in self.items_metadata:
                logger.warning(f"PLY file '{name}' found but not in items.txt. Adding with default values.")
                self.items_metadata[name] = {'name': f"New Item: {name}", 'price': 0.00}
                needs_save = True

            item_meta = self.items_metadata.get(name, {})
            
            # Combine information
            full_item_info = {
                'base_name': name,
                'display_name': item_meta.get('name', f"Unnamed: {name}"),
                'price': item_meta.get('price', 0.00),
                'vertex_count': info.get('ply_info', {}).get('vertex_count', 0),
                'face_count': info.get('ply_info', {}).get('face_count', 0),
                'has_color': info.get('ply_info', {}).get('has_color', False),
                'file_size_mb': info.get('file_size_mb', 0),
                'created_at': info.get('created_at', ''),
                'file_id': info.get('file_id', '')
            }
            menu_items.append(full_item_info)
        
        if needs_save:
            self._save_items_metadata()
            
        menu_items.sort(key=lambda x: x['created_at'], reverse=True)
        return menu_items
        
# --- END: Changes to GoogleDrivePointCloudStorage ---


# Initialize storage
storage = None

def get_storage():
    global storage
    if storage is None:
        # Use the new refactored class
        storage = RefactoredGoogleDriveStorage()
    return storage

# REMOVED: /api/queue-command endpoint is no longer needed

@app.route('/', methods=['GET'])
def index():
    """Health check"""
    return jsonify({
        'status': 'running',
        'message': 'Google Drive PLY Menu API Server',
        'version': '2.0', # Updated version
        'endpoints': [
            'GET /',
            'GET /api/list-items', # Renamed for clarity
            'GET /api/download-ply/<name>',
            'POST /api/upload-ply',
            'DELETE /api/delete-ply/<name>',
            'POST /api/update-item/<name>', # New endpoint
            'GET /api/storage-info'
        ]
    })

@app.route('/api/list-items', methods=['GET'])
def list_items():
    """List all menu items by merging PLY files and items.txt data."""
    try:
        logger.info("Listing menu items...")
        storage = get_storage()
        menu_items = storage.list_menu_items()
        
        logger.info(f"Found {len(menu_items)} menu items.")
        
        return jsonify({
            'success': True,
            'items': menu_items,
            'count': len(menu_items)
        })
    
    except Exception as e:
        logger.error(f"Error in list_items: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/download-ply/<name>', methods=['GET'])
def download_ply(name):
    """Download a specific PLY file (unchanged)"""
    try:
        storage = get_storage()
        if name not in storage.metadata_cache:
            return jsonify({'success': False, 'error': f"PLY file '{name}' not found"}), 404
        
        file_id = storage.metadata_cache[name]['file_id']
        request_obj = storage.service.files().get_media(fileId=file_id)
        
        buffer = BytesIO()
        from googleapiclient.http import MediaIoBaseDownload
        downloader = MediaIoBaseDownload(buffer, request_obj)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                logger.info(f"Download progress for {name}: {int(status.progress() * 100)}%")
        
        buffer.seek(0)
        return send_file(buffer, mimetype='application/octet-stream', as_attachment=False, download_name=f"{name}.ply")
    
    except Exception as e:
        logger.error(f"Error in download_ply: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upload-ply', methods=['POST'])
def upload_ply():
    """Upload PLY file and add a default entry to items.txt."""
    temp_path = None
    try:
        if 'file' not in request.files: return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        name = request.form.get('name', file.filename.replace('.ply', ''))
        
        if not file.filename.endswith('.ply'): return jsonify({'success': False, 'error': 'File must be a PLY file'}), 400

        # Save to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ply') as tmp:
            temp_path = tmp.name
            file.save(temp_path)

        storage = get_storage()
        
        # Store the PLY file
        file_id = storage.store_ply_file(name=name, file_path=temp_path, metadata={'uploaded_via': 'web_api'})
        
        # --- NEW LOGIC: Add default entry to items.txt if it doesn't exist ---
        if name not in storage.items_metadata:
            storage.items_metadata[name] = {
                'name': f"New Item: {name}",
                'price': 0.00
            }
            storage._save_items_metadata()
            logger.info(f"Added default entry for '{name}' to items.txt.")
        
        return jsonify({ 'success': True, 'name': name, 'file_id': file_id, 'message': 'File uploaded and menu item created.' })
    
    except Exception as e:
        logger.error(f"Error in upload_ply: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if temp_path and os.path.exists(temp_path): os.remove(temp_path)

@app.route('/api/delete-ply/<name>', methods=['DELETE'])
def delete_ply(name):
    """Delete a PLY file and its corresponding entry in items.txt."""
    try:
        storage = get_storage()
        
        if name not in storage.metadata_cache:
            return jsonify({'success': False, 'error': f"PLY file '{name}' not found"}), 404
        
        file_id = storage.metadata_cache[name].get('file_id')
        storage.service.files().delete(fileId=file_id).execute()
        del storage.metadata_cache[name]
        storage._save_metadata()
        logger.info(f"Deleted PLY file '{name}' from Drive and metadata.")

        # --- NEW LOGIC: Remove from items.txt ---
        if name in storage.items_metadata:
            del storage.items_metadata[name]
            storage._save_items_metadata()
            logger.info(f"Removed entry for '{name}' from items.txt.")
        
        return jsonify({'success': True, 'message': f"Successfully deleted item {name}."})
    
    except Exception as e:
        logger.error(f"Error in delete_ply: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/update-item/<name>', methods=['POST'])
def update_item(name):
    """Updates the display name and price for an item in items.txt."""
    try:
        storage = get_storage()
        data = request.get_json()

        if name not in storage.items_metadata:
            return jsonify({'success': False, 'error': f"Item '{name}' not found in items metadata."}), 404

        new_display_name = data.get('name')
        new_price = data.get('price')

        if new_display_name is None or new_price is None:
            return jsonify({'success': False, 'error': 'Both "name" and "price" are required.'}), 400

        storage.items_metadata[name]['name'] = str(new_display_name)
        storage.items_metadata[name]['price'] = float(new_price)
        storage._save_items_metadata()
        
        logger.info(f"Updated item '{name}' with new name: '{new_display_name}' and price: {new_price}")
        return jsonify({'success': True, 'message': f"Item '{name}' updated successfully."})
    
    except Exception as e:
        logger.error(f"Error in update_item: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/storage-info', methods=['GET'])
def storage_info():
    """Get Google Drive storage info (unchanged)"""
    try:
        storage = get_storage()
        info = storage.get_storage_info()
        return jsonify({'success': True, 'storage': info})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    print("🚀 Google Drive PLY Menu API Server v2.0")
    app.run(debug=True, host='0.0.0.0', port=8000)