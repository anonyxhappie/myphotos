"""
Google Takeout Parser
=====================

Parses a Google Takeout export directory and merges the companion JSON
metadata files with the actual media files before ingesting them into
the database.

Google Takeout structure::

    Takeout/
    └── Google Photos/
        ├── Album Name 1/
        │   ├── IMG_0001.jpg
        │   ├── IMG_0001.jpg.json        ← companion metadata
        │   ├── IMG_0002.heic
        │   └── IMG_0002.heic.json
        ├── Album Name 2/
        │   └── ...
        └── Photos from 2024/
            └── ...

The JSON companion file contains:
    • ``photoTakenTime``  → epoch timestamp (more reliable than EXIF)
    • ``geoData``         → latitude, longitude, altitude
    • ``geoDataExif``     → GPS from EXIF (often less accurate)
    • ``description``     → user caption
    • ``url``             → original Google Photos URL
    • ``imageViews``      → view count
    • ``favorited``       → boolean (mapped from ``FAVORITE`` key)
    • ``archived``        → boolean
    • ``trashed``         → boolean
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.config import settings
from backend.db.batch import MediaItemDict, batch_insert_media_items
from backend.db.models import Album, media_albums
from backend.services.scanner import ScanResult, compute_phash, compute_sha256, extract_exif
from backend.services.thumbnails import generate_preview, generate_thumbnail
from backend.services.volumes import get_volume_for_path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON companion finder
# ---------------------------------------------------------------------------
def _find_companion_json(media_path: Path) -> Optional[Path]:
    """Locate the Google Takeout companion JSON for a media file.

    Google uses several naming patterns:
        1. ``IMG_0001.jpg.json``          ← most common
        2. ``IMG_0001.json``              ← sometimes (no media ext)
        3. ``IMG_0001(1).jpg.json``       ← edited copies
        4. ``IMG_0001.jpg(1).json``       ← another variant
    """
    # Pattern 1: <filename>.<ext>.json
    candidate = media_path.parent / f"{media_path.name}.json"
    if candidate.exists():
        return candidate

    # Pattern 2: <filename_without_ext>.json
    candidate = media_path.parent / f"{media_path.stem}.json"
    if candidate.exists():
        return candidate

    # Pattern 3: Try with parenthetical variants
    for i in range(1, 10):
        # IMG_0001(1).jpg.json
        candidate = media_path.parent / f"{media_path.stem}({i}){media_path.suffix}.json"
        if candidate.exists():
            return candidate
        # IMG_0001.jpg(1).json
        candidate = media_path.parent / f"{media_path.name}({i}).json"
        if candidate.exists():
            return candidate

    return None


# ---------------------------------------------------------------------------
# JSON metadata parser
# ---------------------------------------------------------------------------
def _parse_takeout_json(json_path: Path) -> dict[str, Any]:
    """Parse a Google Takeout companion JSON file.

    Returns a flat dict with keys matching ``MediaItem`` column names.
    """
    result: dict[str, Any] = {}

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to parse Takeout JSON %s: %s", json_path, exc)
        return result

    # Photo taken time (epoch seconds — very reliable)
    photo_taken = data.get("photoTakenTime", {})
    timestamp = photo_taken.get("timestamp")
    if timestamp:
        try:
            result["date_taken"] = datetime.fromtimestamp(
                int(timestamp), tz=timezone.utc
            )
        except (ValueError, OSError):
            pass

    # GPS — prefer geoData over geoDataExif (Google's post-processed
    # location is more accurate than raw EXIF GPS)
    geo = data.get("geoData", {})
    if not geo or (geo.get("latitude", 0) == 0 and geo.get("longitude", 0) == 0):
        geo = data.get("geoDataExif", {})

    lat = geo.get("latitude")
    lng = geo.get("longitude")
    alt = geo.get("altitude")

    if lat and lat != 0.0:
        result["latitude"] = float(lat)
    if lng and lng != 0.0:
        result["longitude"] = float(lng)
    if alt and alt != 0.0:
        result["altitude_m"] = float(alt)

    # Description / caption
    desc = data.get("description", "")
    if desc:
        result["google_description"] = desc

    # Original Google Photos URL
    url = data.get("url", "")
    if url:
        result["google_url"] = url

    # Favorited / Archived / Trashed
    # Google uses "FAVORITE" key in an odd structure
    if data.get("favorited") or data.get("FAVORITE"):
        result["is_favorite"] = True
    if data.get("archived"):
        result["is_archived"] = True
    if data.get("trashed"):
        result["is_trashed"] = True

    return result


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------
def _update_task_progress(
    task_id: str | None,
    status: str,
    total_found: int = 0,
    processed: int = 0,
    new_inserted: int = 0,
    duplicates_skipped: int = 0,
    errors: int = 0,
    current_file: str | None = None,
    start_time: float | None = None,
) -> None:
    from backend.services.task_control import write_task_progress

    write_task_progress(
        task_id,
        status,
        total_found=total_found,
        processed=processed,
        new_inserted=new_inserted,
        duplicates_skipped=duplicates_skipped,
        errors=errors,
        current_file=current_file,
        start_time=start_time,
    )


def parse_takeout_directory(
    takeout_root: str | Path,
    session: Session,
    *,
    generate_thumbs: bool = True,
    task_id: str | None = None,
    resume_after: str | None = None,
    initial_progress: dict[str, Any] | None = None,
) -> ScanResult:
    """Parse a Google Takeout export and ingest all media files.

    Parameters
    ----------
    takeout_root:
        Path to the Takeout directory (e.g. ``/path/to/Takeout``).
        Can also point directly to the ``Google Photos`` subdirectory.
    session:
        SQLAlchemy session.
    generate_thumbs:
        Generate WebP thumbnails inline.
    task_id:
        UUID of the scan task for progress tracking.

    Returns
    -------
    ScanResult
        Summary of the import.
    """
    import time
    initial_progress = initial_progress or {}
    start_time = float(initial_progress.get("start_time") or time.time())
    last_update_time = 0.0
    last_update_processed = 0
    root = Path(takeout_root).resolve()

    # Auto-detect the Google Photos subdirectory
    google_photos_dir = root / "Google Photos"
    if google_photos_dir.is_dir():
        root = google_photos_dir

    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    result = ScanResult(
        root_path=str(root),
        new_inserted=int(initial_progress.get("new_inserted", 0)),
        duplicates_skipped=int(initial_progress.get("duplicates_skipped", 0)),
        errors=int(initial_progress.get("errors", 0)),
    )

    import os

    media_files: list[Path] = []
    for dirpath_str, dirs, filenames in os.walk(root):
        # Ignore hidden directories (starting with '.')
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        dirs.sort()
        for fname in sorted(filenames):
            # Ignore hidden files (starting with '.') and macOS shadow/metadata files (starting with '._')
            if fname.startswith('.'):
                continue
            if fname.endswith(".json"):
                continue
            if Path(fname).suffix.lower() in settings.SUPPORTED_EXTENSIONS:
                media_files.append(Path(dirpath_str) / fname)
    total_files = len(media_files)

    start_index = 0
    if resume_after:
        try:
            start_index = next(
                index + 1 for index, file_path in enumerate(media_files) if str(file_path) == resume_after
            )
        except StopIteration:
            logger.warning("Takeout resume cursor no longer exists; rescanning with dedup: %s", resume_after)
            start_index = 0

    # Resolve volume
    volume = get_volume_for_path(session, root)
    volume_id = volume.id if volume else None

    # Pre-load existing items metadata
    from backend.services.scanner import _load_existing_items_metadata

    existing_items = _load_existing_items_metadata(session)

    if generate_thumbs:
        settings.ensure_cache_dirs()

    # Track albums: folder_name → album_id
    album_cache: dict[str, str] = {}
    batch_buffer: list[MediaItemDict] = []
    # Map sha256 → album folder name for post-insert album linking
    media_album_links: list[tuple[str, str]] = []  # (media_id, album_id)
    processed = start_index
    live_batch_size = max(1, min(settings.SCAN_BATCH_SIZE, 20))

    def flush_batch() -> None:
        if not batch_buffer:
            return
        inserted = batch_insert_media_items(
            session, batch_buffer, batch_size=live_batch_size
        )
        result.new_inserted += inserted
        batch_buffer.clear()

    def flush_album_links() -> None:
        if not media_album_links:
            return
        session.execute(
            media_albums.insert().prefix_with("OR IGNORE"),
            [
                {"media_item_id": media_id, "album_id": album_id}
                for media_id, album_id in media_album_links
            ],
        )
        session.commit()
        media_album_links.clear()

    # Report initial status
    _update_task_progress(
        task_id,
        "running",
        total_found=total_files,
        processed=processed,
        new_inserted=result.new_inserted,
        duplicates_skipped=result.duplicates_skipped,
        errors=result.errors,
        current_file=resume_after,
        start_time=start_time,
    )

    from backend.services.task_control import clear_task_control, pause_requested

    def report_progress_if_needed(current_path: Path) -> None:
        nonlocal last_update_time, last_update_processed
        if task_id:
            now = time.time()
            if (now - last_update_time >= 3.0 and processed - last_update_processed >= 100) or processed == total_files:
                _update_task_progress(
                    task_id,
                    "running",
                    total_found=total_files,
                    processed=processed,
                    new_inserted=result.new_inserted,
                    duplicates_skipped=result.duplicates_skipped,
                    errors=result.errors,
                    current_file=str(current_path),
                    start_time=start_time,
                )
                last_update_time = time.time()
                last_update_processed = processed

    for file_path in media_files[start_index:]:
            if pause_requested(task_id):
                flush_batch()
                flush_album_links()
                result.total_found = processed
                result.paused = True
                clear_task_control(task_id)
                _update_task_progress(
                    task_id,
                    "paused",
                    total_found=total_files,
                    processed=processed,
                    new_inserted=result.new_inserted,
                    duplicates_skipped=result.duplicates_skipped,
                    errors=result.errors,
                    current_file=str(media_files[processed - 1]) if processed > 0 else resume_after,
                    start_time=start_time,
                )
                logger.info("Takeout import paused at %d / %d files", processed, total_files)
                return result

            dirpath = file_path.parent
            folder_name = dirpath.name
            fname = file_path.name
            ext = file_path.suffix.lower()
            processed += 1

            # Log current file to rotating log file
            logger.info("Processing file: %s", file_path)

            try:
                # 1. SHA-256
                sha256 = compute_sha256(file_path)

                if sha256 in existing_items:
                    has_thumb, has_preview = existing_items[sha256]
                    updated_fields = {}
                    
                    if generate_thumbs and ext in settings.SUPPORTED_EXTENSIONS:
                        if not has_thumb:
                            thumb_path = generate_thumbnail(file_path, sha256)
                            if thumb_path:
                                updated_fields["thumb_path"] = thumb_path
                        if not has_preview:
                            preview_path = generate_preview(file_path, sha256)
                            if preview_path:
                                updated_fields["preview_path"] = preview_path
                        if ext in settings.SUPPORTED_VIDEO_EXTENSIONS and "proxy_path" not in updated_fields:
                            from backend.services.thumbnails import _generate_video_proxy
                            proxy_path = _generate_video_proxy(file_path, sha256)
                            if proxy_path:
                                updated_fields["proxy_path"] = proxy_path
                                
                    if updated_fields:
                        from backend.db.models import MediaItem
                        session.query(MediaItem).filter(MediaItem.sha256 == sha256).update(updated_fields)
                        session.commit()
                        existing_items[sha256] = (
                            has_thumb or "thumb_path" in updated_fields,
                            has_preview or "preview_path" in updated_fields
                        )

                    result.duplicates_skipped += 1
                    report_progress_if_needed(file_path)
                    continue

                existing_items[sha256] = (
                    generate_thumbs and ext in settings.SUPPORTED_EXTENSIONS,
                    generate_thumbs and ext in settings.SUPPORTED_EXTENSIONS
                )

                # 2. pHash - Defer if generate_thumbs is False to speed up scanning
                phash = compute_phash(file_path) if generate_thumbs else None

                # 3. EXIF metadata from the image itself
                exif = extract_exif(file_path)

                # 4. Google Takeout JSON metadata (takes priority)
                json_path = _find_companion_json(file_path)
                takeout_meta: dict[str, Any] = {}
                if json_path:
                    takeout_meta = _parse_takeout_json(json_path)

                # Merge: JSON overrides EXIF for date_taken and GPS
                merged = {**exif, **takeout_meta}

                # 5. File metadata
                stat = file_path.stat()
                import mimetypes as _mt

                mime_type, _ = _mt.guess_type(str(file_path))

                # 6. Thumbnails
                thumb_path = None
                preview_path = None
                proxy_path = None
                if generate_thumbs and ext in settings.SUPPORTED_EXTENSIONS:
                    thumb_path = generate_thumbnail(file_path, sha256)
                    preview_path = generate_preview(file_path, sha256)
                    if ext in settings.SUPPORTED_VIDEO_EXTENSIONS:
                        from backend.services.thumbnails import _generate_video_proxy
                        proxy_path = _generate_video_proxy(file_path, sha256)

                # 7. Build record
                media_id = str(uuid.uuid4())
                record: MediaItemDict = {
                    "id": media_id,
                    "sha256": sha256,
                    "phash": phash,
                    "volume_id": volume_id,
                    "original_path": str(file_path),
                    "filename": fname,
                    "mime_type": mime_type,
                    "file_size_bytes": stat.st_size,
                    "thumb_path": thumb_path,
                    "preview_path": preview_path,
                    "proxy_path": proxy_path,
                    "date_modified": datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ),
                    **merged,
                }
                batch_buffer.append(record)

                # 8. Album association (folder name = album title)
                # Skip generic "Photos from YYYY" folders
                if folder_name and not folder_name.startswith("Photos from "):
                    if folder_name not in album_cache:
                        existing_album = session.query(Album).filter(Album.title == folder_name).first()
                        if existing_album:
                            album_id = existing_album.id
                        else:
                            album_id = str(uuid.uuid4())
                            album = Album(id=album_id, title=folder_name)
                            session.add(album)
                            session.flush()
                        album_cache[folder_name] = album_id
                    media_album_links.append((media_id, album_cache[folder_name]))

                # Flush batch
                if len(batch_buffer) >= live_batch_size:
                    flush_batch()

            except Exception as exc:
                result.errors += 1
                result.error_details.append(f"{file_path}: {exc}")
                logger.warning("Takeout parse error: %s: %s", file_path, exc)

            report_progress_if_needed(file_path)

    # Flush remaining
    flush_batch()
    result.total_found = total_files

    # Insert album associations
    if media_album_links:
        try:
            link_count = len(media_album_links)
            flush_album_links()
            logger.info("Linked %d media items to %d albums", link_count, len(album_cache))
        except Exception:
            session.rollback()
            logger.exception("Failed to insert album associations")

    # Report final scan progress state
    if task_id:
        _update_task_progress(
            task_id,
            "running",
            total_found=total_files,
            processed=processed,
            new_inserted=result.new_inserted,
            duplicates_skipped=result.duplicates_skipped,
            errors=result.errors,
            start_time=start_time,
        )

    logger.info(
        "Takeout parse complete: found=%d, inserted=%d, dupes=%d, errors=%d, albums=%d",
        result.total_found,
        result.new_inserted,
        result.duplicates_skipped,
        result.errors,
        len(album_cache),
    )
    return result
