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
        self.orders_metadata = []
        self._load_items_metadata()
        self._load_orders_metadata()

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

    def _load_orders_metadata(self):
        """Loads orders.txt from Google Drive and parses it as JSON. Always fetches fresh data."""
        logger.info("Attempting to load orders.txt from Google Drive...")
        
        # Always refresh metadata cache to ensure we have the latest version
        # Force clear cache first to avoid any stale data
        self.metadata_cache = {}
        self._load_metadata()
        
        # If orders.txt not found in cache, search for it directly on Drive
        orders_file_id = self.metadata_cache.get('orders.txt', {}).get('file_id')
        
        if not orders_file_id:
            logger.info("orders.txt not in metadata cache, searching directly on Google Drive...")
            try:
                # Search for existing orders.txt file in the folder
                results = self.service.files().list(
                    q=f"name='orders.txt' and parents in '{self.folder_id}' and trashed=false",
                    fields="files(id, name, modifiedTime)"
                ).execute()
                
                files = results.get('files', [])
                if files:
                    orders_file_id = files[0]['id']
                    logger.info(f"Found orders.txt directly on Drive with ID: {orders_file_id}, modified: {files[0].get('modifiedTime')}")
                    # Update cache with found file
                    self.metadata_cache['orders.txt'] = {'file_id': orders_file_id, 'type': 'metadata'}
                else:
                    logger.info("No orders.txt file found on Google Drive")
                    self.orders_metadata = []
                    return
            except Exception as e:
                logger.error(f"Error searching for orders.txt on Drive: {e}")
                self.orders_metadata = []
                return

        try:
            logger.info(f"Downloading orders.txt from Google Drive (file_id: {orders_file_id})...")
            request_obj = self.service.files().get_media(fileId=orders_file_id)
            buffer = BytesIO()
            from googleapiclient.http import MediaIoBaseDownload
            downloader = MediaIoBaseDownload(buffer, request_obj)
            
            done = False
            while not done:
                _, done = downloader.next_chunk()
            
            buffer.seek(0)
            content = buffer.read().decode('utf-8')
            
            # Parse JSON with error handling
            if content.strip():
                self.orders_metadata = json.loads(content)
            else:
                self.orders_metadata = []
            
            logger.info(f"Successfully loaded and parsed orders.txt. Found {len(self.orders_metadata)} orders.")
        except Exception as e:
            logger.error(f"Failed to load or parse orders.txt: {e}. Using empty orders list.", exc_info=True)
            self.orders_metadata = []

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

    def _save_orders_metadata(self):
        """Saves the current orders metadata to orders.txt in Google Drive."""
        logger.info("Saving orders metadata to orders.txt...")
        
        # Ensure metadata cache is fresh before checking
        if not self.metadata_cache:
            self._load_metadata()
        
        orders_file_id = self.metadata_cache.get('orders.txt', {}).get('file_id')
        
        # If not found in cache, try to find existing file by name
        if not orders_file_id:
            logger.info("orders.txt not in cache, searching for existing file by name...")
            try:
                # Search for existing orders.txt file in the folder
                results = self.service.files().list(
                    q=f"name='orders.txt' and parents in '{self.folder_id}' and trashed=false",
                    fields="files(id, name)"
                ).execute()
                
                files = results.get('files', [])
                if files:
                    orders_file_id = files[0]['id']
                    logger.info(f"Found existing orders.txt file with ID: {orders_file_id}")
                    # Update cache with found file
                    self.metadata_cache['orders.txt'] = {'file_id': orders_file_id, 'type': 'metadata'}
                    self._save_metadata()
                else:
                    logger.info("No existing orders.txt file found, will create new one")
            except Exception as e:
                logger.error(f"Error searching for existing orders.txt: {e}")
        
        from googleapiclient.http import MediaFileUpload
        
        json_content = json.dumps(self.orders_metadata, indent=2)
        
        # Save to a temporary local file first
        with open("/tmp/orders.txt", "w") as f:
            f.write(json_content)
        
        file_metadata = {'name': 'orders.txt', 'mimeType': 'text/plain'}
        media = MediaFileUpload("/tmp/orders.txt", mimetype='text/plain', resumable=True)
        
        try:
            if orders_file_id:
                # Update existing file
                logger.info(f"Updating existing orders.txt file with ID: {orders_file_id}")
                updated_file = self.service.files().update(
                    fileId=orders_file_id,
                    body=file_metadata,
                    media_body=media,
                    fields='id,name'
                ).execute()
                logger.info(f"Successfully updated existing orders.txt with ID: {updated_file.get('id')}")
            else:
                # Create new file
                logger.info("Creating new orders.txt file...")
                file_metadata['parents'] = [self.folder_id]
                created_file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id,name'
                ).execute()
                logger.info(f"Created new orders.txt with ID: {created_file.get('id')}")
                # Important: update metadata cache so we can find it next time
                self.metadata_cache['orders.txt'] = {'file_id': created_file.get('id'), 'type': 'metadata'}
                self._save_metadata() # Save the main metadata.json
                logger.info("Updated metadata cache with new orders.txt reference")
        except Exception as e:
            logger.error(f"Failed to save orders.txt to Google Drive: {e}", exc_info=True)

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


