#!/usr/bin/env python3
"""
Test script to write a test line into command_queue.txt in Google Drive
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app_minimal import SimpleGoogleDriveStorage
from io import BytesIO
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

def write_test_command():
    storage = SimpleGoogleDriveStorage()
    test_command = "run_example --data_path /content/drive/MyDrive/Pi3/examples/parkour_long.mp4 --save_path /content/drive/MyDrive/PointClouds3D/commandtest.ply --interval 40"
    
    # Get existing file or create new
    command_queue_file_id = storage.metadata.get('command_queue.txt', {}).get('file_id')
    
    # Load existing content
    content = ""
    if command_queue_file_id:
        request = storage.service.files().get_media(fileId=command_queue_file_id)
        buffer = BytesIO()
        MediaIoBaseDownload(buffer, request).next_chunk()
        content = buffer.read().decode('utf-8')
    
    # Append new command
    content += test_command + '\n'
    
    # Save back to Google Drive
    buffer = BytesIO(content.encode('utf-8'))
    file_metadata = {'name': 'command_queue.txt', 'mimeType': 'text/plain'}
    media = MediaIoBaseUpload(buffer, mimetype='text/plain')
    
    if command_queue_file_id:
        storage.service.files().update(fileId=command_queue_file_id, body=file_metadata, media_body=media).execute()
    else:
        file_metadata['parents'] = [storage.folder_id]
        file = storage.service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        storage.metadata['command_queue.txt'] = {'file_id': file.get('id'), 'type': 'command_queue'}
        storage._save_metadata()
    
    print(f"Command written to command_queue.txt")

if __name__ == "__main__":
    write_test_command()
