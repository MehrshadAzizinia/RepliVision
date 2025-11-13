from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
from io import BytesIO
import os
import logging
import json
import pickle
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError

# Google Drive configuration
SCOPES = ['https://www.googleapis.com/auth/drive']

app = Flask(__name__)

# CORS configuration
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure for file uploads
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max

class SimpleGoogleDriveStorage:
    def __init__(self, credentials_file='credentials.json', token_file='token.pickle'):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.folder_name = 'PointClouds3D'
        self.service = self._authenticate()
        self.folder_id = self._get_or_create_folder(self.folder_name)
        self.metadata = self._load_metadata()
        self.items_metadata = {}
        self.orders_metadata = []
        self._initialize_metadata()
    
    def _authenticate(self):
        creds = None
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        return build('drive', 'v3', credentials=creds)
    
    def _get_or_create_folder(self, folder_name):
        try:
            results = self.service.files().list(
                q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            items = results.get('files', [])
            if items:
                return items[0]['id']
            
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            return folder['id']
        
        except HttpError as error:
            logger.error(f"Error creating folder: {error}")
            raise
    
    def _load_metadata(self):
        try:
            # Try to find existing metadata file
            results = self.service.files().list(
                q=f"name='metadata_index.json' and '{self.folder_id}' in parents and trashed=false",
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            items = results.get('files', [])
            if items:
                file_id = items[0]['id']
                request = self.service.files().get_media(fileId=file_id)
                buffer = BytesIO()
                downloader = MediaIoBaseDownload(buffer, request)
                
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                
                buffer.seek(0)
                return json.loads(buffer.read().decode('utf-8'))
            else:
                return {}
        
        except HttpError as error:
            logger.error(f"Error loading metadata: {error}")
            return {}
    
    def _save_metadata(self):
        try:
            # Find or create metadata file
            results = self.service.files().list(
                q=f"name='metadata_index.json' and '{self.folder_id}' in parents and trashed=false",
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            items = results.get('files', [])
            if items:
                file_id = items[0]['id']
                buffer = BytesIO(json.dumps(self.metadata, indent=2).encode('utf-8'))
                media = MediaIoBaseUpload(buffer, mimetype='application/json')
                
                self.service.files().update(
                    fileId=file_id,
                    media_body=media
                ).execute()
            else:
                buffer = BytesIO(json.dumps(self.metadata, indent=2).encode('utf-8'))
                file_metadata = {
                    'name': 'metadata_index.json',
                    'parents': [self.folder_id]
                }
                media = MediaIoBaseUpload(buffer, mimetype='application/json')
                
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
        
        except HttpError as error:
            logger.error(f"Error saving metadata: {error}")
            raise
    
    def _initialize_metadata(self):
        # Load items metadata
        items_file_id = self.metadata.get('items.txt', {}).get('file_id')
        if items_file_id:
            try:
                request = self.service.files().get_media(fileId=items_file_id)
                buffer = BytesIO()
                downloader = MediaIoBaseDownload(buffer, request)
                
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                
                buffer.seek(0)
                content = buffer.read().decode('utf-8')
                self.items_metadata = json.loads(content) if content.strip() else {}
            except Exception as e:
                logger.error(f"Failed to load items metadata: {e}")
                self.items_metadata = {}
        
        # Load orders metadata
        orders_file_id = self.metadata.get('orders.txt', {}).get('file_id')
        if orders_file_id:
            try:
                request = self.service.files().get_media(fileId=orders_file_id)
                buffer = BytesIO()
                downloader = MediaIoBaseDownload(buffer, request)
                
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                
                buffer.seek(0)
                content = buffer.read().decode('utf-8')
                self.orders_metadata = json.loads(content) if content.strip() else []
            except Exception as e:
                logger.error(f"Failed to load orders metadata: {e}")
                self.orders_metadata = []
    
    def _save_items_metadata(self):
        json_content = json.dumps(self.items_metadata, indent=2)
        buffer = BytesIO(json_content.encode('utf-8'))
        
        items_file_id = self.metadata.get('items.txt', {}).get('file_id')
        file_metadata = {'name': 'items.txt', 'mimeType': 'text/plain'}
        media = MediaIoBaseUpload(buffer, mimetype='text/plain')
        
        try:
            if items_file_id:
                self.service.files().update(
                    fileId=items_file_id,
                    body=file_metadata,
                    media_body=media
                ).execute()
            else:
                file_metadata['parents'] = [self.folder_id]
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                self.metadata['items.txt'] = {'file_id': file.get('id'), 'type': 'metadata'}
                self._save_metadata()
        except Exception as e:
            logger.error(f"Failed to save items metadata: {e}")
    
    def _save_orders_metadata(self):
        json_content = json.dumps(self.orders_metadata, indent=2)
        buffer = BytesIO(json_content.encode('utf-8'))
        
        orders_file_id = self.metadata.get('orders.txt', {}).get('file_id')
        file_metadata = {'name': 'orders.txt', 'mimeType': 'text/plain'}
        media = MediaIoBaseUpload(buffer, mimetype='text/plain')
        
        try:
            if orders_file_id:
                self.service.files().update(
                    fileId=orders_file_id,
                    body=file_metadata,
                    media_body=media
                ).execute()
            else:
                file_metadata['parents'] = [self.folder_id]
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                self.metadata['orders.txt'] = {'file_id': file.get('id'), 'type': 'metadata'}
                self._save_metadata()
        except Exception as e:
            logger.error(f"Failed to save orders metadata: {e}")
    
    def list_menu_items(self):
        # Get all PLY files
        try:
            query = f"'{self.folder_id}' in parents and name contains '.ply' and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, size, createdTime)',
                pageSize=1000
            ).execute()
            
            files = results.get('files', [])
            menu_items = []
            
            for file in files:
                file_name = file['name']
                name = file_name.replace('.ply', '')
                
                # Get item metadata or use defaults
                item_meta = self.items_metadata.get(name, {'name': f"Item: {name}", 'price': 0.00, 'category': 'Uncategorized', 'description': '', 'available': True})
                
                file_size = int(file.get('size', 0))
                menu_items.append({
                    'base_name': name,
                    'display_name': item_meta.get('name', f"Unnamed: {name}"),
                    'price': item_meta.get('price', 0.00),
                    'category': item_meta.get('category', 'Uncategorized'),
                    'description': item_meta.get('description', ''),
                    'available': item_meta.get('available', True),
                    'vertex_count': 0,  # Simplified - not extracting PLY metadata
                    'face_count': 0,
                    'has_color': False,
                    'file_size_mb': file_size / (1024**2),
                    'created_at': file.get('createdTime', ''),
                    'file_id': file['id']
                })
            
            # Sort by creation time
            menu_items.sort(key=lambda x: x['created_at'], reverse=True)
            return menu_items
            
        except HttpError as error:
            logger.error(f"Error listing files: {error}")
            return []
    
    def store_ply_file(self, name, file_path, metadata=None):
        try:
            with open(file_path, 'rb') as f:
                file_metadata = {
                    'name': f"{name}.ply",
                    'parents': [self.folder_id],
                    'mimeType': 'application/octet-stream'
                }
                
                media = MediaIoBaseUpload(f, mimetype='application/octet-stream')
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                
                # Update metadata
                self.metadata[name] = {
                    'file_id': file['id'],
                    'type': 'ply',
                    'created_at': datetime.now().isoformat(),
                    'custom_metadata': metadata or {}
                }
                self._save_metadata()
                
                # Add to items metadata if not exists
                if name not in self.items_metadata:
                    self.items_metadata[name] = {
                        'name': f"New Item: {name}",
                        'price': 0.00,
                        'category': 'Uncategorized',
                        'description': '',
                        'available': True
                    }
                    self._save_items_metadata()
                
                return file['id']
        
        except Exception as e:
            logger.error(f"Error storing file: {e}")
            raise
    
    def delete_ply_file(self, name):
        if name in self.metadata:
            file_id = self.metadata[name]['file_id']
            self.service.files().delete(fileId=file_id).execute()
            del self.metadata[name]
            self._save_metadata()
            
            # Remove from items metadata
            if name in self.items_metadata:
                del self.items_metadata[name]
                self._save_items_metadata()
    
    def get_storage_info(self):
        try:
            about = self.service.about().get(fields='storageQuota').execute()
            quota = about['storageQuota']
            
            total = int(quota.get('limit', 0))
            used = int(quota.get('usage', 0))
            
            return {
                'total_gb': total / (1024**3),
                'used_gb': used / (1024**3),
                'available_gb': (total - used) / (1024**3),
                'used_percentage': (used / total * 100) if total > 0 else 0
            }
        except HttpError as error:
            logger.error(f"Error getting storage info: {error}")
            return None

# Global storage instance
storage = SimpleGoogleDriveStorage()

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'status': 'running',
        'message': 'Simple Google Drive PLY Menu API',
        'version': '1.0'
    })

