# full_test.py
from google_drive_storage import GoogleDrivePointCloudStorage
import numpy as np

print("=" * 50)
print("Google Drive Storage - Complete Test")
print("=" * 50)

# Initialize storage
print("\n1. Initializing Google Drive Storage...")
storage = GoogleDrivePointCloudStorage()

# Test 1: Store a point cloud
print("\n2. Creating and storing a point cloud...")
points = np.random.rand(5000, 3) * 100
colors = np.random.rand(5000, 3)
storage.store_point_cloud(
    'test_pointcloud',
    points,
    colors=colors,
    metadata={'test': 'full_test', 'source': 'Mac'}
)

# Test 2: Store a mesh
print("\n3. Creating and storing a mesh...")
vertices = np.random.rand(200, 3) * 10
faces = np.random.randint(0, 200, size=(100, 3))
storage.store_mesh(
    'test_mesh',
    vertices,
    faces,
    metadata={'test': 'full_test'}
)

# Test 3: List all items
print("\n4. Listing all stored items...")
all_items = storage.list_all()
print(f"\nTotal items stored: {len(all_items)}")
for name, info in all_items.items():
    print(f"\n  {name}:")
    if 'num_points' in info:
        print(f"    Type: Point Cloud")
        print(f"    Points: {info['num_points']}")
    elif info.get('type') == 'mesh':
        print(f"    Type: Mesh")
        print(f"    Vertices: {info['num_vertices']}, Faces: {info['num_faces']}")
    elif info.get('type') == 'video':
        print(f"    Type: Video")
        print(f"    Size: {info.get('file_size_mb', 0):.2f} MB")

# Test 4: Load point cloud
print("\n5. Loading point cloud back...")
loaded = storage.load_point_cloud('test_pointcloud')
print(f"   Loaded {len(loaded['points'])} points")
print(f"   Has colors: {loaded['colors'] is not None}")

# Test 5: Load mesh
print("\n6. Loading mesh back...")
loaded_mesh = storage.load_mesh('test_mesh')
print(f"   Loaded {len(loaded_mesh['vertices'])} vertices")
print(f"   Loaded {len(loaded_mesh['faces'])} faces")

# Test 6: Get storage info
print("\n7. Checking Google Drive storage...")
info = storage.get_storage_info()
if info:
    print(f"   Total: {info['total_gb']:.2f} GB")
    print(f"   Used: {info['used_gb']:.2f} GB ({info['used_percentage']:.1f}%)")
    print(f"   Available: {info['available_gb']:.2f} GB")

print("\n" + "=" * 50)
print("✅ All tests completed successfully!")
print("=" * 50)
print("\nYou can now view your files at:")
print("https://drive.google.com")
print("Look for the 'PointClouds3D' folder")
