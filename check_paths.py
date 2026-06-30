import sys
import os

sys.path.append(os.getcwd())
os.environ["DATA_DIR"] = "./data"

from backend.db.engine import SessionLocal
from backend.db.models import MediaItem
from sqlalchemy import func

db = SessionLocal()

prefixes = db.query(
    func.substr(MediaItem.original_path, 1, 17), 
    func.count(MediaItem.id)
).group_by(func.substr(MediaItem.original_path, 1, 17)).all()

for p, count in prefixes:
    print(f"{p}: {count}")
