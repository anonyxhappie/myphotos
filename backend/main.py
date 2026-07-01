"""
FastAPI Application
===================

The main API server for MyPhotos.  Start with::

    uvicorn backend.main:app --reload

All endpoints are prefixed with ``/api/``.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.config import settings
from backend.db.engine import get_db, log_audit_entry
from backend.db.models import Base, MediaItem, Volume, Tag, Person, Face
from backend.db.engine import engine
from backend.schemas import (
    MediaItemDetail,
    MediaItemSummary,
    ScanEnqueuedResponse,
    ScanProgress,
    ScanRequest,
    ScanStatusResponse,
    TakeoutRequest,
    TimelineResponse,
    VolumeResponse,
    AuditLogResponse,
    BulkDeleteRequest,
    PersonResponse,
    PersonUpdate,
    BulkDeletePeoplePetsRequest,
    TagCreate,
    TagWithCount,
    TimelineMetadataResponse,
)

logger = logging.getLogger(__name__)
settings.setup_rotating_logging()

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = FastAPI(
    title="MyPhotos",
    description="Local, offline Google Photos clone — Zero Server Spin-up",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# WebSocket Connection Manager & Redis Pub/Sub Listener
# ---------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()

async def redis_pubsub_listener():
    import os
    import redis.asyncio as aioredis
    import asyncio

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    while True:
        try:
            r = aioredis.from_url(redis_url)
            pubsub = r.pubsub()
            await pubsub.subscribe("scan_progress")
            logger.info("Subscribed to Redis scan_progress Pub/Sub channel")

            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is not None:
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    await manager.broadcast(data)
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Redis Pub/Sub listener error, reconnecting in 5s: %s", e)
            await asyncio.sleep(5)

# CORS – allow the React/Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Startup: ensure tables exist
# ---------------------------------------------------------------------------
@app.on_event("startup")
def _on_startup() -> None:
    settings.setup_rotating_logging()
    Base.metadata.create_all(bind=engine)
    settings.ensure_cache_dirs()

    # Auto-migrate: add trashed_at column if it doesn't exist
    try:
        from sqlalchemy import text, inspect as sa_inspect
        inspector = sa_inspect(engine)
        existing_cols = {c["name"] for c in inspector.get_columns("media_items")}
        if "trashed_at" not in existing_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE media_items ADD COLUMN trashed_at DATETIME"))
            logger.info("Migrated: added trashed_at column to media_items")
    except Exception as e:
        logger.warning("Migration check for trashed_at failed (may already exist): %s", e)

    logger.info("MyPhotos API ready — DB at %s", engine.url)
    
    # Clean up stale tasks and orphaned directory scans on startup
    try:
        from backend.db.engine import SessionLocal
        from backend.db.models import SyncedDirectory
        from backend.services.task_control import cleanup_stale_tasks
        
        with SessionLocal() as db:
            active_dirs = db.query(SyncedDirectory).filter(SyncedDirectory.is_active == True).all()
            active_paths = [d.path for d in active_dirs]
            cleanup_stale_tasks(active_paths)
    except Exception as e:
        logger.error("Failed to clean up stale tasks on startup: %s", e)

    # Start Redis Pub/Sub background listener
    import asyncio
    asyncio.create_task(redis_pubsub_listener())

    # Start directory watcher
    from backend.services.watcher import watcher_service
    watcher_service.start()

@app.on_event("shutdown")
def _on_shutdown() -> None:
    from backend.services.watcher import watcher_service
    watcher_service.stop()

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Timeline Endpoint                                                      ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@app.get("/api/timeline/metadata", response_model=TimelineMetadataResponse)
def get_timeline_metadata(
    favorites_only: bool = Query(False),
    videos_only: bool = Query(False),
    locked_only: bool = Query(False),
    dir_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> TimelineMetadataResponse:
    """Returns aggregated metadata for the timeline map (e.g. counts per year/month)."""
    from sqlalchemy import func, cast, Integer
    
    query = select(MediaItem).where(MediaItem.is_trashed == False)

    if locked_only:
        query = query.where(MediaItem.is_locked == True)
    else:
        query = query.where(MediaItem.is_locked == False)

    if favorites_only:
        query = query.where(MediaItem.is_favorite == True)
    
    if videos_only:
        query = query.where(MediaItem.mime_type.like("video/%"))

    if dir_id:
        from backend.db.models import SyncedDirectory
        import os
        directory = db.get(SyncedDirectory, dir_id)
        if directory:
            path_prefix = directory.path
            if not path_prefix.endswith(os.sep):
                path_prefix += os.sep
            query = query.where(MediaItem.original_path.like(path_prefix + "%"))
        else:
            query = query.where(MediaItem.id == "not-found")

    sort_col = func.coalesce(MediaItem.date_taken, MediaItem.date_modified, MediaItem.ingested_at)
    
    year_expr = cast(func.strftime('%Y', sort_col), Integer)
    month_expr = cast(func.strftime('%m', sort_col), Integer)
    
    agg_query = (
        query.with_only_columns(
            year_expr.label("year"), 
            month_expr.label("month"), 
            func.count(MediaItem.id).label("count")
        )
        .group_by(year_expr, month_expr)
        .order_by(year_expr.desc(), month_expr.desc())
    )
    
    rows = db.execute(agg_query).all()
    
    total_count = sum(row.count for row in rows)
    
    return TimelineMetadataResponse(
        total_count=total_count,
        items=[
            {"year": row.year, "month": row.month, "count": row.count}
            for row in rows
            if row.year is not None and row.month is not None
        ]
    )

@app.get("/api/timeline", response_model=TimelineResponse)
def get_timeline(
    cursor: Optional[str] = Query(None, description="ISO datetime cursor from previous page"),
    direction: str = Query("desc", description="'desc' fetches older, 'asc' fetches newer"),
    limit: int = Query(settings.TIMELINE_PAGE_SIZE, ge=1, le=500),
    favorites_only: bool = Query(False),
    videos_only: bool = Query(False),
    locked_only: bool = Query(False),
    dir_id: Optional[str] = Query(None),
    sort: str = Query("date_taken"),
    db: Session = Depends(get_db),
) -> TimelineResponse:
    """Return a page of media items sorted by date_taken or ingested_at DESC.

    Uses cursor-based pagination (keyset pagination) for stable,
    efficient paging over millions of rows — no OFFSET needed.
    """
    query = select(MediaItem).where(MediaItem.is_trashed == False)

    # Base filters
    if locked_only:
        query = query.where(MediaItem.is_locked == True)
    else:
        query = query.where(MediaItem.is_locked == False)

    if favorites_only:
        query = query.where(MediaItem.is_favorite == True)
    
    if videos_only:
        query = query.where(MediaItem.mime_type.like("video/%"))

    if dir_id:
        from backend.db.models import SyncedDirectory
        import os
        directory = db.get(SyncedDirectory, dir_id)
        if directory:
            path_prefix = directory.path
            if not path_prefix.endswith(os.sep):
                path_prefix += os.sep
            query = query.where(MediaItem.original_path.like(path_prefix + "%"))
        else:
            query = query.where(MediaItem.id == "not-found")

    # Total count (respecting filters)
    count_query = query.with_only_columns(func.count(MediaItem.id)).order_by(None)
    total = db.scalar(count_query)
    size_query = query.with_only_columns(func.sum(MediaItem.file_size_bytes)).order_by(None)
    total_size = db.scalar(size_query) or 0

    # Order By
    sort_col = (
        MediaItem.ingested_at
        if sort == "ingested_at"
        else func.coalesce(
            MediaItem.date_taken, MediaItem.date_modified, MediaItem.ingested_at
        )
    )
    
    if direction == "asc":
        query = query.order_by(sort_col.asc(), MediaItem.id.asc())
    else:
        query = query.order_by(sort_col.desc(), MediaItem.id.desc())

    # Apply cursor filter
    if cursor:
        from datetime import datetime
        try:
            cursor_dt = datetime.fromisoformat(cursor)
        except ValueError:
            raise HTTPException(400, f"Invalid cursor format: {cursor}")
        
        if direction == "asc":
            query = query.where(
                (sort_col > cursor_dt)
                | ((sort_col == cursor_dt) & (MediaItem.id > cursor))
            )
        else:
            query = query.where(
                (sort_col < cursor_dt)
                | ((sort_col == cursor_dt) & (MediaItem.id < cursor))
            )

    query = query.limit(limit + 1)  # Fetch one extra to determine if there's a next page
    rows = db.execute(query).scalars().all()

    # Determine next cursor
    has_next = len(rows) > limit
    if has_next:
        rows = rows[:limit]

    # If we fetched ascending, we reverse the rows so they are still returned
    # to the frontend in descending order (newest to oldest).
    if direction == "asc":
        rows.reverse()

    next_cursor = None
    if has_next and rows:
        last = rows[0] if direction == "asc" else rows[-1]
        val = last.date_taken or last.date_modified or last.ingested_at
        next_cursor = val.isoformat() if val else last.id

    # Build volume online lookup
    volume_ids = {item.volume_id for item in rows if item.volume_id}
    online_volumes: set[str] = set()
    if volume_ids:
        online_rows = db.execute(
            select(Volume.id).where(Volume.id.in_(volume_ids), Volume.is_online.is_(True))
        ).scalars().all()
        online_volumes = set(online_rows)

    # Map to response models
    summaries = []
    for item in rows:
        is_online = item.volume_id in online_volumes if item.volume_id else True
        summaries.append(
            MediaItemSummary(
                id=item.id,
                sha256=item.sha256,
                thumb_path=item.thumb_path,
                date_taken=item.date_taken,
                date_modified=item.date_modified,
                width=item.width,
                height=item.height,
                mime_type=item.mime_type,
                is_favorite=item.is_favorite,
                is_locked=item.is_locked,
                is_online=is_online,
            )
        )

    return TimelineResponse(
        items=summaries,
        next_cursor=next_cursor,
        total_count=total or 0,
        total_size_bytes=total_size,
    )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Media Detail                                                           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@app.get("/api/media/{media_id}", response_model=MediaItemDetail)
def get_media_detail(media_id: str, db: Session = Depends(get_db)) -> MediaItemDetail:
    """Return full metadata for a single media item.

    If the item's volume is offline, includes an ``offline_message``
    prompting the user to reconnect the drive.
    """
    item = db.get(MediaItem, media_id)
    if not item:
        raise HTTPException(404, "Media item not found")

    # Check both the recorded volume state and the actual file.  A removable
    # drive can disappear between volume scans, so the filesystem is the
    # source of truth for whether the original can be served.
    is_online = True
    original_available = Path(item.original_path).is_file()
    volume_label = None
    offline_message = None

    if item.volume_id:
        volume = db.get(Volume, item.volume_id)
        if volume:
            volume_label = volume.label
            is_online = volume.is_online
            if not is_online:
                offline_message = (
                    f'Please connect drive "{volume.label}" to view the original file.'
                )
    if not original_available and not offline_message:
        offline_message = "The original file is currently unavailable."

    return MediaItemDetail(
        **{
            c.key: getattr(item, c.key)
            for c in item.__table__.columns
        },
        is_online=is_online,
        original_available=original_available,
        volume_label=volume_label,
        offline_message=offline_message,
        tags=item.tags,
    )

@app.post("/api/media/{media_id}/favorite", response_model=MediaItemSummary)
def toggle_favorite(media_id: str, db: Session = Depends(get_db)):
    """Toggle the favorite status of a media item."""
    item = db.get(MediaItem, media_id)
    if not item:
        raise HTTPException(404, "Media item not found")
    item.is_favorite = not item.is_favorite
    db.commit()
    return MediaItemSummary.model_validate(item)

@app.post("/api/media/{media_id}/lock", response_model=MediaItemSummary)
def toggle_lock(media_id: str, db: Session = Depends(get_db)):
    """Toggle the locked status of a media item."""
    item = db.get(MediaItem, media_id)
    if not item:
        raise HTTPException(404, "Media item not found")
    item.is_locked = not item.is_locked
    db.commit()
    return MediaItemSummary.model_validate(item)

@app.post("/api/media/delete")
def bulk_delete_media(req: BulkDeleteRequest, db: Session = Depends(get_db)):
    """Soft-delete media items by moving them to the bin (is_trashed=True)."""
    import uuid
    from datetime import datetime, timezone
    
    if not req.media_ids:
        return {"status": "success", "deleted_count": 0}
        
    valid_ids = []
    for mid in req.media_ids:
        try:
            valid_ids.append(str(uuid.UUID(mid)))
        except ValueError:
            pass

    if not valid_ids:
        return {"status": "success", "deleted_count": 0}

    items = db.query(MediaItem).filter(MediaItem.id.in_(valid_ids)).all()
    trashed_count = len(items)
    
    now = datetime.now(timezone.utc)
    for item in items:
        item.is_trashed = True
        item.trashed_at = now
        
    db.commit()
         
    log_audit_entry("file_trashed", "info", f"Moved {trashed_count} media item(s) to bin")
    return {"status": "success", "deleted_count": trashed_count}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Bin (Trash)                                                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@app.get("/api/bin", response_model=TimelineResponse)
def list_bin(db: Session = Depends(get_db)) -> TimelineResponse:
    """List all trashed media items."""
    query = select(MediaItem).where(MediaItem.is_trashed == True)
    sort_col = func.coalesce(MediaItem.date_taken, MediaItem.date_modified, MediaItem.ingested_at)
    query = query.order_by(sort_col.desc())
    rows = db.execute(query).scalars().all()

    volume_ids = {item.volume_id for item in rows if item.volume_id}
    online_volumes: set[str] = set()
    if volume_ids:
        online_rows = db.execute(
            select(Volume.id).where(Volume.id.in_(volume_ids), Volume.is_online.is_(True))
        ).scalars().all()
        online_volumes = set(online_rows)

    summaries = []
    for item in rows:
        is_online = item.volume_id in online_volumes if item.volume_id else True
        summaries.append(
            MediaItemSummary(
                id=item.id,
                sha256=item.sha256,
                thumb_path=item.thumb_path,
                date_taken=item.date_taken,
                date_modified=item.date_modified,
                width=item.width,
                height=item.height,
                mime_type=item.mime_type,
                is_favorite=item.is_favorite,
                is_locked=item.is_locked,
                is_online=is_online,
            )
        )

    total_size = sum(item.file_size_bytes or 0 for item in rows)
    return TimelineResponse(
        items=summaries,
        next_cursor=None,
        total_count=len(summaries),
        total_size_bytes=total_size,
    )


@app.post("/api/bin/restore")
def restore_from_bin(req: BulkDeleteRequest, db: Session = Depends(get_db)):
    """Restore trashed media items from the bin."""
    import uuid

    if not req.media_ids:
        return {"status": "success", "restored_count": 0}

    valid_ids = []
    for mid in req.media_ids:
        try:
            valid_ids.append(str(uuid.UUID(mid)))
        except ValueError:
            pass

    if not valid_ids:
        return {"status": "success", "restored_count": 0}

    items = db.query(MediaItem).filter(
        MediaItem.id.in_(valid_ids),
        MediaItem.is_trashed == True,
    ).all()
    restored_count = len(items)

    for item in items:
        item.is_trashed = False
        item.trashed_at = None

    db.commit()
    log_audit_entry("file_restored", "info", f"Restored {restored_count} media item(s) from bin")
    return {"status": "success", "restored_count": restored_count}


@app.post("/api/bin/empty")
def empty_bin(db: Session = Depends(get_db)):
    """Permanently delete all trashed media items."""
    from backend.db.vector import get_clip_table, get_face_table

    items = db.query(MediaItem).filter(MediaItem.is_trashed == True).all()
    if not items:
        return {"status": "success", "deleted_count": 0}

    valid_ids = [item.id for item in items]
    deleted_count = len(items)

    for item in items:
        # Delete generated thumbnails/previews
        if item.thumb_path:
            try:
                (settings.CACHE_DIR / item.thumb_path).unlink(missing_ok=True)
            except Exception:
                pass
        if item.preview_path:
            try:
                (settings.CACHE_DIR / item.preview_path).unlink(missing_ok=True)
            except Exception:
                pass

        # Delete original file on disk
        if item.original_path:
            try:
                original_file = Path(item.original_path)
                if original_file.exists():
                    original_file.unlink()
            except Exception as e:
                logger.warning("Failed to delete original file %s: %s", item.original_path, e)

        db.delete(item)

    db.commit()

    # Delete from LanceDB vector index
    try:
        clip_table = get_clip_table()
        clip_table.delete(f"media_id in {tuple(valid_ids) if len(valid_ids) > 1 else f'(\"{valid_ids[0]}\")'}") 
    except Exception as e:
        logger.warning("Failed to delete from clip vector table: %s", e)

    try:
        face_table = get_face_table()
        face_table.delete(f"media_id in {tuple(valid_ids) if len(valid_ids) > 1 else f'(\"{valid_ids[0]}\")'}") 
    except Exception as e:
        logger.warning("Failed to delete from face vector table: %s", e)

    log_audit_entry("bin_emptied", "warning", f"Permanently deleted {deleted_count} media item(s) from bin")
    return {"status": "success", "deleted_count": deleted_count}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Thumbnail / Preview Serving                                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@app.get("/api/media/{media_id}/thumb")
def get_thumbnail(media_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """Serve the 256 px WebP thumbnail for a media item."""
    item = db.get(MediaItem, media_id)
    if not item:
        raise HTTPException(404, "Media item not found")
    if not item.thumb_path:
        raise HTTPException(404, "Thumbnail not generated yet")

    full_path = settings.CACHE_DIR / item.thumb_path
    if not full_path.exists():
        raise HTTPException(404, "Thumbnail file missing from cache")

    return FileResponse(
        str(full_path),
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.get("/api/media/{media_id}/preview")
def get_preview(media_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """Serve the 1080 px WebP preview for a media item."""
    item = db.get(MediaItem, media_id)
    if not item:
        raise HTTPException(404, "Media item not found")
    if not item.preview_path:
        raise HTTPException(404, "Preview not generated yet")

    full_path = settings.CACHE_DIR / item.preview_path
    if not full_path.exists():
        raise HTTPException(404, "Preview file missing from cache")

    return FileResponse(
        str(full_path),
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@app.get("/api/media/{media_id}/original")
def get_original(media_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """Stream the original media file inline.

    Starlette's ``FileResponse`` handles HTTP byte ranges, which lets native
    browser video controls seek without downloading the whole file first.
    """
    item = db.get(MediaItem, media_id)
    if not item:
        raise HTTPException(404, "Media item not found")

    full_path = Path(item.original_path)
    try:
        # Check readability to catch macOS TCC / permission issues early
        with open(full_path, "rb") as f:
            pass
    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Permission denied by macOS. Please grant Full Disk Access to your Terminal/IDE in System Settings."
        )
    except Exception:
        raise HTTPException(404, "Original file is currently unavailable")

    guessed_type, _ = mimetypes.guess_type(full_path.name)
    media_type = item.mime_type or guessed_type or "application/octet-stream"

    return FileResponse(
        str(full_path),
        media_type=media_type,
        filename=item.filename,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/api/media/{media_id}/open-in-finder")
def open_in_finder(media_id: str, db: Session = Depends(get_db)):
    """Open the original media file in macOS Finder (revealed and highlighted)."""
    item = db.get(MediaItem, media_id)
    if not item:
        raise HTTPException(404, "Media item not found")

    full_path = Path(item.original_path)
    if not full_path.exists():
        raise HTTPException(404, "Original file is offline or unavailable")

    import subprocess
    try:
        # open -R reveals the file in Finder on macOS
        subprocess.run(["open", "-R", str(full_path)], check=True)
        return {"status": "success"}
    except Exception as e:
        logger.error("Failed to open in Finder: %s", e)
        raise HTTPException(500, f"Failed to open in Finder: {e}")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Volumes                                                                ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@app.get("/api/volumes", response_model=list[VolumeResponse])
def list_volumes(db: Session = Depends(get_db)) -> list[VolumeResponse]:
    """List all tracked storage volumes with online/offline status."""
    volumes = db.query(Volume).order_by(Volume.label).all()
    return [VolumeResponse.model_validate(v) for v in volumes]


@app.post("/api/volumes/sync", response_model=list[VolumeResponse])
def sync_volumes(db: Session = Depends(get_db)) -> list[VolumeResponse]:
    """Re-detect mounted volumes and sync the database.

    Marks disconnected drives as offline and registers new drives.
    """
    from backend.services.volumes import sync_volumes_to_db

    sync_volumes_to_db(db)
    volumes = db.query(Volume).order_by(Volume.label).all()
    return [VolumeResponse.model_validate(v) for v in volumes]


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Scan Endpoints                                                         ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@app.get("/api/select-folder")
def select_folder() -> dict:
    """Open a native macOS folder chooser dialog and return the path."""
    import subprocess
    import sys

    # Only support macOS for native dialog choosing
    if sys.platform != "darwin":
        raise HTTPException(400, "Native folder chooser is only supported on macOS.")

    # Run AppleScript to open directory dialog
    script = 'POSIX path of (choose folder with prompt "Select Photos Directory")'
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        selected_path = proc.stdout.strip()
        return {"path": selected_path}
    except subprocess.CalledProcessError:
        # User canceled the dialog
        return {"path": None}
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "Folder selection timed out.")


@app.post("/api/scan", response_model=ScanEnqueuedResponse)
def enqueue_scan(req: ScanRequest) -> ScanEnqueuedResponse:
    """Enqueue a background directory scan task."""
    scan_path = Path(req.path).resolve()
    if not scan_path.is_dir():
        raise HTTPException(400, f"Not a valid directory: {req.path}")

    from backend.tasks import task_scan_directory
    from backend.services.task_control import clear_task_control, write_task_progress
    import uuid

    task_id = str(uuid.uuid4())
    clear_task_control(task_id)
    write_task_progress(
        task_id,
        "pending",
        path=str(scan_path),
        mode="scan",
        generate_thumbs=req.generate_thumbs,
    )
    task_scan_directory.delay(str(scan_path), req.generate_thumbs, task_id=task_id)
    return ScanEnqueuedResponse(task_id=task_id, message=f"Scan enqueued for {scan_path}", path=str(scan_path))


@app.post("/api/scan/takeout", response_model=ScanEnqueuedResponse)
def enqueue_takeout(req: TakeoutRequest) -> ScanEnqueuedResponse:
    """Enqueue a background Google Takeout import task."""
    takeout_path = Path(req.path).resolve()
    if not takeout_path.is_dir():
        raise HTTPException(400, f"Not a valid directory: {req.path}")

    from backend.tasks import task_parse_takeout
    from backend.services.task_control import clear_task_control, write_task_progress
    import uuid

    task_id = str(uuid.uuid4())
    clear_task_control(task_id)
    write_task_progress(
        task_id,
        "pending",
        path=str(takeout_path),
        mode="takeout",
        generate_thumbs=req.generate_thumbs,
    )
    task_parse_takeout.delay(str(takeout_path), req.generate_thumbs, task_id=task_id)
    return ScanEnqueuedResponse(task_id=task_id, message=f"Takeout import enqueued for {takeout_path}", path=str(takeout_path))


@app.websocket("/api/ws/scan-progress")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep the socket open by listening for heartbeat / client events
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/api/scan/status/{task_id}", response_model=ScanStatusResponse)
def get_scan_status(task_id: str) -> ScanStatusResponse:
    """Check the status of a background scan task."""
    from backend.services.task_control import read_task_state

    data = read_task_state(task_id)
    if data:
        return ScanStatusResponse.model_validate(data)

    return ScanStatusResponse(
        task_id=task_id,
        status="pending",
        progress=ScanProgress(
            total_found=0,
            processed=0,
            new_inserted=0,
            duplicates_skipped=0,
            errors=0,
        ),
    )


@app.get("/api/scans", response_model=list[ScanStatusResponse])
def list_scans(include_complete: bool = Query(False)) -> list[ScanStatusResponse]:
    """List persisted scan tasks so paused and failed scans survive reloads."""
    from backend.services.task_control import list_task_states

    return [
        ScanStatusResponse.model_validate(state)
        for state in list_task_states(include_complete=include_complete)
        if state.get("path")
    ]


@app.post("/api/scan/{task_id}/pause", response_model=ScanStatusResponse)
def pause_scan(task_id: str) -> ScanStatusResponse:
    """Request a cooperative pause at the next file boundary."""
    from backend.services.task_control import read_task_state, request_pause, write_task_progress

    state = read_task_state(task_id)
    if not state:
        raise HTTPException(404, "Scan task not found")
    if state.get("status") not in {"pending", "running"}:
        raise HTTPException(409, f"Cannot pause a {state.get('status')} scan")

    request_pause(task_id)
    updated = write_task_progress(task_id, "pausing")
    return ScanStatusResponse.model_validate(updated)


def _requeue_scan(task_id: str, *, retry: bool) -> ScanStatusResponse:
    from backend.services.task_control import clear_task_control, read_task_state, write_task_progress
    from backend.tasks import task_parse_takeout, task_scan_directory

    state = read_task_state(task_id)
    if not state:
        raise HTTPException(404, "Scan task not found")

    allowed_statuses = {"error"} if retry else {"paused"}
    if state.get("status") not in allowed_statuses:
        action = "retry" if retry else "resume"
        raise HTTPException(409, f"Cannot {action} a {state.get('status')} scan")
    path = state.get("path")
    if path in ("AI Media Analysis", "Face Detection"):
        pass # Skip directory check for ML tasks
    elif not path or not Path(path).is_dir():
        raise HTTPException(400, f"Scan directory is unavailable: {path}")

    progress = state.get("progress") or {}
    resume_after = None if retry else progress.get("current_file")
    initial_progress = None if retry else progress
    mode = state.get("mode", "scan")
    generate_thumbs = state.get("generate_thumbs", True)

    clear_task_control(task_id)
    updated = write_task_progress(
        task_id,
        "pending",
        path=path,
        mode=mode,
        generate_thumbs=generate_thumbs,
        error_message=None,
        **({} if not retry else {
            "total_found": 0,
            "processed": 0,
            "new_inserted": 0,
            "duplicates_skipped": 0,
            "errors": 0,
            "current_file": "",
            "start_time": None,
        }),
    )

    if task_id == "ml-pipeline":
        from backend.tasks import task_process_ml_pipeline
        task_process_ml_pipeline.delay()
    elif task_id == "face-scan":
        from backend.tasks import task_scan_faces
        task_scan_faces.delay(task_id="face-scan")
    else:
        task = task_parse_takeout if mode == "takeout" else task_scan_directory
        task.delay(
            path,
            generate_thumbs,
            task_id=task_id,
            resume_after=resume_after,
            initial_progress=initial_progress,
        )

    return ScanStatusResponse.model_validate(updated)


@app.post("/api/scan/{task_id}/resume", response_model=ScanStatusResponse)
def resume_scan(task_id: str) -> ScanStatusResponse:
    """Resume a paused scan from its last processed file."""
    return _requeue_scan(task_id, retry=False)


@app.post("/api/scan/{task_id}/retry", response_model=ScanStatusResponse)
def retry_scan(task_id: str) -> ScanStatusResponse:
    """Retry a failed scan; committed media remains and is deduplicated."""
    return _requeue_scan(task_id, retry=True)


@app.delete("/api/scan/{task_id}")
def delete_scan(task_id: str) -> dict[str, str]:
    """Delete/dismiss a persisted scan task from the cache entirely."""
    from backend.services.task_control import task_state_path, task_control_path
    
    state_path = task_state_path(task_id)
    control_path = task_control_path(task_id)
    
    deleted = False
    if state_path.exists():
        state_path.unlink(missing_ok=True)
        deleted = True
    if control_path.exists():
        control_path.unlink(missing_ok=True)
        deleted = True
        
    if not deleted:
        raise HTTPException(404, "Scan task not found")
        
    return {"status": "success", "message": f"Scan task {task_id} deleted"}


@app.post("/api/scan/resync_all", response_model=list[ScanEnqueuedResponse])
def resync_all(db: Session = Depends(get_db)):
    """Trigger background scans for all actively monitored directories."""
    from backend.tasks import task_scan_directory
    from backend.db.models import SyncedDirectory
    from backend.services.task_control import clear_task_control, write_task_progress
    import uuid
    
    dirs = db.query(SyncedDirectory).filter(SyncedDirectory.is_active == True).all()
    responses = []
    for directory in dirs:
        task_id = str(uuid.uuid4())
        clear_task_control(task_id)
        write_task_progress(
            task_id,
            "pending",
            path=directory.path,
            mode="scan",
            generate_thumbs=True,
        )
        task_scan_directory.delay(directory.path, True, task_id=task_id)
        responses.append(ScanEnqueuedResponse(
            task_id=task_id, 
            message=f"Scan started for {directory.path}",
            path=directory.path
        ))
    return responses

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Search & ML Endpoints                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@app.post("/api/ml/start", response_model=ScanEnqueuedResponse)
def start_ml_pipeline() -> ScanEnqueuedResponse:
    """Enqueue the background ML pipeline for embeddings."""
    from backend.tasks import task_process_ml_pipeline
    
    result = task_process_ml_pipeline.delay()
    return ScanEnqueuedResponse(task_id=result.id, message="ML pipeline started")

@app.post("/api/ml/retrain", response_model=ScanEnqueuedResponse)
def retrain_ml(db: Session = Depends(get_db)):
    """Reset ML flags and re-run ML pipeline for all items. Also clears out old ML data."""
    from backend.tasks import task_process_ml_pipeline
    from backend.db.models import MediaItem, AuditLog, Face, Person, media_tags, Tag
    from backend.services.ml import get_face_table, get_clip_table
    import lancedb
    
    # 1. Clear out SQL tables
    db.query(Face).delete()
    db.query(Person).delete()
    
    # 2. Remove AI generated tags
    ml_tags = db.query(Tag).filter(Tag.source.in_(["ai_clip", "ai_deepface", "ai_ocr"])).all()
    ml_tag_ids = [t.id for t in ml_tags]
    if ml_tag_ids:
        db.execute(media_tags.delete().where(media_tags.c.tag_id.in_(ml_tag_ids)))
        db.query(Tag).filter(Tag.id.in_(ml_tag_ids)).delete(synchronize_session=False)
        
    db.query(MediaItem).update({"faces_scanned": False, "clip_embedded": False})
    
    # 3. Clear LanceDB tables
    try:
        get_face_table().delete("1=1")
    except Exception:
        pass
    try:
        get_clip_table().delete("1=1")
    except Exception:
        pass
        
    db.add(AuditLog(
        action="retrain_ml",
        level="warning",
        details="Triggered AI retraining for all media items. Cleared old ML data."
    ))
    db.commit()
    
    result = task_process_ml_pipeline.delay()
    return ScanEnqueuedResponse(task_id=result.id, message="ML retraining started")

@app.post("/api/ml/retrain_faces", response_model=ScanEnqueuedResponse)
def retrain_faces(db: Session = Depends(get_db)):
    """Reset only face flags and re-run ML pipeline. Clears out old face data."""
    from backend.tasks import task_process_ml_pipeline
    from backend.db.models import MediaItem, AuditLog, Face, Person, media_tags, Tag
    from backend.services.ml import get_face_table
    
    # 1. Clear out SQL tables
    db.query(Face).delete()
    db.query(Person).delete()
    
    # 2. Remove Deepface tags
    deepface_tags = db.query(Tag).filter(Tag.source == "ai_deepface").all()
    if deepface_tags:
        df_tag_ids = [t.id for t in deepface_tags]
        db.execute(media_tags.delete().where(media_tags.c.tag_id.in_(df_tag_ids)))
        db.query(Tag).filter(Tag.id.in_(df_tag_ids)).delete(synchronize_session=False)
    
    db.query(MediaItem).update({"faces_scanned": False})
    
    # 3. Clear LanceDB table
    try:
        get_face_table().delete("1=1")
    except Exception:
        pass
        
    db.add(AuditLog(
        action="retrain_faces",
        level="info",
        details="Triggered Face Retraining for all media items. Cleared old face data."
    ))
    db.commit()
    
    result = task_process_ml_pipeline.delay()
    return ScanEnqueuedResponse(task_id=result.id, message="Face retraining started")

@app.get("/api/search", response_model=TimelineResponse)
def search_media(q: str = Query(..., description="Search query"), db: Session = Depends(get_db)) -> TimelineResponse:
    """Search for media items semantically or by metadata."""
    from backend.services.ml import search_semantic
    
    # 1. Get media IDs from LanceDB (Semantic search)
    semantic_media_ids = search_semantic(q, limit=50)
    
    # 2. Get media IDs from SQL database matching explicitly generated tags
    tag_media_rows = db.execute(
        select(MediaItem.id)
        .join(MediaItem.tags)
        .where(Tag.name.ilike(f"%{q}%"))
        .limit(50)
    ).scalars().all()
    
    # Combine sets of IDs
    all_media_ids = list(set(semantic_media_ids + list(tag_media_rows)))
    
    if not all_media_ids:
        return TimelineResponse(items=[], next_cursor=None, total_count=0, total_size_bytes=0)
        
    # Fetch metadata for those IDs
    query = select(MediaItem).where(MediaItem.id.in_(all_media_ids), MediaItem.is_trashed == False)
    rows = db.execute(query).scalars().all()
    
    # Sort them: first the semantic results in order, then any SQL-only matches
    items_by_id = {item.id: item for item in rows}
    items = []
    
    for mid in semantic_media_ids:
        if mid in items_by_id:
            items.append(items_by_id[mid])
            del items_by_id[mid]
            
    for item in items_by_id.values():
        items.append(item)
    
    # Build volume online lookup
    volume_ids = {item.volume_id for item in items if item.volume_id}
    online_volumes: set[str] = set()
    if volume_ids:
        online_rows = db.execute(
            select(Volume.id).where(Volume.id.in_(volume_ids), Volume.is_online.is_(True))
        ).scalars().all()
        online_volumes = set(online_rows)

    # Map to response models
    summaries = []
    for item in items:
        is_online = item.volume_id in online_volumes if item.volume_id else True
        summaries.append(
            MediaItemSummary(
                id=item.id,
                sha256=item.sha256,
                thumb_path=item.thumb_path,
                date_taken=item.date_taken,
                date_modified=item.date_modified,
                width=item.width,
                height=item.height,
                mime_type=item.mime_type,
                is_favorite=item.is_favorite,
                is_locked=item.is_locked,
                is_online=is_online,
            )
        )

    total_size = sum(item.file_size_bytes or 0 for item in items)

    return TimelineResponse(
        items=summaries,
        next_cursor=None,
        total_count=len(summaries),
        total_size_bytes=total_size,
    )


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Health Check                                                           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@app.get("/api/health")
def health_check(db: Session = Depends(get_db)) -> dict:
    """Simple health check — verifies DB connectivity."""
    from sqlalchemy import text

    row = db.execute(text("SELECT 1")).scalar()
    total_media = db.scalar(select(func.count(MediaItem.id)))
    total_volumes = db.scalar(select(func.count(Volume.id)))
    total_size = db.scalar(select(func.sum(MediaItem.file_size_bytes))) or 0
    return {
        "status": "healthy",
        "db_connected": row == 1,
        "total_media_items": total_media,
        "total_volumes": total_volumes,
        "total_size_bytes": total_size,
    }


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Settings / Synced Directories                                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

from backend.db.models import SyncedDirectory
from backend.schemas import SyncedDirectoryResponse, SyncedDirectoryCreate
from backend.services.watcher import watcher_service
from backend.services.directory_stats import get_cached_total_files

@app.get("/api/settings/synced-directories", response_model=list[SyncedDirectoryResponse])
def get_synced_directories(db: Session = Depends(get_db)):
    """List all synced directories with total and synced file counts."""
    import os
    dirs = db.query(SyncedDirectory).all()
    res = []
    for d in dirs:
        total_files = 0
        try:
            path_obj = Path(d.path)
            total_files = get_cached_total_files(path_obj)
        except Exception:
            pass

        # Count synced files
        path_prefix = d.path
        if not path_prefix.endswith(os.sep):
            path_prefix += os.sep

        synced_files = db.query(MediaItem).filter(
            MediaItem.original_path.like(path_prefix + "%")
        ).count()

        covers = db.query(MediaItem.id).filter(
            MediaItem.original_path.like(path_prefix + "%")
        ).order_by(MediaItem.date_taken.desc().nullslast(), MediaItem.id.desc()).limit(4).all()
        cover_media_ids = [c[0] for c in covers]

        res.append(
            SyncedDirectoryResponse(
                id=d.id,
                path=d.path,
                is_active=d.is_active,
                created_at=d.created_at,
                updated_at=d.updated_at,
                total_files=total_files,
                synced_files=synced_files,
                cover_media_ids=cover_media_ids,
            )
        )
    return res

@app.post("/api/settings/synced-directories", response_model=SyncedDirectoryResponse)
def add_synced_directory(req: SyncedDirectoryCreate, db: Session = Depends(get_db)):
    """Add a new directory to monitor for real-time changes."""
    import os
    path_obj = Path(req.path).resolve()
    if not path_obj.is_dir():
        raise HTTPException(400, f"Not a valid directory: {req.path}")
        
    watcher_service.add_directory(str(path_obj))
    
    # Return the newly added or updated directory
    sd = db.query(SyncedDirectory).filter_by(path=str(path_obj)).first()
    
    # Enqueue a background directory scan task
    from backend.tasks import task_scan_directory
    from backend.services.task_control import clear_task_control, write_task_progress
    import uuid
    
    task_id = str(uuid.uuid4())
    clear_task_control(task_id)
    write_task_progress(
        task_id,
        "pending",
        path=str(path_obj),
        mode="scan",
        generate_thumbs=True,
    )
    task_scan_directory.delay(str(path_obj), True, task_id=task_id)
    
    # Calculate counts
    total_files = 0
    try:
        total_files = get_cached_total_files(path_obj)
    except Exception:
        pass

    path_prefix = str(path_obj)
    if not path_prefix.endswith(os.sep):
        path_prefix += os.sep

    synced_files = db.query(MediaItem).filter(
        MediaItem.original_path.like(path_prefix + "%")
    ).count()

    covers = db.query(MediaItem.id).filter(
        MediaItem.original_path.like(path_prefix + "%")
    ).order_by(MediaItem.date_taken.desc().nullslast(), MediaItem.id.desc()).limit(4).all()
    cover_media_ids = [c[0] for c in covers]

    log_audit_entry("sync_dir_added", "success", f"Added directory to sync: {path_obj}")

    return SyncedDirectoryResponse(
        id=sd.id,
        path=sd.path,
        is_active=sd.is_active,
        created_at=sd.created_at,
        updated_at=sd.updated_at,
        task_id=task_id,
        total_files=total_files,
        synced_files=synced_files,
        cover_media_ids=cover_media_ids,
    )

@app.get("/api/settings/synced-directories/{id}", response_model=SyncedDirectoryResponse)
def get_synced_directory(id: str, db: Session = Depends(get_db)):
    """Get a single synced directory."""
    import os
    d = db.get(SyncedDirectory, id)
    if not d:
        raise HTTPException(404, "Synced directory not found")
        
    total_files = 0
    try:
        path_obj = Path(d.path)
        if path_obj.is_dir():
            for dirpath, dirnames, filenames in os.walk(path_obj):
                # Ignore hidden directories (starting with '.')
                dirnames[:] = [d for d in dirnames if not d.startswith('.')]
                for fname in filenames:
                    # Ignore hidden files (starting with '.') and macOS shadow/metadata files (starting with '._')
                    if fname.startswith('.'):
                        continue
                    ext = Path(fname).suffix.lower()
                    if ext in settings.SUPPORTED_EXTENSIONS:
                        total_files += 1
    except Exception:
        pass

    path_prefix = d.path
    if not path_prefix.endswith(os.sep):
        path_prefix += os.sep

    synced_files = db.query(MediaItem).filter(
        MediaItem.original_path.like(path_prefix + "%")
    ).count()

    covers = db.query(MediaItem.id).filter(
        MediaItem.original_path.like(path_prefix + "%")
    ).order_by(MediaItem.date_taken.desc().nullslast(), MediaItem.id.desc()).limit(4).all()
    cover_media_ids = [c[0] for c in covers]

    return SyncedDirectoryResponse(
        id=d.id,
        path=d.path,
        is_active=d.is_active,
        created_at=d.created_at,
        updated_at=d.updated_at,
        total_files=total_files,
        synced_files=synced_files,
        cover_media_ids=cover_media_ids,
    )

from backend.schemas import DirectoryToAlbumRequest
from backend.db.models import Album

@app.post("/api/synced-directories/{dir_id}/add-to-albums")
def add_directory_to_albums(dir_id: str, req: DirectoryToAlbumRequest, db: Session = Depends(get_db)):
    """Add all media items in a synced directory to one or more albums."""
    import os
    
    directory = db.get(SyncedDirectory, dir_id)
    if not directory:
        raise HTTPException(404, "Synced directory not found")
        
    albums = db.query(Album).filter(Album.id.in_(req.album_ids)).all()
    if not albums:
        raise HTTPException(404, "No valid albums found")
        
    path_prefix = directory.path
    if not path_prefix.endswith(os.sep):
        path_prefix += os.sep
        
    media_items = db.query(MediaItem).filter(
        MediaItem.original_path.like(path_prefix + "%")
    ).all()
    
    if not media_items:
        return {"status": "success", "added": 0}
        
    added_count = 0
    for album in albums:
        existing_ids = {item.id for item in album.media_items}
        for item in media_items:
            if item.id not in existing_ids:
                album.media_items.append(item)
                added_count += 1
                
                if not album.cover_media_id:
                    album.cover_media_id = item.id
                    
    db.commit()
    return {"status": "success", "added": added_count}

@app.delete("/api/settings/synced-directories/{id}")
def remove_synced_directory(id: str, db: Session = Depends(get_db)):
    """Stop monitoring a directory and remove all synced media files from DB and cache."""
    import os
    sd = db.query(SyncedDirectory).filter_by(id=id).first()
    if not sd:
        raise HTTPException(404, "Synced directory not found")
        
    path_prefix = sd.path
    if not path_prefix.endswith(os.sep):
        path_prefix += os.sep

    # Find all media items synced from this folder
    items = db.query(MediaItem).filter(MediaItem.original_path.like(path_prefix + "%")).all()
    for item in items:
        # Delete generated thumbnail files if they exist
        if item.thumb_path:
            try:
                (settings.CACHE_DIR / item.thumb_path).unlink(missing_ok=True)
            except Exception:
                pass
        if item.preview_path:
            try:
                (settings.CACHE_DIR / item.preview_path).unlink(missing_ok=True)
            except Exception:
                pass
        db.delete(item)

    sd_path = sd.path
    # Delete the SyncedDirectory record
    db.delete(sd)
    db.commit()

    # Clean up any persisted scan tasks for this directory
    try:
        from backend.services.task_control import cleanup_stale_tasks
        active_dirs = db.query(SyncedDirectory).filter(SyncedDirectory.is_active == True).all()
        active_paths = [d.path for d in active_dirs]
        cleanup_stale_tasks(active_paths)
    except Exception as e:
        logger.error("Failed to clean up tasks on directory removal: %s", e)

    log_audit_entry(
        "sync_dir_removed", 
        "warning", 
        f"Removed directory from sync: {sd_path}. Deleted {len(items)} synced media files from database and cache."
    )

    # Update watcher observer watches
    watcher_service.remove_directory(id)
    
    return {"status": "success", "message": "Directory and all associated media removed"}


@app.post("/api/settings/factory-reset")
def factory_reset(db: Session = Depends(get_db)):
    """Delete all media items, volumes, albums, tags, synced directories from DB, clear local cache, and reset vectors."""
    import shutil
    from backend.db.engine import engine
    from backend.db.models import Base
    from backend.celery_app import celery_app
    
    logger.info("Factory reset initiated")
    
    # 1. Purge all pending Celery tasks
    try:
        celery_app.control.purge()
    except Exception as e:
        logger.warning("Failed to purge Celery tasks: %s", e)

    # 2. Clear cache directory and recreate empty structure
    try:
        if settings.CACHE_DIR.exists():
            shutil.rmtree(settings.CACHE_DIR, ignore_errors=True)
        settings.ensure_cache_dirs()
    except Exception as e:
        logger.error("Failed to clear cache directory: %s", e)

    # 3. Clear LanceDB vector database
    try:
        if settings.LANCEDB_PATH.exists():
            shutil.rmtree(settings.LANCEDB_PATH, ignore_errors=True)
    except Exception as e:
        logger.error("Failed to clear LanceDB path: %s", e)

    # 4. Clear SQLite database (drop and recreate all tables)
    try:
        # Dispose engine connections to avoid database locks
        engine.dispose()
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.error("Failed to reset SQLite database tables: %s", e)
        raise HTTPException(status_code=500, detail=f"Database reset failed: {str(e)}")

    # 5. Sync watcher service watches (clearing active watchers)
    try:
        watcher_service._sync_watches_from_db()
    except Exception as e:
        logger.error("Failed to sync watcher after reset: %s", e)

    return {"status": "success", "message": "Factory reset complete. Database and cache cleared."}


@app.get("/api/settings/audit-logs", response_model=list[AuditLogResponse])
def get_audit_logs(db: Session = Depends(get_db)):
    """Fetch the most recent 100 audit log entries."""
    from backend.db.models import AuditLog
    return db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(100).all()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Albums                                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝

from backend.db.models import Album
from backend.schemas import AlbumCreate, AlbumResponse, AlbumMediaAdd

@app.get("/api/albums", response_model=list[AlbumResponse])
def get_albums(db: Session = Depends(get_db)):
    """List all user albums."""
    return db.query(Album).order_by(Album.created_at.desc()).all()

@app.post("/api/albums", response_model=AlbumResponse)
def create_album(req: AlbumCreate, db: Session = Depends(get_db)):
    """Create a new empty album."""
    album = Album(title=req.title)
    db.add(album)
    db.commit()
    db.refresh(album)
    return album

@app.get("/api/albums/{album_id}/media", response_model=TimelineResponse)
def get_album_media(album_id: str, db: Session = Depends(get_db)):
    """Get all media items in an album."""
    album = db.get(Album, album_id)
    if not album:
        raise HTTPException(404, "Album not found")
    
    # Just return everything for now without cursor pagination since albums are usually small
    sort_col = func.coalesce(
        MediaItem.date_taken, MediaItem.date_modified, MediaItem.ingested_at
    )
    items = album.media_items.options(joinedload(MediaItem.volume)).order_by(sort_col.desc(), MediaItem.id.desc()).all()
    
    summaries = []
    for item in items:
        # Simplified volume check
        is_online = item.volume.is_online if item.volume else True
        summaries.append(
            MediaItemSummary(
                id=item.id,
                sha256=item.sha256,
                thumb_path=item.thumb_path,
                date_taken=item.date_taken,
                date_modified=item.date_modified,
                width=item.width,
                height=item.height,
                mime_type=item.mime_type,
                is_favorite=item.is_favorite,
                is_locked=item.is_locked,
                is_online=is_online,
            )
        )
        
    total_size = sum(item.file_size_bytes or 0 for item in items)

    return TimelineResponse(
        items=summaries,
        next_cursor=None,
        total_count=len(summaries),
        total_size_bytes=total_size,
    )

@app.post("/api/albums/{album_id}/media")
def add_media_to_album(album_id: str, req: AlbumMediaAdd, db: Session = Depends(get_db)):
    """Add media items to an album."""
    album = db.get(Album, album_id)
    if not album:
        raise HTTPException(404, "Album not found")
        
    for media_id in req.media_ids:
        item = db.get(MediaItem, media_id)
        if item and item not in album.media_items:
            album.media_items.append(item)
            # Set cover photo if it's the first item
            if not album.cover_media_id:
                album.cover_media_id = item.id
                
    db.commit()
    return {"status": "success"}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Tags                                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════╗

@app.get("/api/tags", response_model=list[TagWithCount])
def get_tags(source: Optional[str] = None, db: Session = Depends(get_db)):
    """List all tags with their media counts."""
    from backend.schemas import TagWithCount
    query = db.query(Tag)
    if source:
        query = query.filter(Tag.source == source)
    tags = query.all()
    results = []
    for tag in tags:
        count = tag.media_items.count()
        results.append(
            TagWithCount(
                id=tag.id,
                name=tag.name,
                source=tag.source,
                media_count=count
            )
        )
    results.sort(key=lambda t: (-t.media_count, t.name))
    return results

@app.post("/api/tags", response_model=TagWithCount)
def create_tag(req: TagCreate, db: Session = Depends(get_db)):
    """Create a new tag and immediately trigger background scan."""
    from backend.schemas import TagWithCount
    name_clean = req.name.strip()
    if not name_clean:
        raise HTTPException(400, "Tag name cannot be empty")
        
    tag = db.query(Tag).filter(Tag.name == name_clean).first()
    if tag:
        return TagWithCount(
            id=tag.id,
            name=tag.name,
            source=tag.source,
            media_count=tag.media_items.count()
        )
        
    tag = Tag(name=name_clean, source="user")
    db.add(tag)
    db.commit()
    db.refresh(tag)
    
    from backend.tasks import task_scan_tag
    task_id = f"tag-scan-{tag.id}"
    task_scan_tag.delay(tag.id, confidence_threshold=0.17, task_id=task_id)
    
    return TagWithCount(
        id=tag.id,
        name=tag.name,
        source=tag.source,
        media_count=0
    )

@app.delete("/api/tags/{tag_id}")
def delete_tag(tag_id: str, db: Session = Depends(get_db)):
    """Delete a tag."""
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(404, "Tag not found")
    db.delete(tag)
    db.commit()
    return {"status": "success"}

@app.get("/api/tags/{tag_id}/media", response_model=TimelineResponse)
def get_tag_media(tag_id: str, db: Session = Depends(get_db)):
    """Get all media items for a tag."""
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(404, "Tag not found")
        
    sort_col = func.coalesce(
        MediaItem.date_taken, MediaItem.date_modified, MediaItem.ingested_at
    )
    items = tag.media_items.options(joinedload(MediaItem.volume)).order_by(sort_col.desc(), MediaItem.id.desc()).all()
    
    summaries = []
    for item in items:
        is_online = item.volume.is_online if item.volume else True
        summaries.append(
            MediaItemSummary(
                id=item.id,
                sha256=item.sha256,
                thumb_path=item.thumb_path,
                date_taken=item.date_taken,
                date_modified=item.date_modified,
                width=item.width,
                height=item.height,
                mime_type=item.mime_type,
                is_favorite=item.is_favorite,
                is_locked=item.is_locked,
                is_online=is_online,
            )
        )
        
    total_size = sum(item.file_size_bytes or 0 for item in items)

    return TimelineResponse(
        items=summaries,
        next_cursor=None,
        total_count=len(summaries),
        total_size_bytes=total_size,
    )

@app.post("/api/tags/{tag_id}/scan", response_model=ScanEnqueuedResponse)
def trigger_tag_scan(tag_id: str, db: Session = Depends(get_db)):
    """Trigger a scan for a tag."""
    tag = db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(404, "Tag not found")
        
    from backend.tasks import task_scan_tag
    task_id = f"tag-scan-{tag.id}"
    
    task_scan_tag.delay(tag.id, confidence_threshold=0.17, task_id=task_id)
    
    return ScanEnqueuedResponse(
        task_id=task_id,
        message=f"Tag scan enqueued for '{tag.name}'",
        path=f"Tag: {tag.name}"
    )

@app.get("/api/tags/{tag_id}/scan/status", response_model=ScanStatusResponse)
def get_tag_scan_status(tag_id: str):
    """Get scan progress for a tag."""
    from backend.services.task_control import read_task_state
    task_id = f"tag-scan-{tag_id}"
    state = read_task_state(task_id)
    if not state:
        return ScanStatusResponse(
            task_id=task_id,
            status="pending",
        )
    return ScanStatusResponse.model_validate(state)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  People & Pets                                                           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@app.get("/api/people", response_model=list[PersonResponse])
def get_people(db: Session = Depends(get_db)):
    """List all people with their cover face."""
    people = db.execute(
        select(Person).order_by(Person.name)
    ).scalars().all()
    
    responses = []
    for p in people:
        count = db.execute(
            select(func.count(func.distinct(MediaItem.id)))
            .join(Face, Face.media_item_id == MediaItem.id)
            .where(Face.person_id == p.id)
            .where(MediaItem.is_archived == False)
        ).scalar() or 0
        cover_media_id = None
        if p.cover_face_id:
            cover_face = db.get(Face, p.cover_face_id)
            if cover_face:
                cover_media_id = cover_face.media_item_id
                
        responses.append(PersonResponse(
            id=p.id,
            name=p.name,
            cover_media_id=cover_media_id,
            cover_face_id=p.cover_face_id,
            face_count=count
        ))
        
    responses.sort(key=lambda x: x.face_count, reverse=True)
    return responses

@app.put("/api/people/{person_id}", response_model=PersonResponse)
def update_person(person_id: str, req: PersonUpdate, db: Session = Depends(get_db)):
    """Rename a person."""
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404, "Person not found")
    person.name = req.name
    db.commit()
    db.refresh(person)
    
    count = db.execute(select(func.count(Face.id)).where(Face.person_id == person.id)).scalar() or 0
    cover_media_id = None
    if person.cover_face_id:
        cover_face = db.get(Face, person.cover_face_id)
        if cover_face:
            cover_media_id = cover_face.media_item_id
            
    return PersonResponse(
        id=person.id,
        name=person.name,
        cover_media_id=cover_media_id,
        cover_face_id=person.cover_face_id,
        face_count=count
    )

@app.get("/api/people/{person_id}/media", response_model=TimelineResponse)
def get_person_media(person_id: str, db: Session = Depends(get_db)):
    """Get all media items containing a specific person."""
    person = db.get(Person, person_id)
    if not person:
        raise HTTPException(404, "Person not found")
        
    sort_col = func.coalesce(
        MediaItem.date_taken, MediaItem.date_modified, MediaItem.ingested_at
    )
    
    # Query media items that have a face belonging to this person
    items = db.execute(
        select(MediaItem)
        .join(Face, Face.media_item_id == MediaItem.id)
        .where(Face.person_id == person_id)
        .where(MediaItem.is_archived == False)
        .group_by(MediaItem.id)
        .order_by(sort_col.desc(), MediaItem.id.desc())
    ).scalars().all()
    
    summaries = []
    for item in items:
        is_online = item.volume.is_online if item.volume else True
        summaries.append(
            MediaItemSummary(
                id=item.id,
                sha256=item.sha256,
                thumb_path=item.thumb_path,
                date_taken=item.date_taken,
                date_modified=item.date_modified,
                width=item.width,
                height=item.height,
                mime_type=item.mime_type,
                is_favorite=item.is_favorite,
                is_locked=item.is_locked,
                is_online=is_online,
            )
        )
        
    total_size = sum(item.file_size_bytes or 0 for item in items)

    return TimelineResponse(
        items=summaries,
        next_cursor=None,
        total_count=len(summaries),
        total_size_bytes=total_size,
    )

@app.post("/api/people/bulk-delete")
def bulk_delete_people_pets(req: BulkDeletePeoplePetsRequest, db: Session = Depends(get_db)):
    """Bulk delete people and optionally pets tags."""
    if req.person_ids:
        people = db.execute(select(Person).where(Person.id.in_(req.person_ids))).scalars().all()
        for p in people:
            db.delete(p)
    if req.delete_pets:
        tags = db.execute(select(Tag).where(Tag.name.in_(["Dog", "Cat"]))).scalars().all()
        for t in tags:
            db.delete(t)
    db.commit()
    return {"status": "success"}

@app.get("/api/faces/{face_id}/crop")
def get_face_crop(face_id: str, db: Session = Depends(get_db)):
    """Return the cropped face image, using cache if available."""
    import os
    from PIL import Image

    face = db.get(Face, face_id)
    if not face:
        raise HTTPException(404, "Face not found")
        
    media_item = db.get(MediaItem, face.media_item_id)
    if not media_item:
        raise HTTPException(404, "Media item not found")
        
    # Check cache first
    face_cache_dir = settings.CACHE_DIR / "faces"
    face_cache_dir.mkdir(parents=True, exist_ok=True)
    crop_path = face_cache_dir / f"{face_id}.jpg"
    
    if crop_path.exists():
        return FileResponse(crop_path, media_type="image/jpeg")
        
    # Generate crop
    try:
        if not os.path.exists(media_item.original_path):
            raise HTTPException(404, f"Original file not found: {media_item.original_path}")
            
        with Image.open(media_item.original_path) as img:
            # Crop using the bounding box
            # PIL crop expects (left, upper, right, lower)
            # Make sure coordinates are within bounds
            width, height = img.size
            
            box_width = face.box_x2 - face.box_x1
            box_height = face.box_y2 - face.box_y1
            
            pad_x = box_width * 0.20
            pad_y = box_height * 0.20
            
            x1 = max(0, min(face.box_x1 - pad_x, width))
            y1 = max(0, min(face.box_y1 - pad_y, height))
            x2 = max(0, min(face.box_x2 + pad_x, width))
            y2 = max(0, min(face.box_y2 + pad_y, height))
            
            # If the box is invalid/collapsed, use full image
            if x2 <= x1 or y2 <= y1:
                cropped = img
            else:
                cropped = img.crop((x1, y1, x2, y2))
                
            # Resize to a standard thumbnail size, e.g. 160x160
            cropped = cropped.resize((160, 160), Image.Resampling.LANCZOS)
            cropped.convert("RGB").save(crop_path, "JPEG", quality=90)
            
        return FileResponse(crop_path, media_type="image/jpeg")
    except Exception as e:
        logger.exception("Failed to generate face crop: %s", e)
        raise HTTPException(500, f"Error generating crop: {str(e)}")

@app.get("/api/pets", response_model=TimelineResponse)
def get_pets(db: Session = Depends(get_db)):
    """Get all media items tagged with 'Dog' or 'Cat'."""
    sort_col = func.coalesce(
        MediaItem.date_taken, MediaItem.date_modified, MediaItem.ingested_at
    )
    
    items = db.execute(
        select(MediaItem)
        .join(MediaItem.tags)
        .where(Tag.name.in_(["Dog", "Cat"]))
        .order_by(sort_col.desc(), MediaItem.id.desc())
    ).scalars().unique().all()
    
    summaries = []
    for item in items:
        is_online = item.volume.is_online if item.volume else True
        summaries.append(
            MediaItemSummary(
                id=item.id,
                sha256=item.sha256,
                thumb_path=item.thumb_path,
                date_taken=item.date_taken,
                date_modified=item.date_modified,
                width=item.width,
                height=item.height,
                mime_type=item.mime_type,
                is_favorite=item.is_favorite,
                is_locked=item.is_locked,
                is_online=is_online,
            )
        )
        
    total_size = sum(item.file_size_bytes or 0 for item in items)

    return TimelineResponse(
        items=summaries,
        next_cursor=None,
        total_count=len(summaries),
        total_size_bytes=total_size,
    )

@app.post("/api/ml/cluster_faces")
def trigger_cluster_faces(db: Session = Depends(get_db)):
    """Manually trigger face clustering."""
    from backend.services.ml import cluster_faces
    result = cluster_faces(db)
    return result


@app.post("/api/settings/generate-thumbnails", response_model=dict)
def generate_missing_thumbnails():
    """Manually trigger background thumbnail generation for all items missing thumbnails."""
    from backend.tasks import task_generate_thumbnails
    from backend.db.engine import log_audit_entry
    
    try:
        result = task_generate_thumbnails.delay()
        log_audit_entry(
            "generate_thumbnails",
            "info",
            f"Manually triggered background thumbnail generation task: {result.id}"
        )
        return {"status": "success", "message": "Thumbnail generation task enqueued", "task_id": result.id}
    except Exception as e:
        logger.error("Failed to enqueue thumbnail generation: %s", e)
        # Try inline generation as fallback
        try:
            from backend.services.thumbnails import generate_thumbnails_batch
            from backend.db.engine import SessionLocal
            from backend.db.models import MediaItem
            
            with SessionLocal() as session:
                items = session.query(MediaItem).filter(
                    MediaItem.thumb_path.is_(None),
                    (MediaItem.mime_type.like("image/%") | MediaItem.mime_type.like("video/%")),
                ).all()
                
                if not items:
                    return {"status": "success", "message": "No items need thumbnail generation"}
                
                work = [(item.original_path, item.sha256) for item in items]
                results = generate_thumbnails_batch(work)
                
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
                            item.phash = tr.phash
                            db_updated = True
                        if db_updated:
                            updated += 1
                
                session.commit()
                log_audit_entry(
                    "generate_thumbnails",
                    "success",
                    f"Inline thumbnail generation complete: {updated}/{len(items)} items"
                )
                return {"status": "success", "message": f"Generated thumbnails for {updated}/{len(items)} items", "generated": updated, "total": len(items)}
        except Exception as inline_exc:
            logger.error("Inline thumbnail generation also failed: %s", inline_exc)
            raise HTTPException(500, f"Thumbnail generation failed: {str(inline_exc)}")
