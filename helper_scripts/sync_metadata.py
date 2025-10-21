"""
Script to sync metadata with actual files in Google Drive
This will remove orphaned entries and add missing ones
"""

from google_drive_storage import GoogleDrivePointCloudStorage

def sync_metadata():
    """Sync metadata_index.json with actual files in Google Drive"""
    
    print("="*60)
    print("Syncing Metadata with Google Drive")
    print("="*60)
    print()
    
    storage = GoogleDrivePointCloudStorage()
    
    print("Step 1: Getting all files from Google Drive folder...")
    
    # Get all files actually in the Drive folder
    try:
        results = storage.service.files().list(
            q=f"'{storage.folder_id}' in parents and trashed=false",
            spaces='drive',
            fields='files(id, name, size, mimeType, modifiedTime)'
        ).execute()
        
        actual_files = results.get('files', [])
        
        # Filter for PLY files
        ply_files_in_drive = {
            f['name'].replace('.ply', ''): f 
            for f in actual_files 
            if f['name'].endswith('.ply')
        }
        
        print(f"Found {len(ply_files_in_drive)} PLY files in Drive:")
        for name in ply_files_in_drive.keys():
            print(f"  ✓ {name}.ply")
        
    except Exception as e:
        print(f"Error accessing Drive: {e}")
        return
    
    print("\nStep 2: Checking metadata cache...")
    
    # Get all PLY files in metadata
    metadata_ply_files = {
        name: info 
        for name, info in storage.metadata_cache.items() 
        if info.get('type') == 'ply'
    }
    
    print(f"Found {len(metadata_ply_files)} PLY entries in metadata:")
    for name in metadata_ply_files.keys():
        print(f"  • {name}")
    
    print("\nStep 3: Finding discrepancies...")
    
    # Find orphaned entries (in metadata but not in Drive)
    orphaned = set(metadata_ply_files.keys()) - set(ply_files_in_drive.keys())
    
    # Find missing entries (in Drive but not in metadata)
    missing = set(ply_files_in_drive.keys()) - set(metadata_ply_files.keys())
    
    # Find mismatched file IDs
    mismatched = []
    for name in set(metadata_ply_files.keys()) & set(ply_files_in_drive.keys()):
        metadata_id = metadata_ply_files[name].get('file_id')
        drive_id = ply_files_in_drive[name]['id']
        if metadata_id != drive_id:
            mismatched.append(name)
    
    print("\n" + "="*60)
    print("RESULTS:")
    print("="*60)
    
    if orphaned:
        print(f"\n⚠️  Orphaned entries (in metadata but not in Drive): {len(orphaned)}")
        for name in orphaned:
            print(f"  ❌ {name}")
    
    if missing:
        print(f"\n⚠️  Missing entries (in Drive but not in metadata): {len(missing)}")
        for name in missing:
            print(f"  ⚠️  {name}")
    
    if mismatched:
        print(f"\n⚠️  Mismatched file IDs: {len(mismatched)}")
        for name in mismatched:
            print(f"  ⚠️  {name}")
    
    if not orphaned and not missing and not mismatched:
        print("\n✅ Everything is in sync! No issues found.")
        return
    
    print("\n" + "="*60)
    
    # Ask user what to do
    if orphaned:
        print(f"\nOrphaned entries need to be removed from metadata.")
        response = input("Remove orphaned entries? (y/n): ")
        if response.lower() == 'y':
            for name in orphaned:
                del storage.metadata_cache[name]
                print(f"  ✓ Removed {name} from metadata")
    
    if missing:
        print(f"\nMissing entries need to be added to metadata.")
        response = input("Add missing entries? (y/n): ")
        if response.lower() == 'y':
            from io import BytesIO
            from googleapiclient.http import MediaIoBaseDownload
            import tempfile
            import os
            from datetime import datetime
            
            for name in missing:
                print(f"\n  Processing {name}...")
                file_info = ply_files_in_drive[name]
                file_id = file_info['id']
                file_size = int(file_info.get('size', 0))
                
                try:
                    # Download temporarily to extract metadata
                    request = storage.service.files().get_media(fileId=file_id)
                    buffer = BytesIO()
                    downloader = MediaIoBaseDownload(buffer, request)
                    
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                    
                    buffer.seek(0)
                    
                    # Save to temp file
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.ply') as tmp:
                        tmp.write(buffer.read())
                        temp_path = tmp.name
                    
                    # Extract metadata
                    ply_info = storage._extract_ply_metadata(temp_path)
                    os.remove(temp_path)
                    
                    # Add to metadata cache
                    storage.metadata_cache[name] = {
                        'file_id': file_id,
                        'type': 'ply',
                        'file_format': 'ply',
                        'file_size': file_size,
                        'file_size_mb': file_size / (1024**2),
                        'created_at': file_info.get('modifiedTime', datetime.now().isoformat()),
                        'ply_info': ply_info,
                        'custom_metadata': {'synced': True}
                    }
                    
                    print(f"    ✓ Added {name} to metadata")
                    print(f"      Vertices: {ply_info.get('vertex_count', 'N/A')}")
                    
                except Exception as e:
                    print(f"    ✗ Error processing {name}: {e}")
    
    if mismatched:
        print(f"\nMismatched file IDs will be updated.")
        response = input("Update file IDs? (y/n): ")
        if response.lower() == 'y':
            for name in mismatched:
                old_id = storage.metadata_cache[name]['file_id']
                new_id = ply_files_in_drive[name]['id']
                storage.metadata_cache[name]['file_id'] = new_id
                print(f"  ✓ Updated {name}: {old_id[:10]}... → {new_id[:10]}...")
    
    # Save metadata
    if orphaned or missing or mismatched:
        print("\nSaving updated metadata...")
        storage._save_metadata()
        print("✅ Metadata saved successfully!")
    
    print("\n" + "="*60)
    print("Sync complete! Restart your Flask server to see changes.")
    print("="*60)

