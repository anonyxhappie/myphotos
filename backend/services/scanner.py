"""
File Scanner & Ingestion Pipeline
==================================

Recursively walks a directory tree, computes content hashes, extracts
EXIF metadata, generates thumbnails, and batch-inserts everything into
the SQLite database.

Pipeline per file:
    1. Filter by extension (skip unsupported types).
    2. SHA-256 content hash → skip if already in DB (exact dedup).
    3. pHash (images only) → stored for near-duplicate detection.
    4. EXIF extraction → date_taken, GPS, camera info, dimensions.
    5. Thumbnail + preview generation → WebP in .local_cache.
    6. Accumulate into batch → flush every SCAN_BATCH_SIZE files.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from PIL import Image
from PIL.ExifTags import GPS as GPS_TAGS
from PIL.ExifTags import TAGS as EXIF_TAGS
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db.batch import MediaItemDict, batch_insert_media_items
from backend.db.models import MediaItem
from backend.services.thumbnails import generate_preview, generate_thumbnail
from backend.services.volumes import get_volume_for_path

logger = logging.getLogger(__name__)

# Try to import imagehash for perceptual hashing
try:
    import imagehash

    _PHASH_AVAILABLE = True
except ImportError:
    _PHASH_AVAILABLE = False
    logger.info("imagehash not installed — perceptual hashing disabled")


# ---------------------------------------------------------------------------
# Scan result
# ---------------------------------------------------------------------------
@dataclass
class ScanResult:
    """Summary of a directory scan."""

    root_path: str
    total_found: int = 0
    new_inserted: int = 0
    duplicates_skipped: int = 0
    errors: int = 0
    error_details: list[str] = field(default_factory=list)
    paused: bool = False


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------
def compute_sha256(file_path: str | Path) -> str:
    """Compute a fast pseudo-SHA-256 hash using file metadata (size, mtime)
    and a sample of the file content (first and last 100 KiB).
    
    This avoids reading the entire file, which is extremely slow on
    external drives, network shares, or for large video files.
    """
    path = Path(file_path)
    try:
        stat = path.stat()
        size = stat.st_size
        mtime = stat.st_mtime
        
        # We hash the metadata first
        h = hashlib.sha256()
        h.update(f"{size}_{mtime}".encode())
        
        # If the file is small, we read it completely
        if size <= 200_000:
            with open(path, "rb") as f:
                h.update(f.read())
        else:
            # Otherwise, read first 100 KiB and last 100 KiB
            with open(path, "rb") as f:
                h.update(f.read(100_000))
                f.seek(size - 100_000)
                h.update(f.read(100_000))
        return h.hexdigest()
    except Exception:
        # Fallback to standard full file hash if stat or seek fails
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()


def compute_phash(file_path: str | Path) -> Optional[str]:
    """Compute perceptual hash for an image file.

    Returns the hex string of the 64-bit pHash, or None for videos
    or if imagehash is not installed.
    """
    if not _PHASH_AVAILABLE:
        return None

    ext = Path(file_path).suffix.lower()
    if ext not in settings.SUPPORTED_IMAGE_EXTENSIONS:
        return None

    try:
        with Image.open(file_path) as img:
            return str(imagehash.phash(img))
    except Exception as exc:
        logger.debug("pHash failed for %s: %s", file_path, exc)
        return None


# ---------------------------------------------------------------------------
# EXIF extraction
# ---------------------------------------------------------------------------
def _dms_to_decimal(dms_tuple, ref: str) -> Optional[float]:
    """Convert EXIF GPS DMS (degrees, minutes, seconds) to decimal degrees."""
    try:
        degrees = float(dms_tuple[0])
        minutes = float(dms_tuple[1])
        seconds = float(dms_tuple[2])
        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if ref in ("S", "W"):
            decimal = -decimal
        return decimal
    except (TypeError, IndexError, ValueError, ZeroDivisionError):
        return None


def extract_exif(file_path: str | Path) -> dict[str, Any]:
    """Extract relevant EXIF fields from an image file.

    Returns a flat dict with keys matching ``MediaItem`` column names.
    Non-image files or files without EXIF return an empty dict.
    """
    ext = Path(file_path).suffix.lower()
    if ext not in settings.SUPPORTED_IMAGE_EXTENSIONS:
        return {}

    result: dict[str, Any] = {}

    try:
        with Image.open(file_path) as img:
            result["width"] = img.width
            result["height"] = img.height

            exif_data = img.getexif()
            if not exif_data:
                return result

            # Map numeric EXIF tags to human-readable names
            decoded: dict[str, Any] = {}
            for tag_id, value in exif_data.items():
                tag_name = EXIF_TAGS.get(tag_id, str(tag_id))
                decoded[tag_name] = value

            # Date taken
            date_str = decoded.get("DateTimeOriginal") or decoded.get("DateTime")
            if date_str and isinstance(date_str, str):
                try:
                    # EXIF format: "2024:01:15 14:30:00"
                    dt = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                    result["date_taken"] = dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            # Camera info
            if "Make" in decoded:
                result["camera_make"] = str(decoded["Make"]).strip()
            if "Model" in decoded:
                result["camera_model"] = str(decoded["Model"]).strip()
            if "LensModel" in decoded:
                result["lens_model"] = str(decoded["LensModel"]).strip()
            if "ISOSpeedRatings" in decoded:
                result["iso"] = int(decoded["ISOSpeedRatings"])
            if "FocalLength" in decoded:
                fl = decoded["FocalLength"]
                result["focal_length_mm"] = float(fl) if fl else None
            if "FNumber" in decoded:
                fn = decoded["FNumber"]
                result["aperture"] = float(fn) if fn else None
            if "ExposureTime" in decoded:
                et = decoded["ExposureTime"]
                if et:
                    result["exposure_time"] = str(et)

            # GPS data
            gps_ifd = exif_data.get_ifd(0x8825)  # GPSInfo IFD
            if gps_ifd:
                gps_decoded: dict[str, Any] = {}
                for tag_id, value in gps_ifd.items():
                    tag_name = GPS_TAGS.get(tag_id, str(tag_id))
                    gps_decoded[tag_name] = value

                lat = _dms_to_decimal(
                    gps_decoded.get("GPSLatitude"),
                    gps_decoded.get("GPSLatitudeRef", "N"),
                )
                lng = _dms_to_decimal(
                    gps_decoded.get("GPSLongitude"),
                    gps_decoded.get("GPSLongitudeRef", "E"),
                )
                if lat is not None:
                    result["latitude"] = lat
                if lng is not None:
                    result["longitude"] = lng

                alt = gps_decoded.get("GPSAltitude")
                if alt is not None:
                    try:
                        result["altitude_m"] = float(alt)
                    except (TypeError, ValueError):
                        pass

    except Exception as exc:
        logger.debug("EXIF extraction failed for %s: %s", file_path, exc)

    return result


# ---------------------------------------------------------------------------
# Directory scanner
# ---------------------------------------------------------------------------
def _load_existing_items_metadata(session: Session) -> dict[str, tuple[bool, bool]]:
    """Load metadata (has_thumb, has_preview) for existing items keyed by SHA-256.

    For a library of 1M photos this dict uses ~80-100 MB of RAM, which is acceptable.
    """
    stmt = select(MediaItem.sha256, MediaItem.thumb_path, MediaItem.preview_path, MediaItem.proxy_path)
    rows = session.execute(stmt).all()
    return {
        row[0]: (row[1] is not None, row[2] is not None)
        for row in rows
    }



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


def scan_directory(
    root_path: str | Path,
    session: Session,
    *,
    generate_thumbs: bool = True,
    task_id: str | None = None,
    resume_after: str | None = None,
    initial_progress: dict[str, Any] | None = None,
) -> ScanResult:
    """Scan a directory tree for media files and ingest them.

    Parameters
    ----------
    root_path:
        Absolute path to the directory to scan.
    session:
        SQLAlchemy session (caller manages lifecycle).
    generate_thumbs:
        If True, generate WebP thumbnails and previews inline.
        Set to False to defer thumbnail generation to a Huey task.
    task_id:
        UUID of the scan task for progress tracking.

    Returns
    -------
    ScanResult
        Summary with counts of found/inserted/skipped/errored files.
    """
    import time
    initial_progress = initial_progress or {}
    start_time = float(initial_progress.get("start_time") or time.time())
    last_update_time = 0.0
    last_update_processed = 0
    root = Path(root_path).resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    result = ScanResult(
        root_path=str(root),
        new_inserted=int(initial_progress.get("new_inserted", 0)),
        duplicates_skipped=int(initial_progress.get("duplicates_skipped", 0)),
        errors=int(initial_progress.get("errors", 0)),
    )

    media_files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Ignore hidden directories (starting with '.')
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        dirnames.sort()
        for fname in sorted(filenames):
            # Ignore hidden files (starting with '.') and macOS shadow/metadata files (starting with '._')
            if fname.startswith('.'):
                continue
            if Path(fname).suffix.lower() in settings.SUPPORTED_EXTENSIONS:
                media_files.append(Path(dirpath) / fname)
    total_files = len(media_files)

    start_index = 0
    if resume_after:
        try:
            start_index = next(
                index + 1 for index, file_path in enumerate(media_files) if str(file_path) == resume_after
            )
        except StopIteration:
            logger.warning("Resume cursor no longer exists; safely rescanning with dedup: %s", resume_after)
            start_index = 0

    # Pre-load existing items metadata for O(1) checks
    existing_items = _load_existing_items_metadata(session)
    logger.info("Loaded %d existing items for dedup and thumbnail verification", len(existing_items))

    # Resolve the volume for this path
    volume = get_volume_for_path(session, root)
    volume_id = volume.id if volume else None

    # Ensure cache dirs exist
    if generate_thumbs:
        settings.ensure_cache_dirs()

    # Accumulate records for batch insert
    batch_buffer: list[MediaItemDict] = []
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
                logger.info("Scan paused at %d / %d files", processed, total_files)
                return result

            ext = file_path.suffix.lower()
            fname = file_path.name
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
                        session.query(MediaItem).filter(MediaItem.sha256 == sha256).update(updated_fields)
                        session.commit()
                    existing_items[sha256] = (
                        has_thumb or "thumb_path" in updated_fields,
                        has_preview or "preview_path" in updated_fields
                    )

                    result.duplicates_skipped += 1
                    report_progress_if_needed(file_path)
                    continue

                # Mark as seen to avoid processing the same file twice
                # within this scan (e.g. symlinks)
                existing_items[sha256] = (
                    generate_thumbs and ext in settings.SUPPORTED_EXTENSIONS,
                    generate_thumbs and ext in settings.SUPPORTED_EXTENSIONS
                )

                # 2. pHash (images only) - Defer if generate_thumbs is False to speed up scanning
                phash = compute_phash(file_path) if generate_thumbs else None

                # 3. EXIF metadata
                exif = extract_exif(file_path)

                # 4. File metadata
                stat = file_path.stat()
                mime_type, _ = mimetypes.guess_type(str(file_path))

                # 5. Thumbnail generation (optional)
                thumb_path = None
                preview_path = None
                proxy_path = None
                if generate_thumbs and ext in settings.SUPPORTED_EXTENSIONS:
                    thumb_path = generate_thumbnail(file_path, sha256)
                    preview_path = generate_preview(file_path, sha256)
                    if ext in settings.SUPPORTED_VIDEO_EXTENSIONS:
                        from backend.services.thumbnails import _generate_video_proxy
                        proxy_path = _generate_video_proxy(file_path, sha256)

                # 6. Build record
                record: MediaItemDict = {
                    "id": str(uuid.uuid4()),
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
                    **exif,
                }
                batch_buffer.append(record)

                # Flush batch when buffer is full
                if len(batch_buffer) >= live_batch_size:
                    flush_batch()

            except Exception as exc:
                result.errors += 1
                error_msg = f"{file_path}: {exc}"
                result.error_details.append(error_msg)
                logger.warning("Scan error: %s", error_msg)

            report_progress_if_needed(file_path)

    # Flush remaining records
    flush_batch()
    result.total_found = total_files

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
        "Scan complete: found=%d, inserted=%d, dupes=%d, errors=%d",
        result.total_found,
        result.new_inserted,
        result.duplicates_skipped,
        result.errors,
    )
    return result

def scan_file(
    file_path: str | Path,
    session: Session,
    *,
    generate_thumbs: bool = True,
) -> bool:
    """Ingest a single file. Returns True if inserted, False if skipped/errored."""
    file_path = Path(file_path).resolve()
    if not file_path.is_file():
        return False
    
    ext = file_path.suffix.lower()
    if ext not in settings.SUPPORTED_EXTENSIONS:
        return False
        
    try:
        sha256 = compute_sha256(file_path)
        
        # O(1) dedup check
        existing = session.query(MediaItem).filter(MediaItem.sha256 == sha256).first()
        if existing:
            updated = False
            if generate_thumbs and ext in settings.SUPPORTED_EXTENSIONS:
                settings.ensure_cache_dirs()
                if not existing.thumb_path:
                    existing.thumb_path = generate_thumbnail(file_path, sha256)
                    updated = True
                if not existing.preview_path:
                    existing.preview_path = generate_preview(file_path, sha256)
                    updated = True
                if not existing.proxy_path and ext in settings.SUPPORTED_VIDEO_EXTENSIONS:
                    from backend.services.thumbnails import _generate_video_proxy
                    existing.proxy_path = _generate_video_proxy(file_path, sha256)
                    updated = True
                if updated:
                    session.commit()
            return False
            
        phash = compute_phash(file_path) if generate_thumbs else None
        exif = extract_exif(file_path)
        stat = file_path.stat()
        mime_type, _ = mimetypes.guess_type(str(file_path))
        
        volume = get_volume_for_path(session, file_path)
        volume_id = volume.id if volume else None
        
        thumb_path = None
        preview_path = None
        proxy_path = None
        if generate_thumbs and ext in settings.SUPPORTED_EXTENSIONS:
            settings.ensure_cache_dirs()
            thumb_path = generate_thumbnail(file_path, sha256)
            preview_path = generate_preview(file_path, sha256)
            if ext in settings.SUPPORTED_VIDEO_EXTENSIONS:
                from backend.services.thumbnails import _generate_video_proxy
                proxy_path = _generate_video_proxy(file_path, sha256)
            
        record: MediaItemDict = {
            "id": str(uuid.uuid4()),
            "sha256": sha256,
            "phash": phash,
            "volume_id": volume_id,
            "original_path": str(file_path),
            "filename": file_path.name,
            "mime_type": mime_type,
            "file_size_bytes": stat.st_size,
            "thumb_path": thumb_path,
            "preview_path": preview_path,
            "proxy_path": proxy_path,
            "date_modified": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ),
            **exif,
        }
        
        inserted = batch_insert_media_items(session, [record], batch_size=1)
        return inserted > 0
    except Exception as exc:
        logger.warning("scan_file error for %s: %s", file_path, exc)
        return False
