import logging
import time
from sqlalchemy.orm import Session
from backend.db.models import Tag, MediaItem, media_tags
from backend.db.vector import get_clip_table
from backend.services.ml import generate_text_embedding
from backend.services.task_control import write_task_progress

logger = logging.getLogger(__name__)

def scan_tag(db: Session, tag_id: str, confidence_threshold: float = 0.17, task_id: str | None = None) -> dict:
    """Scan all media items and assign the tag to those that semantically match."""
    start_time = time.time()
    
    # 1. Fetch the tag
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise ValueError(f"Tag with id {tag_id} not found")
    
    write_task_progress(
        task_id,
        "running",
        total_found=0,
        processed=0,
        new_inserted=0,
        duplicates_skipped=0,
        errors=0,
        start_time=start_time,
        mode="scan"
    )
    
    try:
        # 2. Generate text embedding for tag name
        vector = generate_text_embedding(tag.name)
        if not vector:
            raise ValueError(f"Failed to generate text embedding for tag: {tag.name}")
            
        clip_table = get_clip_table()
        if len(clip_table) == 0:
            logger.info("CLIP table is empty, no media to scan")
            write_task_progress(
                task_id,
                "complete",
                processed=0,
                start_time=start_time
            )
            return {"status": "success", "tagged_count": 0}
            
        # 3. Search LanceDB
        # Cosine similarity = 1 - L2 / 2
        # If similarity >= threshold, then L2 <= 2 * (1 - threshold)
        l2_threshold = 2.0 * (1.0 - confidence_threshold)
        
        max_limit = 100000
        results = clip_table.search(vector).limit(max_limit).to_list()
        
        matching_media_ids = []
        for r in results:
            dist = r.get("_distance", 999.0)
            if dist <= l2_threshold:
                matching_media_ids.append(r["media_id"])
                
        total_found = len(matching_media_ids)
        write_task_progress(
            task_id,
            "running",
            total_found=total_found,
            processed=0,
            start_time=start_time
        )
        
        # Clear existing media associations for this tag (re-scan behavior)
        db.execute(media_tags.delete().where(media_tags.c.tag_id == tag_id))
        db.commit()
        
        # 4. Assign tag to matching items
        batch_size = 100
        tagged_count = 0
        
        for i in range(0, len(matching_media_ids), batch_size):
            batch_ids = matching_media_ids[i:i+batch_size]
            items = db.query(MediaItem).filter(MediaItem.id.in_(batch_ids)).all()
            
            for item in items:
                if tag not in item.tags:
                    item.tags.append(tag)
                    tagged_count += 1
            
            db.commit()
            
            write_task_progress(
                task_id,
                "running",
                total_found=total_found,
                processed=min(i + batch_size, len(matching_media_ids)),
                new_inserted=tagged_count,
                start_time=start_time
            )
            
        write_task_progress(
            task_id,
            "complete",
            total_found=total_found,
            processed=len(matching_media_ids),
            new_inserted=tagged_count,
            start_time=start_time
        )
        
        return {"status": "success", "tagged_count": tagged_count}
        
    except Exception as e:
        logger.error(f"Error scanning tag: {e}", exc_info=True)
        write_task_progress(
            task_id,
            "error",
            error_message=str(e),
            start_time=start_time
        )
        raise e
