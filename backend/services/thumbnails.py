"""
Thumbnail Generator
===================

Generates WebP thumbnails (256 px) and previews (1080 px) from original
image files and stores them in the local cache directory, sharded by the
first two hex characters of the SHA-256 hash.

Directory layout::

    ~/.local_cache/myphotos/
    ├── thumbs/
    │   ├── a1/
    │   │   └── a1b2c3d4e5…64chars.webp
    │   └── ff/
    │       └── ff00aa11bb…64chars.webp
    └── previews/
        └── a1/
            └── a1b2c3d4e5…64chars.webp

Why WebP?
    • 25-35% smaller than JPEG at equivalent quality.
    • Supports transparency (useful for PNG originals).
    • Universally supported in modern browsers.

Why shard by hash prefix?
    • At 1 million photos, un-sharded flat directory = 1M inodes in one
      dir → very slow ``readdir()`` on ext4/HFS+.
    • 256 prefix dirs × ~4k files each = fast filesystem lookups.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

from backend.config import settings

logger = logging.getLogger(__name__)

# Register HEIF/HEIC opener if pillow-heif is installed
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    _HEIC_SUPPORTED = True
except ImportError:
    _HEIC_SUPPORTED = False
    logger.info("pillow-heif not installed — HEIC/HEIF files will be skipped")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------
@dataclass
class ThumbnailResult:
    """Result of generating thumbnails for a single media item."""

    sha256: str
    thumb_rel_path: Optional[str] = None    # relative to CACHE_DIR
    preview_rel_path: Optional[str] = None  # relative to CACHE_DIR
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Single-file generators
# ---------------------------------------------------------------------------
def _shard_dir(base_dir: Path, sha256: str) -> Path:
    """Return the shard subdirectory: ``<base>/<sha256[:2]>/``."""
    shard = sha256[:2]
    d = base_dir / shard
    d.mkdir(parents=True, exist_ok=True)
    return d


def generate_thumbnail(original_path: str | Path, sha256: str) -> Optional[str]:
    """Generate a 256 px WebP thumbnail.

    Returns the path relative to ``settings.CACHE_DIR``, or None on failure.
    """
    out_dir = _shard_dir(settings.THUMB_DIR, sha256)
    out_path = out_dir / f"{sha256}.webp"

    if out_path.exists():
        return str(out_path.relative_to(settings.CACHE_DIR))

    try:
        with Image.open(original_path) as img:
            img.thumbnail(
                (settings.THUMB_SIZE, settings.THUMB_SIZE),
                Image.Resampling.LANCZOS,
            )
            # Convert to RGB if necessary (RGBA → RGB for WebP without alpha)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(out_path, format="WEBP", quality=settings.THUMB_QUALITY)

        return str(out_path.relative_to(settings.CACHE_DIR))

    except Exception as exc:
        logger.warning("Thumbnail generation failed for %s: %s", original_path, exc)
        return None


def generate_preview(original_path: str | Path, sha256: str) -> Optional[str]:
    """Generate a 1080 px WebP preview.

    Returns the path relative to ``settings.CACHE_DIR``, or None on failure.
    """
    out_dir = _shard_dir(settings.PREVIEW_DIR, sha256)
    out_path = out_dir / f"{sha256}.webp"

    if out_path.exists():
        return str(out_path.relative_to(settings.CACHE_DIR))

    try:
        with Image.open(original_path) as img:
            img.thumbnail(
                (settings.PREVIEW_SIZE, settings.PREVIEW_SIZE),
                Image.Resampling.LANCZOS,
            )
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(out_path, format="WEBP", quality=settings.PREVIEW_QUALITY)

        return str(out_path.relative_to(settings.CACHE_DIR))

    except Exception as exc:
        logger.warning("Preview generation failed for %s: %s", original_path, exc)
        return None


# ---------------------------------------------------------------------------
# Batch generator (thread pool)
# ---------------------------------------------------------------------------
def _generate_single(original_path: str, sha256: str) -> ThumbnailResult:
    """Worker function for a single item — generates both thumb + preview."""
    result = ThumbnailResult(sha256=sha256)
    try:
        result.thumb_rel_path = generate_thumbnail(original_path, sha256)
        result.preview_rel_path = generate_preview(original_path, sha256)
    except Exception as exc:
        result.error = str(exc)
    return result


def generate_thumbnails_batch(
    items: list[tuple[str, str]],
    max_workers: int | None = None,
) -> list[ThumbnailResult]:
    """Generate thumbnails and previews for multiple items concurrently.

    Parameters
    ----------
    items:
        List of ``(original_path, sha256)`` tuples.
    max_workers:
        Thread pool size. Defaults to ``settings.THUMBNAIL_WORKERS``.

    Returns
    -------
    list[ThumbnailResult]
        One result per input item (order not guaranteed).
    """
    settings.ensure_cache_dirs()
    workers = max_workers or settings.THUMBNAIL_WORKERS
    results: list[ThumbnailResult] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_generate_single, path, sha): (path, sha)
            for path, sha in items
        }
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                path, sha = futures[future]
                logger.error("Unhandled error generating thumbnails for %s: %s", path, exc)
                results.append(ThumbnailResult(sha256=sha, error=str(exc)))

    succeeded = sum(1 for r in results if r.thumb_rel_path)
    logger.info(
        "Thumbnail batch complete: %d/%d succeeded",
        succeeded,
        len(items),
    )
    return results
