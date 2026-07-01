import sys
import os

sys.path.append(os.getcwd())
os.environ["DATA_DIR"] = "./data"

from backend.db.engine import SessionLocal
from backend.db.models import MediaItem

db = SessionLocal()

print("Updating paths in database...")
items = db.query(MediaItem).filter(MediaItem.original_path.like('/Volumes/disk6s1/%')).all()
count = 0
for item in items:
    item.original_path = item.original_path.replace('/Volumes/disk6s1/', '/Volumes/dwarf/')
    count += 1

db.commit()
print(f"Updated {count} paths!")
