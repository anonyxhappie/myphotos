import sys
import os
import pandas as pd

sys.path.append(os.getcwd())
os.environ["DATA_DIR"] = "./data"

from backend.db.engine import SessionLocal
from backend.db.models import MediaItem, Face, Person
from backend.db.vector import get_face_table

db = SessionLocal()

print(f"Total MediaItems: {db.query(MediaItem).count()}")
print(f"Total Faces: {db.query(Face).count()}")
print(f"Total People: {db.query(Person).count()}")

# People with 0 faces
people_with_0_faces = 0
for p in db.query(Person).all():
    face_count = db.query(Face).filter(Face.person_id == p.id).count()
    if face_count == 0:
        people_with_0_faces += 1
print(f"People with 0 faces: {people_with_0_faces}")

# LanceDB face table
try:
    tbl = get_face_table()
    print(f"Total vectors in LanceDB face_table: {len(tbl)}")
except Exception as e:
    print(f"LanceDB error: {e}")

