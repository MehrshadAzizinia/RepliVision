from flask import Flask, jsonify, send_file, request
from flask_cors import CORS
from google_drive_storage import GoogleDrivePointCloudStorage
from io import BytesIO
import os

app = Flask(__name__)
CORS(app)

# Configure for large file uploads
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max
app.config['UPLOAD_FOLDER'] = '/tmp'

# Initialize storage
storage = None

def get_storage():
    global storage
    if storage is None:
        storage = GoogleDrivePointCloudStorage()
    return storage

@app.route('/', methods=['GET'])
def index():
    """Health check"""
    return jsonify({
        'status': 'running',
        'message': 'Google Drive PLY API Server'
    })

@app.route('/api/list-ply-files', methods=['GET'])
def list_ply_files():
    """List all PLY files in Google Drive"""
    try:
        storage = get_storage()
        ply_files = storage.list_ply_files()
        
        files_list = []
        for name, info in ply_files.items():
            files_list.append({
                'name': name,
                'display_name': f"{name}.ply",
                'vertex_count': info.get('ply_info', {}).get('vertex_count', 0),
                'face_count': info.get('ply_info', {}).get('face_count', 0),
                'has_color': info.get('ply_info', {}).get('has_color', False),
                'has_normals': info.get('ply_info', {}).get('has_normals', False),
                'file_size_mb': info.get('file_size_mb', 0),
                'created_at': info.get('created_at', ''),
                'file_id': info.get('file_id', '')
            })
        
        files_list.sort(key=lambda x: x['created_at'], reverse=True)
        
        return jsonify({
            'success': True,
            'files': files_list,
            'count': len(files_list)
        })
    
    except Exception as e:
        print(f"Error in list_ply_files: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/download-ply/<name>', methods=['GET'])
def download_ply(name):
    """Download a specific PLY file"""
    try:
        print(f"Download request for: {name}")
        storage = get_storage()
        
        if name not in storage.metadata_cache:
            return jsonify({'success': False, 'error': f"PLY file '{name}' not found"}), 404
        
        if storage.metadata_cache[name].get('type') != 'ply':
            return jsonify({'success': False, 'error': f"'{name}' is not a PLY file"}), 400
        
        file_id = storage.metadata_cache[name]['file_id']
        request_obj = storage.service.files().get_media(fileId=file_id)
        
        buffer = BytesIO()
        from googleapiclient.http import MediaIoBaseDownload
        downloader = MediaIoBaseDownload(buffer, request_obj)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"Download progress: {int(status.progress() * 100)}%")
        
        buffer.seek(0)
        print(f"Download complete: {buffer.getbuffer().nbytes} bytes")
        
        return send_file(
            buffer,
            mimetype='application/octet-stream',
            as_attachment=False,
            download_name=f"{name}.ply"
        )
    
    except Exception as e:
        print(f"Error in download_ply: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/upload-ply', methods=['POST'])
def upload_ply():
    """Upload PLY file - stores as-is"""
    temp_path = None
    
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        name = request.form.get('name', file.filename.replace('.ply', ''))
        
        if not file.filename.endswith('.ply'):
            return jsonify({'success': False, 'error': 'File must be a PLY file'}), 400
        
        print(f"Receiving file: {file.filename}")
        
        # Stream to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ply') as tmp:
            temp_path = tmp.name
            chunk_size = 1024 * 1024  # 1MB chunks
            bytes_written = 0
            
            while True:
                chunk = file.stream.read(chunk_size)
                if not chunk:
                    break
                tmp.write(chunk)
                bytes_written += len(chunk)
            
            print(f"Saved {bytes_written / (1024**2):.2f} MB to temp file")
        
        # Upload to Drive as-is (no conversion)
        print("Uploading to Google Drive...")
        storage = get_storage()
        file_id = storage.store_ply_file(
            name=name,
            file_path=temp_path,
            metadata={'uploaded_via': 'web_api'}
        )
        
        ply_info = storage.metadata_cache[name].get('ply_info', {})
        
        print(f"Upload complete: {name}")
        
        return jsonify({
            'success': True,
            'name': name,
            'file_id': file_id,
            'message': 'File uploaded successfully',
            'vertices': ply_info.get('vertex_count', 0),
            'faces': ply_info.get('face_count', 0)
        })
    
    except Exception as e:
        print(f"Error in upload_ply: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
    
    finally:
        # Cleanup
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

@app.route('/api/delete-ply/<name>', methods=['DELETE'])
def delete_ply(name):
    """Delete a PLY file"""
    try:
        print(f"Delete request for: {name}")
        storage = get_storage()
        
        if name not in storage.metadata_cache:
            return jsonify({'success': False, 'error': f"PLY file '{name}' not found"}), 404
        
        if storage.metadata_cache[name].get('type') != 'ply':
            return jsonify({'success': False, 'error': f"'{name}' is not a PLY file"}), 400
        
        file_id = storage.metadata_cache[name].get('file_id')
        
        try:
            storage.service.files().delete(fileId=file_id).execute()
            print(f"Deleted from Drive: {file_id}")
        except Exception as drive_error:
            print(f"Warning: Could not delete from Drive: {drive_error}")
        
        # Remove from metadata
        del storage.metadata_cache[name]
        storage._save_metadata()
        
        print(f"Successfully deleted: {name}")
        
        return jsonify({'success': True, 'message': f"Successfully deleted {name}.ply"})
    
    except Exception as e:
        print(f"Error in delete_ply: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/storage-info', methods=['GET'])
def storage_info():
    """Get Google Drive storage info"""
    try:
        storage = get_storage()
        info = storage.get_storage_info()
        return jsonify({'success': True, 'storage': info})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    print("="*60)
    print("🚀 Google Drive PLY API Server")
    print("="*60)
    print("\n📍 Endpoints:")
    print("  GET    /api/list-ply-files")
    print("  GET    /api/download-ply/<name>")
    print("  POST   /api/upload-ply")
    print("  DELETE /api/delete-ply/<name>")
    print("  GET    /api/storage-info")
    print("\n💡 Server running on http://localhost:8000")
    print("   Viewer supports both ASCII and binary PLY")
    print("   Press Ctrl+C to stop\n")
    print("="*60)
    
    app.run(debug=True, host='0.0.0.0', port=8000)