# Initialize storage - use singleton pattern
storage = None

def get_storage():
    global storage
    if storage is None:
        logger.info("Creating new storage instance (singleton)")
        # Use the new refactored class
        storage = RefactoredGoogleDriveStorage()
    else:
        logger.info("Reusing existing storage instance")
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
            'GET /api/orders', # New endpoint for orders
            'POST /api/orders', # New endpoint for saving orders
            'DELETE /api/orders/<order_id>', # New endpoint for removing orders
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

@app.route('/api/orders', methods=['GET'])
def get_orders():
    """Get all orders from orders.txt - always fetches latest version from Google Drive."""
    try:
        storage = get_storage()
        # Force refresh orders metadata from Google Drive to get latest version
        storage._load_orders_metadata()
        logger.info(f"Retrieved {len(storage.orders_metadata)} orders from storage (fresh from Google Drive).")
        return jsonify({
            'success': True,
            'orders': storage.orders_metadata,
            'count': len(storage.orders_metadata),
            'debug_info': {
                'cache_cleared': True,
                'metadata_loaded': True
            }
        })
    except Exception as e:
        logger.error(f"Error in get_orders: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/debug/orders', methods=['GET'])
def debug_orders():
    """Debug endpoint to show raw orders.txt content from Google Drive."""
    try:
        storage = get_storage()
        
        # Search for orders.txt directly on Drive
        results = storage.service.files().list(
            q=f"name='orders.txt' and parents in '{storage.folder_id}' and trashed=false",
            fields="files(id, name, modifiedTime, size)"
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            return jsonify({
                'success': True,
                'found_file': False,
                'message': 'No orders.txt file found on Google Drive'
            })
        
        orders_file = files[0]
        
        # Download raw content
        request_obj = storage.service.files().get_media(fileId=orders_file['id'])
        buffer = BytesIO()
        from googleapiclient.http import MediaIoBaseDownload
        downloader = MediaIoBaseDownload(buffer, request_obj)
        
        done = False
        while not done:
            _, done = downloader.next_chunk()
        
        buffer.seek(0)
        raw_content = buffer.read().decode('utf-8')
        
        # Try to parse as JSON
        try:
            parsed_content = json.loads(raw_content) if raw_content.strip() else []
        except json.JSONDecodeError as e:
            parsed_content = f"JSON Parse Error: {e}"
        
        return jsonify({
            'success': True,
            'found_file': True,
            'file_info': {
                'id': orders_file['id'],
                'name': orders_file['name'],
                'modifiedTime': orders_file['modifiedTime'],
                'size_bytes': orders_file['size']
            },
            'raw_content': raw_content,
            'parsed_content': parsed_content,
            'content_length': len(raw_content)
        })
        
    except Exception as e:
        logger.error(f"Error in debug_orders: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/orders', methods=['POST'])
def save_order():
    """Save a new order to orders.txt."""
    try:
        storage = get_storage()
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No order data provided.'}), 400
        
        # Add the order to the orders list
        storage.orders_metadata.append(data)
        storage._save_orders_metadata()
        
        logger.info(f"Saved new order for table {data.get('tableNumber', 'unknown')} with {len(data.get('items', []))} items.")
        return jsonify({
            'success': True, 
            'message': 'Order saved successfully.',
            'order_id': data.get('id')
        })
    
    except Exception as e:
        logger.error(f"Error in save_order: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/orders/<int:order_id>', methods=['DELETE'])
def delete_order(order_id):
    """Remove an order from orders.txt."""
    try:
        storage = get_storage()
        
        # Find and remove the order with the matching ID
        original_length = len(storage.orders_metadata)
        storage.orders_metadata = [order for order in storage.orders_metadata if order.get('id') != order_id]
        
        if len(storage.orders_metadata) == original_length:
            return jsonify({'success': False, 'error': f"Order with ID {order_id} not found."}), 404
        
        storage._save_orders_metadata()
        logger.info(f"Removed order with ID {order_id}")
        return jsonify({'success': True, 'message': f"Order {order_id} removed successfully."})
    
    except Exception as e:
        logger.error(f"Error in delete_order: {e}", exc_info=True)
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