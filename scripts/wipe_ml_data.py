import sys, os
sys.path.append(os.getcwd())
os.environ["DATA_DIR"] = "./data"

from backend.db.engine import SessionLocal
from backend.db.models import Face, Person, MediaItem, Tag, media_tags
from backend.services.ml import get_face_table, get_clip_table

def wipe_ml_data():
    db = SessionLocal()
    
    print("Deleting all faces from SQL...")
    db.query(Face).delete()
    
    print("Deleting all people from SQL...")
    db.query(Person).delete()
    
    print("Resetting ML flags on all media items...")
    db.query(MediaItem).update({"faces_scanned": False, "clip_embedded": False})
    
    print("Removing all AI generated tags...")
    ml_tags = db.query(Tag).filter(Tag.source.in_(["ai_clip", "ai_deepface", "ai_ocr"])).all()
    if ml_tags:
        ml_tag_ids = [t.id for t in ml_tags]
        db.execute(media_tags.delete().where(media_tags.c.tag_id.in_(ml_tag_ids)))
        db.query(Tag).filter(Tag.id.in_(ml_tag_ids)).delete(synchronize_session=False)
        
    db.commit()
    
    print("Clearing LanceDB tables...")
    try:
        get_face_table().delete("1=1")
    except Exception as e:
        print(f"Could not delete LanceDB face table: {e}")
        
    try:
        get_clip_table().delete("1=1")
    except Exception as e:
        print(f"Could not delete LanceDB clip table: {e}")
        
    print("ML Data successfully wiped. Ready for a clean scan.")

if __name__ == "__main__":
    wipe_ml_data()
