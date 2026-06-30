import sys, os
sys.path.append(os.getcwd())
os.environ["DATA_DIR"] = "./data"
from backend.services.ml import get_face_table
face_table = get_face_table()
print(f"Face table has {len(face_table)} rows.")