@app.route('/api/list-items', methods=['GET'])
def list_items():
    try:
        menu_items = storage.list_menu_items()
        return jsonify({
            'success': True,
            'items': menu_items,
            'count': len(menu_items)
        })
    except Exception as e:
        logger.error(f"Error in list_items: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/download-ply/<name>', methods=['GET'])
def download_ply(name):
    try:
        if name not in storage.metadata:
            return jsonify({'success': False, 'error': f"PLY file '{name}' not found"}), 404
        
        file_id = storage.metadata[name]['file_id']
        request_obj = storage.service.files().get_media(fileId=file_id)
        
        buffer = BytesIO()
        downloader = MediaIoBaseDownload(buffer, request_obj)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        buffer.seek(0)
        
        return send_file(
            buffer,
            mimetype='application/octet-stream',
            as_attachment=False,
            download_name=f"{name}.ply"
        )
    
    except Exception as e:
        logger.error(f"Error in download_ply: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upload-ply', methods=['POST'])
def upload_ply():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        name = request.form.get('name', file.filename.replace('.ply', ''))
        
        if not file.filename.endswith('.ply'):
            return jsonify({'success': False, 'error': 'File must be a PLY file'}), 400

        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ply') as tmp:
            file.save(tmp.name)
            storage.store_ply_file(name=name, file_path=tmp.name, metadata={'uploaded_via': 'web_api'})
            os.unlink(tmp.name)
        
        return jsonify({
            'success': True,
            'name': name,
            'message': 'File uploaded successfully'
        })
    
    except Exception as e:
        logger.error(f"Error in upload_ply: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete-ply/<name>', methods=['DELETE'])
def delete_ply(name):
    try:
        if name not in storage.metadata:
            return jsonify({'success': False, 'error': f"PLY file '{name}' not found"}), 404
        
        storage.delete_ply_file(name)
        return jsonify({'success': True, 'message': f"Successfully deleted item {name}."})
    
    except Exception as e:
        logger.error(f"Error in delete_ply: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/update-item/<name>', methods=['POST'])
def update_item(name):
    try:
        data = request.get_json()
        if name not in storage.items_metadata:
            return jsonify({'success': False, 'error': f"Item '{name}' not found."}), 404

        new_display_name = data.get('name')
        new_price = data.get('price')
        new_category = data.get('category')
        new_description = data.get('description', '')
        new_available = data.get('available', True)

        if new_display_name is None or new_price is None:
            return jsonify({'success': False, 'error': 'Both "name" and "price" are required.'}), 400

        storage.items_metadata[name]['name'] = str(new_display_name)
        storage.items_metadata[name]['price'] = float(new_price)
        if new_category is not None:
            storage.items_metadata[name]['category'] = str(new_category)
        if new_description is not None:
            storage.items_metadata[name]['description'] = str(new_description)
        if new_available is not None:
            storage.items_metadata[name]['available'] = bool(new_available)
        storage._save_items_metadata()
        
        logger.info(f"Updated item '{name}' with new name: '{new_display_name}' and price: {new_price}")
        return jsonify({'success': True, 'message': f"Item '{name}' updated successfully."})
    
    except Exception as e:
        logger.error(f"Error in update_item: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/orders', methods=['GET'])
def get_orders():
    try:
        return jsonify({
            'success': True,
            'orders': storage.orders_metadata,
            'count': len(storage.orders_metadata)
        })
    except Exception as e:
        logger.error(f"Error in get_orders: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/orders', methods=['POST'])
def save_order():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No order data provided.'}), 400
        
        storage.orders_metadata.append(data)
        storage._save_orders_metadata()
        
        logger.info(f"Saved new order for table {data.get('tableNumber', 'unknown')}")
        return jsonify({
            'success': True,
            'message': 'Order saved successfully.',
            'order_id': data.get('id')
        })
    
    except Exception as e:
        logger.error(f"Error in save_order: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/orders/<int:order_id>', methods=['DELETE'])
def delete_order(order_id):
    try:
        original_length = len(storage.orders_metadata)
        storage.orders_metadata = [order for order in storage.orders_metadata if order.get('id') != order_id]
        
        if len(storage.orders_metadata) == original_length:
            return jsonify({'success': False, 'error': f"Order with ID {order_id} not found."}), 404
        
        storage._save_orders_metadata()
        logger.info(f"Removed order with ID {order_id}")
        return jsonify({'success': True, 'message': f"Order {order_id} removed successfully."})
    
    except Exception as e:
        logger.error(f"Error in delete_order: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/storage-info', methods=['GET'])
def storage_info():
    try:
        info = storage.get_storage_info()
        return jsonify({
            'success': True,
            'storage': info
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    print("🚀 Simple Google Drive PLY Menu API Server")
    app.run(debug=True, host='0.0.0.0', port=8000)
