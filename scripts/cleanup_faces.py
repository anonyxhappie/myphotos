import sys, os
sys.path.append(os.getcwd())
os.environ["DATA_DIR"] = "./data"

from backend.db.engine import SessionLocal
from backend.db.models import Face, Person
from backend.services.ml import cluster_faces

def cleanup():
    db = SessionLocal()
    print("Resetting person assignments...")
    faces = db.query(Face).all()
    for f in faces:
        f.person_id = None
    db.commit()
    
    print("Deleting all existing Person groups...")
    db.query(Person).delete()
    db.commit()
    
    print("Re-running clustering algorithm on all faces...")
    res = cluster_faces(db)
    print(f"Clustering complete: {res}")

if __name__ == "__main__":
    cleanup()
