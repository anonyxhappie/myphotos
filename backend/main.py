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
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db.engine import get_db, log_audit_entry
from backend.db.models import Base, MediaItem, Volume
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
    logger.info("MyPhotos API ready — DB at %s", engine.url)
    
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

@app.get("/api/timeline", response_model=TimelineResponse)
def get_timeline(
    cursor: Optional[str] = Query(None, description="ISO datetime cursor from previous page"),
    limit: int = Query(settings.TIMELINE_PAGE_SIZE, ge=1, le=500),
    favorites_only: bool = Query(False),
    videos_only: bool = Query(False),
    locked_only: bool = Query(False),
    sort: str = Query("date_taken"),
    db: Session = Depends(get_db),
) -> TimelineResponse:
    """Return a page of media items sorted by date_taken or ingested_at DESC.

    Uses cursor-based pagination (keyset pagination) for stable,
    efficient paging over millions of rows — no OFFSET needed.
    """
    query = select(MediaItem)

    # Base filters
    if locked_only:
        query = query.where(MediaItem.is_locked == True)
    else:
        query = query.where(MediaItem.is_locked == False)

    if favorites_only:
        query = query.where(MediaItem.is_favorite == True)
    
    if videos_only:
        query = query.where(MediaItem.mime_type.like("video/%"))

    # Total count (respecting filters)
    total = db.scalar(select(func.count(MediaItem.id)).select_from(query.subquery()))

    # Order By
    sort_col = (
        MediaItem.ingested_at
        if sort == "ingested_at"
        else func.coalesce(
            MediaItem.date_taken, MediaItem.date_modified, MediaItem.ingested_at
        )
    )
    query = query.order_by(sort_col.desc(), MediaItem.id.desc())

    # Apply cursor filter
    if cursor:
        from datetime import datetime
        try:
            cursor_dt = datetime.fromisoformat(cursor)
        except ValueError:
            raise HTTPException(400, f"Invalid cursor format: {cursor}")
        
        query = query.where(
            (sort_col < cursor_dt)
            | ((sort_col == cursor_dt) & (MediaItem.id < cursor))
        )

    query = query.limit(limit + 1)  # Fetch one extra to determine if there's a next page
    rows = db.execute(query).scalars().all()

    # Determine next cursor
    has_next = len(rows) > limit
    items = rows[:limit]
    next_cursor = None
    if has_next and items:
        last = items[-1]
        val = last.date_taken or last.date_modified or last.ingested_at
        next_cursor = val.isoformat() if val else last.id

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

    return TimelineResponse(
        items=summaries,
        next_cursor=next_cursor,
        total_count=total or 0,
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
    """Bulk delete media items from database, cache files, and LanceDB vectors."""
    from backend.db.vector import get_clip_table, get_face_table
    
    if not req.media_ids:
        return {"status": "success", "deleted_count": 0}
        
    items = db.query(MediaItem).filter(MediaItem.id.in_(req.media_ids)).all()
    deleted_count = len(items)
    
    for item in items:
        # 1. Delete generated thumbnails/previews
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
        
        # 2. Delete database record
        db.delete(item)
        
    # Commit SQLite deletion
    db.commit()
    
    # 3. Delete from LanceDB vector index
    try:
        clip_table = get_clip_table()
        # LanceDB SQL filter syntax
        clip_table.delete(f"media_id in {tuple(req.media_ids) if len(req.media_ids) > 1 else f'(\"{req.media_ids[0]}\")'}")
    except Exception as e:
         logger.warning("Failed to delete from clip vector table: %s", e)
         
    try:
        face_table = get_face_table()
        face_table.delete(f"media_id in {tuple(req.media_ids) if len(req.media_ids) > 1 else f'(\"{req.media_ids[0]}\")'}")
    except Exception as e:
         logger.warning("Failed to delete from face vector table: %s", e)
         
    log_audit_entry("file_deleted", "warning", f"Bulk deleted {deleted_count} media item(s)")
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
    if not full_path.is_file():
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
    return ScanEnqueuedResponse(task_id=task_id, message=f"Scan enqueued for {scan_path}")


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
    return ScanEnqueuedResponse(task_id=task_id, message=f"Takeout import enqueued for {takeout_path}")


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
    if not path or not Path(path).is_dir():
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


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  Search & ML Endpoints                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@app.post("/api/ml/start", response_model=ScanEnqueuedResponse)
def start_ml_pipeline() -> ScanEnqueuedResponse:
    """Enqueue the background ML pipeline for embeddings."""
    from backend.tasks import task_process_ml_pipeline
    
    result = task_process_ml_pipeline.delay()
    return ScanEnqueuedResponse(task_id=result.id, message="ML pipeline started")

@app.get("/api/search", response_model=TimelineResponse)
def search_media(q: str = Query(..., description="Search query"), db: Session = Depends(get_db)) -> TimelineResponse:
    """Search for media items semantically or by metadata."""
    from backend.services.ml import search_semantic
    
    # Get media IDs from LanceDB
    media_ids = search_semantic(q, limit=50)
    
    if not media_ids:
        return TimelineResponse(items=[], next_cursor=None, total_count=0)
        
    # Fetch metadata for those IDs
    query = select(MediaItem).where(MediaItem.id.in_(media_ids))
    rows = db.execute(query).scalars().all()
    
    # Sort them in the order of the search results (which are sorted by similarity)
    items_by_id = {item.id: item for item in rows}
    items = [items_by_id[mid] for mid in media_ids if mid in items_by_id]
    
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

    return TimelineResponse(
        items=summaries,
        next_cursor=None,
        total_count=len(summaries),
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
    return {
        "status": "healthy",
        "db_connected": row == 1,
        "total_media_items": total_media,
        "total_volumes": total_volumes,
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

        res.append(
            SyncedDirectoryResponse(
                id=d.id,
                path=d.path,
                is_active=d.is_active,
                created_at=d.created_at,
                updated_at=d.updated_at,
                total_files=total_files,
                synced_files=synced_files,
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
    )

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

    # Delete the SyncedDirectory record
    db.delete(sd)
    db.commit()

    log_audit_entry(
        "sync_dir_removed", 
        "warning", 
        f"Removed directory from sync: {sd.path}. Deleted {len(items)} synced media files from database and cache."
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
    items = album.media_items.order_by(sort_col.desc(), MediaItem.id.desc()).all()
    
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
        
    return TimelineResponse(
        items=summaries,
        next_cursor=None,
        total_count=len(summaries),
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
