import sys
import os

sys.path.append(os.getcwd())
os.environ["DATA_DIR"] = "./data"

from backend.db.engine import SessionLocal
from backend.db.models import MediaItem, Face, Person
from backend.db.vector import get_lancedb

db = SessionLocal()

# 1. Delete all faces and people from SQLite
print("Deleting SQLite faces and people...")
db.query(Face).delete()
db.query(Person).delete()

# 2. Reset faces_scanned flag on all MediaItems
print("Resetting faces_scanned on media items...")
db.query(MediaItem).update({"faces_scanned": False})

# 3. Drop LanceDB table if it exists
print("Dropping LanceDB face_embeddings...")
lancedb_db = get_lancedb()
try:
    lancedb_db.drop_table("face_embeddings")
except Exception as e:
    print(f"LanceDB drop error: {e}")

db.commit()
print("Reset complete! Ready for a clean scan.")
