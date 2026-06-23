"""
Huey Background Task Queue
===========================

SQLite-backed task queue for offloading heavy work from the FastAPI
request cycle.  Runs in a separate process via::

    huey_consumer.py backend.tasks.huey -w 2 -k thread

Tasks defined here:
    • ``task_scan_directory``     — full directory scan + ingestion
    • ``task_generate_thumbnails``— batch thumbnail generation for items
                                    that were ingested without thumbnails
    • ``task_parse_takeout``      — Google Takeout import
"""

from __future__ import annotations

import logging

from backend.celery_app import celery_app

from backend.config import settings
settings.setup_rotating_logging()
from backend.db.engine import SessionLocal
from backend.db.models import MediaItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
def write_task_progress(
    task_id: str | None,
    status: str,
    total_found: int = 0,
    processed: int = 0,
    new_inserted: int = 0,
    duplicates_skipped: int = 0,
    errors: int = 0,
    current_file: str | None = None,
    start_time: float | None = None,
    result: dict | None = None,
    path: str | None = None,
    mode: str | None = None,
    generate_thumbs: bool | None = None,
    error_message: str | None = None,
) -> None:
    from backend.services.task_control import write_task_progress as persist_progress

    persist_progress(
        task_id,
        status,
        total_found=total_found,
        processed=processed,
        new_inserted=new_inserted,
        duplicates_skipped=duplicates_skipped,
        errors=errors,
        current_file=current_file,
        start_time=start_time,
        result=result,
        path=path,
        mode=mode,
        generate_thumbs=generate_thumbs,
        error_message=error_message,
    )


@celery_app.task
def task_scan_directory(
    root_path: str,
    generate_thumbs: bool = True,
    task_id: str | None = None,
    resume_after: str | None = None,
    initial_progress: dict | None = None,
) -> dict:
    """Background task: scan a directory and ingest media files.

    Returns a dict summary of the scan result.
    """
    from backend.services.scanner import scan_directory
    import time

    start_time = (initial_progress or {}).get("start_time") or time.time()
    logger.info("Starting background scan: %s", root_path)
    write_task_progress(
        task_id,
        "running",
        start_time=start_time,
        path=root_path,
        mode="scan",
        generate_thumbs=generate_thumbs,
    )

    try:
        with SessionLocal() as session:
            # Scanning is much faster with generate_thumbs=False.
            # We defer thumbnail generation to the concurrent background task.
            result = scan_directory(
                root_path,
                session,
                generate_thumbs=False,
                task_id=task_id,
                resume_after=resume_after,
                initial_progress=initial_progress,
            )

        summary = {
            "root_path": result.root_path,
            "total_found": result.total_found,
            "new_inserted": result.new_inserted,
            "duplicates_skipped": result.duplicates_skipped,
            "errors": result.errors,
        }
        if result.paused:
            summary["paused"] = True
            return summary

        logger.info("Background scan complete: %s", summary)
        write_task_progress(
            task_id,
            "complete",
            total_found=result.total_found,
            processed=result.total_found,
            new_inserted=result.new_inserted,
            duplicates_skipped=result.duplicates_skipped,
            errors=result.errors,
            start_time=start_time,
            result=summary,
        )
        # Log completion to audit logs
        from backend.db.engine import log_audit_entry
        log_audit_entry(
            "bulk_sync_complete",
            "success",
            f"Completed sync of {root_path}: found {result.total_found} files, inserted {result.new_inserted} new, skipped {result.duplicates_skipped} duplicates."
        )

        if generate_thumbs:
            try:
                task_generate_thumbnails.delay()
            except Exception as thumb_exc:
                logger.warning("Thumbnail generation automatic trigger failed: %s", thumb_exc)

        try:
            task_process_ml_pipeline.delay()
        except Exception as ml_exc:
            logger.warning("ML pipeline automatic trigger failed: %s", ml_exc)

        return summary
    except Exception as exc:
        logger.exception("Background scan failed: %s", exc)
        from backend.db.engine import log_audit_entry
        log_audit_entry("sync_error", "error", f"Background scan failed for {root_path}: {exc}")
        from backend.services.task_control import read_task_state

        state = read_task_state(task_id) if task_id else None
        progress = (state or {}).get("progress") or {}
        write_task_progress(
            task_id,
            "error",
            total_found=progress.get("total_found", 0),
            processed=progress.get("processed", 0),
            new_inserted=progress.get("new_inserted", 0),
            duplicates_skipped=progress.get("duplicates_skipped", 0),
            errors=progress.get("errors", 0),
            current_file=progress.get("current_file"),
            start_time=progress.get("start_time", start_time),
            path=root_path,
            mode="scan",
            generate_thumbs=generate_thumbs,
            error_message=str(exc),
        )
        raise exc


