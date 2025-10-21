"""
Script to check PLY file format and convert binary to ASCII if needed
"""

import os
import struct

def check_ply_format(file_path):
    """Check if PLY file is ASCII or binary"""
    with open(file_path, 'rb') as f:
        # Read first few lines
        header = []
        line = b''
        while True:
            char = f.read(1)
            if not char:
                break
            if char == b'\n':
                header.append(line.decode('ascii', errors='ignore'))
                line = b''
                if header[-1] == 'end_header':
                    break
            else:
                line += char
        
        # Check format
        format_line = [l for l in header if l.startswith('format')]
        if format_line:
            format_type = format_line[0].split()[1]
            print(f"File: {file_path}")
            print(f"Format: {format_type}")
            
            if format_type == 'ascii':
                print("✅ ASCII format - compatible with web viewer")
                return True
            else:
                print("⚠️  Binary format - needs conversion for web viewer")
                return False
        else:
            print("❌ Invalid PLY file - no format line found")
            return None

def convert_binary_to_ascii(input_file, output_file=None):
    """Convert binary PLY to ASCII PLY"""
    if output_file is None:
        output_file = input_file.replace('.ply', '_ascii.ply')
    
    try:
        # Try using trimesh (most reliable)
        import trimesh
        mesh = trimesh.load(input_file)
        
        # Export as ASCII PLY
        with open(output_file, 'w') as f:
            f.write('ply\n')
            f.write('format ascii 1.0\n')
            f.write(f'element vertex {len(mesh.vertices)}\n')
            f.write('property float x\n')
            f.write('property float y\n')
            f.write('property float z\n')
            
            if mesh.visual.vertex_colors is not None:
                f.write('property uchar red\n')
                f.write('property uchar green\n')
                f.write('property uchar blue\n')
                f.write('property uchar alpha\n')
            
            if hasattr(mesh, 'faces') and len(mesh.faces) > 0:
                f.write(f'element face {len(mesh.faces)}\n')
                f.write('property list uchar int vertex_indices\n')
            
            f.write('end_header\n')
            
            # Write vertices
            for i, v in enumerate(mesh.vertices):
                if mesh.visual.vertex_colors is not None:
                    c = mesh.visual.vertex_colors[i]
                    f.write(f'{v[0]} {v[1]} {v[2]} {c[0]} {c[1]} {c[2]} {c[3]}\n')
                else:
                    f.write(f'{v[0]} {v[1]} {v[2]}\n')
            
            # Write faces
            if hasattr(mesh, 'faces') and len(mesh.faces) > 0:
                for face in mesh.faces:
                    f.write(f'3 {face[0]} {face[1]} {face[2]}\n')
        
        print(f"✅ Converted to ASCII: {output_file}")
        return output_file
        
    except ImportError:
        print("❌ trimesh not installed. Install with: pip install trimesh")
        print("\nAlternatively, you can use MeshLab or CloudCompare to convert:")
        print("1. Open file in MeshLab or CloudCompare")
        print("2. Export/Save as PLY")
        print("3. Choose 'ASCII' format in export options")
        return None
    except Exception as e:
        print(f"❌ Conversion failed: {e}")
        return None

def check_all_ply_in_folder(folder_path):
    """Check all PLY files in a folder"""
    ply_files = [f for f in os.listdir(folder_path) if f.endswith('.ply')]
    
    if not ply_files:
        print(f"No PLY files found in {folder_path}")
        return
    
    print(f"Found {len(ply_files)} PLY files\n")
    print("="*60)
    
    binary_files = []
    
    for ply_file in ply_files:
        file_path = os.path.join(folder_path, ply_file)
        is_ascii = check_ply_format(file_path)
        print()
        
        if is_ascii == False:
            binary_files.append(file_path)
    
    if binary_files:
        print("="*60)
        print(f"\n⚠️  Found {len(binary_files)} binary PLY files")
        print("These need to be converted to ASCII for the web viewer.\n")
        
        response = input("Convert them now? (y/n): ")
        if response.lower() == 'y':
            for file_path in binary_files:
                convert_binary_to_ascii(file_path)

def check_drive_files():
    """Check PLY files that are in Google Drive"""
    from google_drive_storage import GoogleDrivePointCloudStorage
    import tempfile
    
    storage = GoogleDrivePointCloudStorage()
    ply_files = storage.list_ply_files()
    
    if not ply_files:
        print("No PLY files found in Google Drive")
        return
    
    print(f"Found {len(ply_files)} PLY files in Google Drive\n")
    print("="*60)
    
    binary_files = []
    
    for name, info in ply_files.items():
        print(f"\nChecking: {name}.ply")
        
        # Download to temp file
        with tempfile.NamedTemporaryFile(suffix='.ply', delete=False) as tmp:
            temp_path = tmp.name
        
        try:
            storage.load_ply_file(name, temp_path)
            is_ascii = check_ply_format(temp_path)
            
            if is_ascii == False:
                binary_files.append((name, temp_path))
            else:
                os.remove(temp_path)
        except Exception as e:
            print(f"Error checking file: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    if binary_files:
        print("\n" + "="*60)
        print(f"⚠️  Found {len(binary_files)} binary PLY files in Drive")
        print("These need to be converted to ASCII for the web viewer.\n")
        
        response = input("Convert and re-upload? (y/n): ")
        if response.lower() == 'y':
            for name, temp_path in binary_files:
                print(f"\nConverting {name}...")
                ascii_path = convert_binary_to_ascii(temp_path)
                
                if ascii_path:
                    print(f"Re-uploading as ASCII...")
                    storage.store_ply_file(name, ascii_path, metadata={'format': 'ascii', 'converted': True})
                    print(f"✅ Done: {name}")
                    os.remove(ascii_path)
                
                os.remove(temp_path)

if __name__ == "__main__":
    print("="*60)
    print("PLY Format Checker & Converter")
    print("="*60)
    print("\nWhat would you like to check?")
    print("1. Single PLY file")
    print("2. All PLY files in a folder")
    print("3. PLY files in Google Drive")
    print()
    
    choice = input("Enter choice (1/2/3): ")
    
    if choice == '1':
        file_path = input("Enter path to PLY file: ")
        if os.path.exists(file_path):
            is_ascii = check_ply_format(file_path)
            if is_ascii == False:
                response = input("\nConvert to ASCII? (y/n): ")
                if response.lower() == 'y':
                    convert_binary_to_ascii(file_path)
        else:
            print(f"File not found: {file_path}")
    
    elif choice == '2':
        folder_path = input("Enter folder path: ")
        if os.path.exists(folder_path):
            check_all_ply_in_folder(folder_path)
        else:
            print(f"Folder not found: {folder_path}")
    
    elif choice == '3':
        try:
            check_drive_files()
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
    
    else:
        print("Invalid choice")