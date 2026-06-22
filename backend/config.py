"""
Central Configuration
=====================

All tunables in one place, overridable via environment variables.
Import as::

    from backend.config import settings
"""

from __future__ import annotations

import os
from pathlib import Path


class Settings:
    """Application-wide settings with sensible defaults."""

    # -- Project root (one level above `backend/`) -------------------------
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

    # -- Database ----------------------------------------------------------
    DB_PATH: Path = Path(
        os.environ.get("MYPHOTOS_DB_PATH", str(PROJECT_ROOT / "data" / "myphotos.db"))
    )

    # -- Huey task queue ---------------------------------------------------
    HUEY_DB_PATH: Path = Path(
        os.environ.get("MYPHOTOS_HUEY_DB_PATH", str(PROJECT_ROOT / "data" / "huey.db"))
    )

    # -- Local cache (thumbnails + previews) --------------------------------
    CACHE_DIR: Path = Path(
        os.environ.get(
            "MYPHOTOS_CACHE_DIR",
            str(Path.home() / ".local_cache" / "myphotos"),
        )
    )
    THUMB_DIR: Path = CACHE_DIR / "thumbs"
    PREVIEW_DIR: Path = CACHE_DIR / "previews"

    # -- ML Models & Vector DB ---------------------------------------------
    LANCEDB_PATH: Path = Path(
        os.environ.get("MYPHOTOS_LANCEDB_PATH", str(PROJECT_ROOT / "data" / "lancedb"))
    )
    CLIP_MODEL_NAME: str = "ViT-L-14"
    CLIP_PRETRAINED: str = "openai"
    DEEPFACE_MODEL_NAME: str = "Facenet"

    # -- Thumbnail sizes ---------------------------------------------------
    THUMB_SIZE: int = 768       # longest edge in pixels
    THUMB_QUALITY: int = 85     # WebP quality (0-100)
    PREVIEW_SIZE: int = 1080    # longest edge in pixels
    PREVIEW_QUALITY: int = 85   # WebP quality (0-100)

    # -- Scanner -----------------------------------------------------------
    SCAN_BATCH_SIZE: int = int(os.environ.get("MYPHOTOS_SCAN_BATCH_SIZE", "500"))
    SHA256_CHUNK_SIZE: int = 65_536  # 64 KiB read chunks for hashing

    SUPPORTED_IMAGE_EXTENSIONS: frozenset[str] = frozenset({
        ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif",
        ".tiff", ".tif", ".bmp", ".gif",
    })
    SUPPORTED_VIDEO_EXTENSIONS: frozenset[str] = frozenset({
        ".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".wmv",
    })
    SUPPORTED_EXTENSIONS: frozenset[str] = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS

    # -- Thumbnail workers -------------------------------------------------
    THUMBNAIL_WORKERS: int = int(os.environ.get("MYPHOTOS_THUMB_WORKERS", "4"))

    # -- API ---------------------------------------------------------------
    API_HOST: str = os.environ.get("MYPHOTOS_HOST", "127.0.0.1")
    API_PORT: int = int(os.environ.get("MYPHOTOS_PORT", "8000"))
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",   # React dev server
        "http://localhost:5173",   # Vite dev server
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # -- Timeline pagination -----------------------------------------------
    TIMELINE_PAGE_SIZE: int = 200  # items per page for virtualized timeline

    def ensure_cache_dirs(self) -> None:
        """Create the cache directory tree if it doesn't exist."""
        self.THUMB_DIR.mkdir(parents=True, exist_ok=True)
        self.PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    def setup_rotating_logging(self) -> None:
        """Configure rotating file logging for the application."""
        import logging
        from logging.handlers import RotatingFileHandler

        log_dir = self.PROJECT_ROOT / "data"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "myphotos.log"

        # Create handler: 5 MB file size limit, keep 3 backup copies
        file_handler = RotatingFileHandler(
            str(log_file),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)

        # Log format
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
        )
        file_handler.setFormatter(formatter)

        # Get root logger and add handler
        root_logger = logging.getLogger()

        # Avoid duplicate handlers if already configured
        if not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
            root_logger.addHandler(file_handler)

        if root_logger.level > logging.INFO or root_logger.level == logging.NOTSET:
            root_logger.setLevel(logging.INFO)


settings = Settings()