@celery_app.task
def task_generate_thumbnails(media_item_ids: list[str] | None = None) -> dict:
    """Background task: generate missing thumbnails.

    If ``media_item_ids`` is None, finds all items in the DB that are
    missing thumbnails and generates them.
    """
    from backend.services.thumbnails import generate_thumbnails_batch

    settings.ensure_cache_dirs()

    with SessionLocal() as session:
        if media_item_ids:
            query = session.query(MediaItem).filter(MediaItem.id.in_(media_item_ids))
        else:
            # Find all image and video items missing thumbnails
            query = session.query(MediaItem).filter(
                MediaItem.thumb_path.is_(None),
                (MediaItem.mime_type.like("image/%") | MediaItem.mime_type.like("video/%")),
            )

        items = query.all()
        if not items:
            logger.info("No items need thumbnail generation")
            return {"generated": 0, "total": 0}

        # Build work list: (original_path, sha256)
        work = [(item.original_path, item.sha256) for item in items]
        results = generate_thumbnails_batch(work)

        # Update DB with generated paths and compute deferred pHash
        item_by_sha256 = {item.sha256: item for item in items}
        updated = 0
        for tr in results:
            item = item_by_sha256.get(tr.sha256)
            if item:
                db_updated = False
                if tr.thumb_rel_path:
                    item.thumb_path = tr.thumb_rel_path
                    db_updated = True
                if tr.preview_rel_path:
                    item.preview_path = tr.preview_rel_path
                    db_updated = True
                if not item.phash and tr.phash:
                    # We use the precomputed pHash from the thread pool
                    item.phash = tr.phash
                    db_updated = True
                if db_updated:
                    updated += 1

        session.commit()

    summary = {"generated": updated, "total": len(items)}
    logger.info("Thumbnail generation complete: %s", summary)
    return summary


@celery_app.task
def task_parse_takeout(
    takeout_root: str,
    generate_thumbs: bool = True,
    task_id: str | None = None,
    resume_after: str | None = None,
    initial_progress: dict | None = None,
) -> dict:
    """Background task: parse a Google Takeout export directory.

    Returns a dict summary of the import result.
    """
    from backend.services.takeout import parse_takeout_directory
    import time

    start_time = (initial_progress or {}).get("start_time") or time.time()
    logger.info("Starting Takeout import: %s", takeout_root)
    write_task_progress(
        task_id,
        "running",
        start_time=start_time,
        path=takeout_root,
        mode="takeout",
        generate_thumbs=generate_thumbs,
    )

    try:
        with SessionLocal() as session:
            # Takeout importing is much faster with generate_thumbs=False.
            # We defer thumbnail generation to the concurrent background task.
            result = parse_takeout_directory(
                takeout_root,
                session,
                generate_thumbs=False,
                task_id=task_id,
                resume_after=resume_after,
                initial_progress=initial_progress,
            )

        summary = {
            "root_path": result.root_path,
            "total_found": result.total_found,
            "new_inserted": result.new_inserted,
            "duplicates_skipped": result.duplicates_skipped,
            "errors": result.errors,
        }
        if result.paused:
            summary["paused"] = True
            return summary

        logger.info("Takeout import complete: %s", summary)
        write_task_progress(
            task_id,
            "complete",
            total_found=result.total_found,
            processed=result.total_found,
            new_inserted=result.new_inserted,
            duplicates_skipped=result.duplicates_skipped,
            errors=result.errors,
            start_time=start_time,
            result=summary,
        )

        if generate_thumbs:
            try:
                task_generate_thumbnails.delay()
            except Exception as thumb_exc:
                logger.warning("Thumbnail generation automatic trigger failed: %s", thumb_exc)

        try:
            task_process_ml_pipeline.delay()
        except Exception as ml_exc:
            logger.warning("ML pipeline automatic trigger failed: %s", ml_exc)

        return summary
    except Exception as exc:
        logger.exception("Takeout import failed: %s", exc)
        from backend.services.task_control import read_task_state

        state = read_task_state(task_id) if task_id else None
        progress = (state or {}).get("progress") or {}
        write_task_progress(
            task_id,
            "error",
            total_found=progress.get("total_found", 0),
            processed=progress.get("processed", 0),
            new_inserted=progress.get("new_inserted", 0),
            duplicates_skipped=progress.get("duplicates_skipped", 0),
            errors=progress.get("errors", 0),
            current_file=progress.get("current_file"),
            start_time=progress.get("start_time", start_time),
            path=takeout_root,
            mode="takeout",
            generate_thumbs=generate_thumbs,
            error_message=str(exc),
        )
        raise exc


