import sys, os
sys.path.append(os.getcwd())
os.environ["DATA_DIR"] = "./data"
from backend.db.engine import SessionLocal
from backend.db.models import Person, Face, MediaItem
from sqlalchemy import func, select

db = SessionLocal()
people = db.execute(select(Person)).scalars().all()
for p in people:
    count = db.execute(select(func.count(Face.id)).where(Face.person_id == p.id)).scalar() or 0
    if count > 0:
        print(f"{p.name} (ID: {p.id}): {count} faces")
