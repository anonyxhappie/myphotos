import sys, os
sys.path.append(os.getcwd())
os.environ["DATA_DIR"] = "./data"
from backend.db.engine import SessionLocal
from backend.db.models import Person, Face, MediaItem
from sqlalchemy import func, select

db = SessionLocal()
people = db.execute(select(Person).where(Person.name == "Person 15")).scalars().all()
print(f"Found {len(people)} people named Person 15")
for p in people:
    count = db.execute(select(func.count(Face.id)).where(Face.person_id == p.id)).scalar() or 0
    items = db.execute(select(MediaItem).join(Face, Face.media_item_id == MediaItem.id).where(Face.person_id == p.id)).scalars().all()
    print(f"Person {p.id}: {count} faces, {len(items)} media items")
    for f in db.execute(select(Face).where(Face.person_id == p.id)).scalars().all():
        mi = db.get(MediaItem, f.media_item_id)
        if mi is None:
            print(f"  Face {f.id} points to missing MediaItem {f.media_item_id}")