def clean_all_metadata():
    """Nuclear option: rebuild metadata from scratch"""
    print("="*60)
    print("⚠️  CLEAN ALL METADATA")
    print("="*60)
    print("\nThis will DELETE all metadata and rebuild from Drive files.")
    print("This is useful if your metadata is completely corrupted.")
    print()
    
    response = input("Are you sure? Type 'yes' to confirm: ")
    if response.lower() != 'yes':
        print("Cancelled.")
        return
    
    storage = GoogleDrivePointCloudStorage()
    
    # Clear all metadata
    storage.metadata_cache = {}
    
    print("\nCleared metadata. Rebuilding from Drive...")
    
    # Get all PLY files from Drive
    try:
        results = storage.service.files().list(
            q=f"'{storage.folder_id}' in parents and name contains '.ply' and trashed=false",
            spaces='drive',
            fields='files(id, name, size, modifiedTime)'
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            print("No PLY files found in Drive.")
            storage._save_metadata()
            return
        
        print(f"Found {len(files)} PLY files. Processing...")
        
        from io import BytesIO
        from googleapiclient.http import MediaIoBaseDownload
        import tempfile
        import os
        from datetime import datetime
        
        for file in files:
            name = file['name'].replace('.ply', '')
            file_id = file['id']
            file_size = int(file.get('size', 0))
            
            print(f"\n  Processing {name}...")
            
            try:
                # Download temporarily
                request = storage.service.files().get_media(fileId=file_id)
                buffer = BytesIO()
                downloader = MediaIoBaseDownload(buffer, request)
                
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                
                buffer.seek(0)
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.ply') as tmp:
                    tmp.write(buffer.read())
                    temp_path = tmp.name
                
                # Extract metadata
                ply_info = storage._extract_ply_metadata(temp_path)
                os.remove(temp_path)
                
                # Add to cache
                storage.metadata_cache[name] = {
                    'file_id': file_id,
                    'type': 'ply',
                    'file_format': 'ply',
                    'file_size': file_size,
                    'file_size_mb': file_size / (1024**2),
                    'created_at': file.get('modifiedTime', datetime.now().isoformat()),
                    'ply_info': ply_info,
                    'custom_metadata': {'rebuilt': True}
                }
                
                print(f"    ✓ Added")
                
            except Exception as e:
                print(f"    ✗ Error: {e}")
        
        # Save
        storage._save_metadata()
        print("\n✅ Metadata rebuilt successfully!")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("\nMetadata Sync Tool")
    print("==================\n")
    print("1. Sync metadata (recommended)")
    print("2. Clean and rebuild all metadata (nuclear option)")
    print("3. Exit")
    print()
    
    choice = input("Choose option (1/2/3): ")
    
    if choice == '1':
        sync_metadata()
    elif choice == '2':
        clean_all_metadata()
    else:
        print("Exiting.")