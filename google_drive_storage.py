import os
import struct
import json
import pickle
import numpy as np
from io import BytesIO
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.pickle
# Using drive scope to access existing files (not just app-created files)
SCOPES = ['https://www.googleapis.com/auth/drive']

class GoogleDrivePointCloudStorage:
    def __init__(self, credentials_file='credentials.json', token_file='token.pickle'):
        """
        Initialize Google Drive storage
        
        Args:
            credentials_file: Path to OAuth credentials JSON file
            token_file: Path to store authentication token
        """
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = self._authenticate()
        self.folder_id = self._get_or_create_folder('PointClouds3D')
        self.metadata_file_id = self._get_or_create_metadata_file()
        self.metadata_cache = self._load_metadata()
    
    def _authenticate(self):
        """Handle Google Drive authentication"""
        creds = None
        
        # Check if token file exists
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
        
        # If no valid credentials, let user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save credentials for next run
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        return build('drive', 'v3', credentials=creds)
    
    def _get_or_create_folder(self, folder_name):
        """Get or create the main storage folder"""
        try:
            # Search for folder
            results = self.service.files().list(
                q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            items = results.get('files', [])
            
            if items:
                print(f"Found existing folder: {folder_name}")
                return items[0]['id']
            
            # Create folder
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = self.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            
            print(f"Created new folder: {folder_name}")
            return folder['id']
        
        except HttpError as error:
            print(f"An error occurred: {error}")
            raise
    
    def _get_or_create_metadata_file(self):
        """Get or create metadata index file"""
        try:
            # Search for metadata file
            results = self.service.files().list(
                q=f"name='metadata_index.json' and '{self.folder_id}' in parents and trashed=false",
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            items = results.get('files', [])
            
            if items:
                return items[0]['id']
            
            # Create metadata file
            metadata = {}
            buffer = BytesIO(json.dumps(metadata).encode('utf-8'))
            
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
            
            return file['id']
        
        except HttpError as error:
            print(f"An error occurred: {error}")
            raise
    
    def _load_metadata(self):
        """Load metadata index from Drive"""
        try:
            request = self.service.files().get_media(fileId=self.metadata_file_id)
            buffer = BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            buffer.seek(0)
            return json.loads(buffer.read().decode('utf-8'))
        
        except HttpError as error:
            print(f"An error occurred loading metadata: {error}")
            return {}
    
    def _save_metadata(self):
        """Save metadata index to Drive"""
        try:
            buffer = BytesIO(json.dumps(self.metadata_cache, indent=2).encode('utf-8'))
            
            media = MediaIoBaseUpload(buffer, mimetype='application/json', resumable=True)
            
            self.service.files().update(
                fileId=self.metadata_file_id,
                media_body=media
            ).execute()
        
        except HttpError as error:
            print(f"An error occurred saving metadata: {error}")
            raise
    
    def store_point_cloud(self, name, points, colors=None, normals=None, metadata=None):
        """
        Store a point cloud to Google Drive
        
        Args:
            name: Unique identifier for the point cloud
            points: numpy array of shape (N, 3) - XYZ coordinates
            colors: optional numpy array of shape (N, 3) - RGB colors (0-1 or 0-255)
            normals: optional numpy array of shape (N, 3) - normal vectors
            metadata: optional dict with additional information
        
        Returns:
            file_id: Google Drive file ID
        """
        print(f"Storing point cloud: {name}")
        
        # Prepare data dictionary
        data = {'points': points}
        if colors is not None:
            data['colors'] = colors
        if normals is not None:
            data['normals'] = normals
        
        # Serialize to compressed numpy format
        buffer = BytesIO()
        np.savez_compressed(buffer, **data)
        buffer.seek(0)
        
        # Check if file already exists
        existing_file_id = None
        if name in self.metadata_cache:
            existing_file_id = self.metadata_cache[name].get('file_id')
        
        try:
            file_metadata = {
                'name': f"{name}.npz",
                'parents': [self.folder_id]
            }
            media = MediaIoBaseUpload(
                buffer, 
                mimetype='application/octet-stream',
                resumable=True
            )
            
            if existing_file_id:
                # Update existing file
                file = self.service.files().update(
                    fileId=existing_file_id,
                    media_body=media
                ).execute()
                print(f"Updated existing file")
            else:
                # Create new file
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, size'
                ).execute()
                print(f"Created new file")
            
            file_id = file['id']
            
            # Calculate statistics
            bounds_min = points.min(axis=0).tolist()
            bounds_max = points.max(axis=0).tolist()
            centroid = points.mean(axis=0).tolist()
            
            # Update metadata cache
            self.metadata_cache[name] = {
                'file_id': file_id,
                'num_points': int(len(points)),
                'has_colors': colors is not None,
                'has_normals': normals is not None,
                'bounds_min': bounds_min,
                'bounds_max': bounds_max,
                'centroid': centroid,
                'file_size': file.get('size', 'unknown'),
                'created_at': datetime.now().isoformat(),
                'custom_metadata': metadata or {}
            }
            
            # Save metadata index
            self._save_metadata()
            
            print(f"Successfully stored {len(points)} points")
            return file_id
        
        except HttpError as error:
            print(f"An error occurred: {error}")
            raise
    
    def load_point_cloud(self, name):
        """
        Load a point cloud from Google Drive
        
        Args:
            name: Identifier of the point cloud
        
        Returns:
            dict with 'points', 'colors' (if available), 'normals' (if available), 'metadata'
        """
        print(f"Loading point cloud: {name}")
        
        if name not in self.metadata_cache:
            raise ValueError(f"Point cloud '{name}' not found")
        
        file_id = self.metadata_cache[name]['file_id']
        
        try:
            # Download file
            request = self.service.files().get_media(fileId=file_id)
            buffer = BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    print(f"Download progress: {int(status.progress() * 100)}%")
            
            # Load numpy data
            buffer.seek(0)
            loaded = np.load(buffer)
            
            result = {
                'points': loaded['points'],
                'colors': loaded['colors'] if 'colors' in loaded else None,
                'normals': loaded['normals'] if 'normals' in loaded else None,
                'metadata': self.metadata_cache[name]
            }
            
            print(f"Successfully loaded {len(result['points'])} points")
            return result
        
        except HttpError as error:
            print(f"An error occurred: {error}")
            raise
    
    def store_mesh(self, name, vertices, faces, vertex_colors=None, vertex_normals=None, metadata=None):
        """
        Store a mesh to Google Drive
        
        Args:
            name: Unique identifier for the mesh
            vertices: numpy array of shape (N, 3) - vertex coordinates
            faces: numpy array of shape (M, 3) - face indices (triangles)
            vertex_colors: optional numpy array of shape (N, 3) - vertex colors
            vertex_normals: optional numpy array of shape (N, 3) - vertex normals
            metadata: optional dict with additional information
        
        Returns:
            file_id: Google Drive file ID
        """
        print(f"Storing mesh: {name}")
        
        # Prepare data
        data = {
            'vertices': vertices,
            'faces': faces
        }
        if vertex_colors is not None:
            data['vertex_colors'] = vertex_colors
        if vertex_normals is not None:
            data['vertex_normals'] = vertex_normals
        
        # Serialize
        buffer = BytesIO()
        np.savez_compressed(buffer, **data)
        buffer.seek(0)
        
        # Check if mesh already exists
        mesh_name = f"mesh_{name}"
        existing_file_id = None
        if mesh_name in self.metadata_cache:
            existing_file_id = self.metadata_cache[mesh_name].get('file_id')
        
        try:
            file_metadata = {
                'name': f"{name}_mesh.npz",
                'parents': [self.folder_id]
            }
            media = MediaIoBaseUpload(buffer, mimetype='application/octet-stream', resumable=True)
            
            if existing_file_id:
                file = self.service.files().update(
                    fileId=existing_file_id,
                    media_body=media
                ).execute()
            else:
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, size'
                ).execute()
            
            file_id = file['id']
            
            # Update metadata
            self.metadata_cache[mesh_name] = {
                'file_id': file_id,
                'type': 'mesh',
                'num_vertices': int(len(vertices)),
                'num_faces': int(len(faces)),
                'has_colors': vertex_colors is not None,
                'has_normals': vertex_normals is not None,
                'file_size': file.get('size', 'unknown'),
                'created_at': datetime.now().isoformat(),
                'custom_metadata': metadata or {}
            }
            
            self._save_metadata()
            
            print(f"Successfully stored mesh with {len(vertices)} vertices and {len(faces)} faces")
            return file_id
        
        except HttpError as error:
            print(f"An error occurred: {error}")
            raise
    
    def load_mesh(self, name):
        """Load a mesh from Google Drive"""
        print(f"Loading mesh: {name}")
        
        mesh_name = f"mesh_{name}"
        if mesh_name not in self.metadata_cache:
            raise ValueError(f"Mesh '{name}' not found")
        
        file_id = self.metadata_cache[mesh_name]['file_id']
        
        try:
            request = self.service.files().get_media(fileId=file_id)
            buffer = BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)
            
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    print(f"Download progress: {int(status.progress() * 100)}%")
            
            buffer.seek(0)
            loaded = np.load(buffer)
            
            result = {
                'vertices': loaded['vertices'],
                'faces': loaded['faces'],
                'vertex_colors': loaded['vertex_colors'] if 'vertex_colors' in loaded else None,
                'vertex_normals': loaded['vertex_normals'] if 'vertex_normals' in loaded else None,
                'metadata': self.metadata_cache[mesh_name]
            }
            
            print(f"Successfully loaded mesh")
            return result
        
        except HttpError as error:
            print(f"An error occurred: {error}")
            raise
    
    def store_mp4_file(self, name, file_path, metadata=None):
        """
        Store an MP4 video file to Google Drive
        
        Args:
            name: Unique identifier for the video
            file_path: Path to the .mp4 file
            metadata: Optional dict with additional info
        
        Returns:
            file_id: Google Drive file ID
        """
        print(f"Storing MP4 file: {name}")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Check if file already exists
        existing_file_id = None
        if name in self.metadata_cache:
            existing_file_id = self.metadata_cache[name].get('file_id')
        
        try:
            file_size = os.path.getsize(file_path)
            print(f"File size: {file_size / (1024**2):.2f} MB")
            
            with open(file_path, 'rb') as f:
                file_metadata = {
                    'name': f"{name}.mp4",
                    'parents': [self.folder_id],
                    'mimeType': 'video/mp4'
                }
                
                # Use resumable upload for large files
                media = MediaIoBaseUpload(
                    f,
                    mimetype='video/mp4',
                    resumable=True,
                    chunksize=1024*1024  # 1MB chunks
                )
                
                if existing_file_id:
                    # Update existing file
                    print("Updating existing file...")
                    file = self.service.files().update(
                        fileId=existing_file_id,
                        media_body=media
                    ).execute()
                    print("Update complete")
                else:
                    # Create new file with progress tracking
                    print("Uploading new file...")
                    request = self.service.files().create(
                        body=file_metadata,
                        media_body=media,
                        fields='id, size'
                    )
                    
                    response = None
                    while response is None:
                        status, response = request.next_chunk()
                        if status:
                            print(f"Upload progress: {int(status.progress() * 100)}%")
                    
                    file = response
                    print("Upload complete")
                
                file_id = file['id']
                
                # Extract video metadata if available
                video_metadata = self._extract_video_metadata(file_path)
                
                # Update metadata cache
                self.metadata_cache[name] = {
                    'file_id': file_id,
                    'type': 'video',
                    'file_format': 'mp4',
                    'file_size': file.get('size', file_size),
                    'file_size_mb': file_size / (1024**2),
                    'created_at': datetime.now().isoformat(),
                    'video_info': video_metadata,
                    'custom_metadata': metadata or {}
                }
                
                # Save metadata index
                self._save_metadata()
                
                print(f"Successfully stored MP4 file ({file_size / (1024**2):.2f} MB)")
                return file_id
        
        except HttpError as error:
            print(f"An error occurred: {error}")
            raise
        except Exception as e:
            print(f"An error occurred: {e}")
            raise
    
    def _extract_video_metadata(self, file_path):
        """Extract metadata from video file (optional - requires opencv)"""
        try:
            import cv2
            
            cap = cv2.VideoCapture(file_path)
            
            if not cap.isOpened():
                return {}
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0
            
            cap.release()
            
            return {
                'fps': fps,
                'frame_count': frame_count,
                'width': width,
                'height': height,
                'duration_seconds': duration,
                'resolution': f"{width}x{height}"
            }
        
        except ImportError:
            # OpenCV not installed
            return {}
        except Exception as e:
            print(f"Could not extract video metadata: {e}")
            return {}
    
    def load_mp4_file(self, name, output_path):
        """
        Download an MP4 file from Google Drive
        
        Args:
            name: Identifier of the video
            output_path: Where to save the downloaded file
        
        Returns:
            output_path: Path to the downloaded file
        """
        print(f"Loading MP4 file: {name}")
        
        if name not in self.metadata_cache:
            raise ValueError(f"MP4 file '{name}' not found")
        
        if self.metadata_cache[name].get('type') != 'video':
            raise ValueError(f"'{name}' is not a video file")
        
        file_id = self.metadata_cache[name]['file_id']
        file_size_mb = self.metadata_cache[name].get('file_size_mb', 0)
        
        try:
            print(f"Downloading {file_size_mb:.2f} MB...")
            
            request = self.service.files().get_media(fileId=file_id)
            
            # Expand ~ in path
            output_path = os.path.expanduser(output_path)
            
            with open(output_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request, chunksize=1024*1024)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        print(f"Download progress: {int(status.progress() * 100)}%")
            
            print(f"Successfully downloaded to {output_path}")
            return output_path
        
        except HttpError as error:
            print(f"An error occurred: {error}")
            raise
    
    def get_shareable_link(self, name, anyone_can_view=True):
        """
        Create a shareable link for the file
        
        Args:
            name: Identifier of the file
            anyone_can_view: If True, anyone with link can view
        
        Returns:
            dict with various links and sharing info
        """
        if name not in self.metadata_cache:
            raise ValueError(f"File '{name}' not found")
        
        file_id = self.metadata_cache[name]['file_id']
        
        try:
            # Make file shareable if requested
            if anyone_can_view:
                permission = {
                    'type': 'anyone',
                    'role': 'reader'
                }
                self.service.permissions().create(
                    fileId=file_id,
                    body=permission
                ).execute()
                print("File is now publicly accessible via link")
            
            # Get file links
            file = self.service.files().get(
                fileId=file_id,
                fields='id, name, webViewLink, webContentLink, size'
            ).execute()
            
            return {
                'file_id': file_id,
                'name': file.get('name'),
                'size_mb': int(file.get('size', 0)) / (1024**2),
                'web_view_link': file.get('webViewLink'),
                'download_link': file.get('webContentLink'),
                'embed_link': f"https://drive.google.com/file/d/{file_id}/preview",
                'direct_link': f"https://drive.google.com/uc?export=download&id={file_id}"
            }
        
        except HttpError as error:
            print(f"An error occurred: {error}")
            raise
    
    def list_all(self):
        """List all stored point clouds, meshes, and videos"""
        return self.metadata_cache
    
    def list_point_clouds(self):
        """List only point clouds"""
        return {k: v for k, v in self.metadata_cache.items() 
                if v.get('type') != 'mesh' and v.get('type') != 'video'}
    
    def list_meshes(self):
        """List only meshes"""
        return {k: v for k, v in self.metadata_cache.items() 
                if v.get('type') == 'mesh'}
    
    def list_videos(self):
        """List all stored video files"""
        return {k: v for k, v in self.metadata_cache.items() 
                if v.get('type') == 'video'}
    
    def delete(self, name):
        """Delete a point cloud, mesh, or video"""
        # Check both regular and mesh names
        actual_name = name
        if name not in self.metadata_cache:
            mesh_name = f"mesh_{name}"
            if mesh_name in self.metadata_cache:
                actual_name = mesh_name
            else:
                raise ValueError(f"Item '{name}' not found")
        
        file_id = self.metadata_cache[actual_name]['file_id']
        
        try:
            self.service.files().delete(fileId=file_id).execute()
            del self.metadata_cache[actual_name]
            self._save_metadata()
            print(f"Deleted: {name}")
        
        except HttpError as error:
            print(f"An error occurred: {error}")
            raise
    
    def get_storage_info(self):
        """Get storage usage information"""
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
            print(f"An error occurred: {error}")
            return None
    def store_ply_file(self, name, file_path, metadata=None):
        """
        Store a PLY file to Google Drive
        
        Args:
            name: Unique identifier for the PLY file
            file_path: Path to the .ply file
            metadata: Optional dict with additional info
        
        Returns:
            file_id: Google Drive file ID
        """
        print(f"Storing PLY file: {name}")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Check if file already exists
        existing_file_id = None
        if name in self.metadata_cache:
            existing_file_id = self.metadata_cache[name].get('file_id')
        
        try:
            file_size = os.path.getsize(file_path)
            print(f"File size: {file_size / (1024**2):.2f} MB")
            
            # Extract PLY metadata
            ply_info = self._extract_ply_metadata(file_path)
            
            with open(file_path, 'rb') as f:
                file_metadata = {
                    'name': f"{name}.ply",
                    'parents': [self.folder_id],
                    'mimeType': 'application/octet-stream'
                }
                
                # Use resumable upload for large files
                from googleapiclient.http import MediaIoBaseUpload
                media = MediaIoBaseUpload(
                    f,
                    mimetype='application/octet-stream',
                    resumable=True,
                    chunksize=1024*1024  # 1MB chunks
                )
                
                if existing_file_id:
                    print("Updating existing file...")
                    file = self.service.files().update(
                        fileId=existing_file_id,
                        media_body=media
                    ).execute()
                    print("Update complete")
                else:
                    print("Uploading new file...")
                    request = self.service.files().create(
                        body=file_metadata,
                        media_body=media,
                        fields='id, size'
                    )
                    
                    response = None
                    while response is None:
                        status, response = request.next_chunk()
                        if status:
                            print(f"Upload progress: {int(status.progress() * 100)}%")
                    
                    file = response
                    print("Upload complete")
                
                file_id = file['id']
                
                # Update metadata cache
                self.metadata_cache[name] = {
                    'file_id': file_id,
                    'type': 'ply',
                    'file_format': 'ply',
                    'file_size': file.get('size', file_size),
                    'file_size_mb': file_size / (1024**2),
                    'created_at': datetime.now().isoformat(),
                    'ply_info': ply_info,
                    'custom_metadata': metadata or {}
                }
                
                # Save metadata index
                self._save_metadata()
                
                print(f"Successfully stored PLY file ({file_size / (1024**2):.2f} MB)")
                return file_id
        
        except Exception as e:
            print(f"An error occurred: {e}")
            raise

    def _extract_ply_metadata(self, file_path):
        """Extract metadata from PLY file header"""
        try:
            with open(file_path, 'rb') as f:
                # Read header
                line = f.readline().decode('ascii').strip()
                if line != 'ply':
                    return {'error': 'Not a valid PLY file'}
                
                format_type = None
                vertex_count = 0
                face_count = 0
                properties = []
                
                while True:
                    line = f.readline().decode('ascii').strip()
                    
                    if line.startswith('format'):
                        format_type = line.split()[1]
                    elif line.startswith('element vertex'):
                        vertex_count = int(line.split()[2])
                    elif line.startswith('element face'):
                        face_count = int(line.split()[2])
                    elif line.startswith('property'):
                        properties.append(' '.join(line.split()[1:]))
                    elif line == 'end_header':
                        break
                
                # Check for color properties
                has_color = any('red' in p or 'green' in p or 'blue' in p for p in properties)
                has_normals = any('nx' in p or 'ny' in p or 'nz' in p for p in properties)
                
                return {
                    'format': format_type,
                    'vertex_count': vertex_count,
                    'face_count': face_count,
                    'has_color': has_color,
                    'has_normals': has_normals,
                    'properties': properties
                }
        
        except Exception as e:
            print(f"Could not extract PLY metadata: {e}")
            return {}

    def load_ply_file(self, name, output_path):
        """
        Download a PLY file from Google Drive
        
        Args:
            name: Identifier of the PLY file
            output_path: Where to save the downloaded file
        
        Returns:
            output_path: Path to the downloaded file
        """
        print(f"Loading PLY file: {name}")
        
        if name not in self.metadata_cache:
            raise ValueError(f"PLY file '{name}' not found")
        
        if self.metadata_cache[name].get('type') != 'ply':
            raise ValueError(f"'{name}' is not a PLY file")
        
        file_id = self.metadata_cache[name]['file_id']
        file_size_mb = self.metadata_cache[name].get('file_size_mb', 0)
        
        try:
            print(f"Downloading {file_size_mb:.2f} MB...")
            
            from googleapiclient.http import MediaIoBaseDownload
            request = self.service.files().get_media(fileId=file_id)
            
            # Expand ~ in path
            output_path = os.path.expanduser(output_path)
            
            with open(output_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request, chunksize=1024*1024)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        print(f"Download progress: {int(status.progress() * 100)}%")
            
            print(f"Successfully downloaded to {output_path}")
            return output_path
        
        except Exception as e:
            print(f"An error occurred: {e}")
            raise

    def sync_existing_ply_files(self):
        """
        Scan the Google Drive folder for existing PLY files and add them to metadata cache
        This is useful for finding PLY files that were uploaded outside of this app
        """
        try:
            print("Scanning Google Drive folder for existing PLY files...")
            
            # Search for all .ply files in the folder
            query = f"'{self.folder_id}' in parents and name contains '.ply' and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, size, createdTime, modifiedTime)',
                pageSize=1000
            ).execute()
            
            files = results.get('files', [])
            new_files_count = 0
            
            for file in files:
                file_name = file['name']
                # Remove .ply extension for the key
                name = file_name.replace('.ply', '')
                
                # Skip if already in metadata cache
                if name in self.metadata_cache:
                    continue
                
                print(f"Found new PLY file: {file_name}")
                
                # Try to extract PLY metadata by downloading header
                ply_info = {}
                try:
                    # Download just the first 10KB to read the header
                    request = self.service.files().get_media(fileId=file['id'])
                    header_bytes = request.execute(num_retries=2)[:10000]
                    
                    # Parse header
                    header_str = header_bytes.decode('ascii', errors='ignore')
                    lines = header_str.split('\n')
                    
                    if lines[0].strip() == 'ply':
                        format_type = None
                        vertex_count = 0
                        face_count = 0
                        properties = []
                        
                        for line in lines:
                            line = line.strip()
                            if line.startswith('format'):
                                format_type = line.split()[1]
                            elif line.startswith('element vertex'):
                                vertex_count = int(line.split()[2])
                            elif line.startswith('element face'):
                                face_count = int(line.split()[2])
                            elif line.startswith('property'):
                                properties.append(' '.join(line.split()[1:]))
                            elif line == 'end_header':
                                break
                        
                        has_color = any('red' in p or 'green' in p or 'blue' in p for p in properties)
                        has_normals = any('nx' in p or 'ny' in p or 'nz' in p for p in properties)
                        
                        ply_info = {
                            'format': format_type,
                            'vertex_count': vertex_count,
                            'face_count': face_count,
                            'has_color': has_color,
                            'has_normals': has_normals,
                            'properties': properties
                        }
                except Exception as e:
                    print(f"Could not extract metadata for {file_name}: {e}")
                
                # Add to metadata cache
                file_size = int(file.get('size', 0))
                self.metadata_cache[name] = {
                    'file_id': file['id'],
                    'type': 'ply',
                    'file_format': 'ply',
                    'file_size': file_size,
                    'file_size_mb': file_size / (1024**2),
                    'created_at': file.get('createdTime', datetime.now().isoformat()),
                    'modified_at': file.get('modifiedTime', datetime.now().isoformat()),
                    'ply_info': ply_info,
                    'custom_metadata': {'synced_from_drive': True}
                }
                new_files_count += 1
            
            if new_files_count > 0:
                print(f"Added {new_files_count} existing PLY files to metadata cache")
                self._save_metadata()
            else:
                print("No new PLY files found")
            
            return new_files_count
            
        except HttpError as error:
            print(f"An error occurred while syncing: {error}")
            return 0

    def list_ply_files(self):
        """List all stored PLY files"""
        # First sync any existing files from Drive
        self.sync_existing_ply_files()
        
        return {k: v for k, v in self.metadata_cache.items() 
                if v.get('type') == 'ply'}

    # Usage example:
    """
    storage = GoogleDrivePointCloudStorage()

    # Upload a PLY file
    file_id = storage.store_ply_file(
        name='my_scan',
        file_path='/path/to/scan.ply',
        metadata={'scanner': 'iPhone LiDAR', 'date': '2025-01-15'}
    )

    # Get shareable link for web viewer
    link_info = storage.get_shareable_link('my_scan', anyone_can_view=True)
    print(f"Direct download: {link_info['direct_link']}")

    # Download PLY file
    storage.load_ply_file('my_scan', '/path/to/output.ply')

    # List all PLY files
    ply_files = storage.list_ply_files()
    for name, info in ply_files.items():
        print(f"{name}: {info['ply_info']['vertex_count']} vertices")
    """