@celery_app.task
def task_process_ml_pipeline() -> dict:
    """Background task: Process ML pipeline (embeddings, etc).
    Runs in batches until no more unprocessed items exist.
    """
    from backend.services.ml import index_unprocessed_items
    from backend.services.task_control import write_task_progress
    from backend.db.models import MediaItem
    import time
    
    logger.info("Starting ML pipeline processing...")
    
    task_id = "ml-pipeline"
    start_time = time.time()
    
    total_processed = 0
    with SessionLocal() as session:
        total_to_process = session.query(MediaItem).filter(
            (MediaItem.clip_embedded == False) | (MediaItem.faces_scanned == False),
            MediaItem.mime_type.like("image/%")
        ).count()
        
        if total_to_process > 0:
            write_task_progress(
                task_id=task_id,
                status="running",
                total_found=total_to_process,
                processed=0,
                path="AI Media Analysis",
                mode="scan",
                start_time=start_time
            )
            
        total_faces = 0
        total_labels = 0
        
        while True:
            result = index_unprocessed_items(session, batch_size=20)
            processed = result.get("processed", 0)
            total_processed += processed
            total_faces += result.get("faces_found", 0)
            total_labels += result.get("labels_found", 0)
            
            if total_to_process > 0:
                write_task_progress(
                    task_id=task_id,
                    status="running",
                    total_found=total_to_process,
                    processed=total_processed,
                    faces_found=total_faces,
                    labels_found=total_labels,
                    path="AI Media Analysis",
                    mode="scan",
                    start_time=start_time
                )
            
            if result.get("status") == "idle" or processed == 0:
                break
            
            time.sleep(0.1)
                
        if total_to_process > 0:
            write_task_progress(
                task_id=task_id,
                status="complete",
                total_found=total_to_process,
                processed=total_processed,
                faces_found=total_faces,
                labels_found=total_labels,
                path="AI Media Analysis",
                mode="scan",
                start_time=start_time
            )
            
            from backend.db.models import AuditLog
            session.add(AuditLog(
                action="ml_pipeline_complete",
                level="success",
                details=f"Completed AI analysis for {total_processed} items. Found {total_faces} faces and {total_labels} labels."
            ))
            session.commit()
                
    summary = {"total_processed": total_processed}
    logger.info("ML pipeline complete: %s", summary)
    return summary


@celery_app.task
def task_scan_tag(tag_id: str, confidence_threshold: float = 0.17, task_id: str | None = None) -> dict:
    """Background task: Scan all media items to assign a tag semantically."""
    from backend.services.tag_scanner import scan_tag
    
    logger.info("Starting background tag scan for tag_id: %s", tag_id)
    with SessionLocal() as session:
        return scan_tag(session, tag_id, confidence_threshold=confidence_threshold, task_id=task_id)

