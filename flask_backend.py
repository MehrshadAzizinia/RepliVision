from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from google_drive_storage import GoogleDrivePointCloudStorage
from io import BytesIO
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend requests

# Initialize Google Drive storage
storage = GoogleDrivePointCloudStorage()

@app.route('/api/list-models', methods=['GET'])
def list_models():
    """
    List all .ply files from Google Drive
    Returns JSON with model information
    """
    try:
        all_items = storage.list_all()
        
        models = []
        for name, metadata in all_items.items():
            # Check if it's a PLY file (could be stored as point cloud or with .ply extension)
            if name.endswith('.ply') or metadata.get('file_format') == 'ply':
                model_info = {
                    'id': name,
                    'name': metadata.get('custom_metadata', {}).get('name', name.replace('.ply', '')),
                    'description': metadata.get('custom_metadata', {}).get('description', 'Point cloud model'),
                    'fileId': metadata['file_id'],
                    'vertices': metadata.get('num_points', 0),
                    'fileSize': format_file_size(metadata.get('file_size', 0)),
                    'createdAt': metadata.get('created_at', '')[:10] if metadata.get('created_at') else '',
                    'hasColors': metadata.get('has_colors', False),
                    'hasNormals': metadata.get('has_normals', False)
                }
                models.append(model_info)
        
        return jsonify({
            'success': True,
            'models': models,
            'count': len(models)
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/get-model', methods=['GET'])
def get_model():
    """
    Download and return a PLY file
    """
    file_id = request.args.get('fileId')
    name = request.args.get('name')
    
    if not file_id:
        return jsonify({'error': 'fileId parameter required'}), 400
    
    try:
        # Option 1: If stored as point cloud, convert to PLY format
        if name and name in storage.metadata_cache:
            metadata = storage.metadata_cache[name]
            
            # Load the point cloud
            data = storage.load_point_cloud(name)
            
            # Convert to PLY format
            ply_content = convert_to_ply(
                data['points'],
                data.get('colors'),
                data.get('normals')
            )
            
            # Return as file
            return ply_content, 200, {
                'Content-Type': 'text/plain',
                'Content-Disposition': f'inline; filename="{name}.ply"'
            }
        
        # Option 2: Direct download from Google Drive
        else:
            # Download file directly
            request_obj = storage.service.files().get_media(fileId=file_id)
            from googleapiclient.http import MediaIoBaseDownload
            
            buffer = BytesIO()
            downloader = MediaIoBaseDownload(buffer, request_obj)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            buffer.seek(0)
            ply_content = buffer.read().decode('utf-8')
            
            return ply_content, 200, {
                'Content-Type': 'text/plain',
                'Content-Disposition': 'inline; filename="model.ply"'
            }
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/upload-ply', methods=['POST'])
def upload_ply():
    """
    Upload a PLY file to Google Drive
    Expects: file in multipart/form-data
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.ply'):
        return jsonify({'error': 'File must be a .ply file'}), 400
    
    try:
        # Save temporarily
        temp_path = f'/tmp/{file.filename}'
        file.save(temp_path)
        
        # Parse PLY to extract point cloud data
        points, colors, normals = parse_ply_file(temp_path)
        
        # Get metadata from form
        name = request.form.get('name', file.filename.replace('.ply', ''))
        description = request.form.get('description', '')
        
        # Store to Google Drive
        file_id = storage.store_point_cloud(
            name=name,
            points=points,
            colors=colors,
            normals=normals,
            metadata={
                'name': name,
                'description': description,
                'file_format': 'ply',
                'original_filename': file.filename
            }
        )
        
        # Clean up temp file
        os.remove(temp_path)
        
        return jsonify({
            'success': True,
            'message': 'File uploaded successfully',
            'fileId': file_id,
            'name': name
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/delete-model', methods=['DELETE'])
def delete_model():
    """
    Delete a model from Google Drive
    """
    name = request.args.get('name')
    
    if not name:
        return jsonify({'error': 'name parameter required'}), 400
    
    try:
        storage.delete(name)
        
        return jsonify({
            'success': True,
            'message': f'Model {name} deleted successfully'
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/storage-info', methods=['GET'])
def storage_info():
    """
    Get Google Drive storage information
    """
    try:
        info = storage.get_storage_info()
        return jsonify({
            'success': True,
            'storage': info
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# Helper functions

def format_file_size(size_bytes):
    """Convert bytes to human readable format"""
    if isinstance(size_bytes, str):
        return size_bytes
    
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def convert_to_ply(points, colors=None, normals=None):
    """
    Convert numpy arrays to PLY format string
    """
    import numpy as np
    
    num_points = len(points)
    
    # Build header
    header = "ply\n"
    header += "format ascii 1.0\n"
    header += f"element vertex {num_points}\n"
    header += "property float x\n"
    header += "property float y\n"
    header += "property float z\n"
    
    if colors is not None:
        header += "property uchar red\n"
        header += "property uchar green\n"
        header += "property uchar blue\n"
    
    if normals is not None:
        header += "property float nx\n"
        header += "property float ny\n"
        header += "property float nz\n"
    
    header += "end_header\n"
    
    # Build vertex data
    lines = [header]
    
    for i in range(num_points):
        line = f"{points[i][0]} {points[i][1]} {points[i][2]}"
        
        if colors is not None:
            # Ensure colors are in 0-255 range
            r, g, b = colors[i]
            if r <= 1.0:  # Normalize if in 0-1 range
                r, g, b = int(r * 255), int(g * 255), int(b * 255)
            line += f" {int(r)} {int(g)} {int(b)}"
        
        if normals is not None:
            line += f" {normals[i][0]} {normals[i][1]} {normals[i][2]}"
        
        lines.append(line + "\n")
    
    return ''.join(lines)


def parse_ply_file(filepath):
    """
    Parse a PLY file and extract points, colors, normals
    """
    import numpy as np
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    # Parse header
    vertex_count = 0
    has_colors = False
    has_normals = False
    header_end = 0
    
    for i, line in enumerate(lines):
        if line.startswith('element vertex'):
            vertex_count = int(line.split()[2])
        elif 'property uchar red' in line or 'property float red' in line:
            has_colors = True
        elif 'property float nx' in line:
            has_normals = True
        elif line.strip() == 'end_header':
            header_end = i + 1
            break
    
    # Parse vertex data
    points = []
    colors = [] if has_colors else None
    normals = [] if has_normals else None
    
    for i in range(header_end, header_end + vertex_count):
        if i >= len(lines):
            break
        
        values = lines[i].strip().split()
        if len(values) < 3:
            continue
        
        # Extract XYZ
        points.append([float(values[0]), float(values[1]), float(values[2])])
        
        # Extract colors if present
        if has_colors and len(values) >= 6:
            colors.append([float(values[3]), float(values[4]), float(values[5])])
        
        # Extract normals if present
        if has_normals:
            offset = 6 if has_colors else 3
            if len(values) >= offset + 3:
                normals.append([float(values[offset]), float(values[offset+1]), float(values[offset+2])])
    
    points = np.array(points)
    colors = np.array(colors) if colors else None
    normals = np.array(normals) if normals else None
    
    return points, colors, normals


if __name__ == '__main__':
    print("=" * 50)
    print("PLY Viewer Backend Server")
    print("=" * 50)
    print(f"Google Drive Folder ID: {storage.folder_id}")
    print(f"Server starting on http://localhost:5000")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000)