"""
Pydantic v2 Schemas
===================

Request / response models for the FastAPI endpoints.  These are
intentionally separate from the SQLAlchemy ORM models to maintain
a clean API contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------
class VolumeResponse(BaseModel):
    """Public representation of a tracked storage volume."""

    id: str
    os_uuid: str
    label: Optional[str] = None
    mount_point: Optional[str] = None
    is_online: bool
    total_bytes: Optional[int] = None
    free_bytes: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Media Item
# ---------------------------------------------------------------------------
class MediaItemSummary(BaseModel):
    """Lightweight representation for the timeline grid.

    Only the fields needed to render a thumbnail tile.
    """

    id: str
    sha256: str
    thumb_path: Optional[str] = None
    date_taken: Optional[datetime] = None
    date_modified: Optional[datetime] = None
    width: Optional[int] = None
    height: Optional[int] = None
    mime_type: Optional[str] = None
    is_favorite: bool = False
    is_locked: bool = False
    is_online: bool = True  # computed from volume status

    model_config = {"from_attributes": True}


class MediaItemDetail(BaseModel):
    """Full metadata for a single media item (detail view)."""

    id: str
    sha256: str
    phash: Optional[str] = None

    # File location
    volume_id: Optional[str] = None
    original_path: str
    filename: str
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None

    # Cache paths
    thumb_path: Optional[str] = None
    preview_path: Optional[str] = None

    # EXIF / Takeout metadata
    date_taken: Optional[datetime] = None
    date_modified: Optional[datetime] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    lens_model: Optional[str] = None
    iso: Optional[int] = None
    focal_length_mm: Optional[float] = None
    aperture: Optional[float] = None
    exposure_time: Optional[str] = None

    # GPS
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_m: Optional[float] = None

    # Google Takeout
    google_description: Optional[str] = None
    is_favorite: bool = False
    is_archived: bool = False
    is_trashed: bool = False
    is_locked: bool = False

    # AI status
    clip_embedded: bool = False
    faces_scanned: bool = False

    # Timestamps
    ingested_at: datetime
    updated_at: datetime

    # Volume info (denormalised for the frontend)
    is_online: bool = True
    original_available: bool = True
    volume_label: Optional[str] = None
    offline_message: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Timeline (paginated)
# ---------------------------------------------------------------------------
class TimelineResponse(BaseModel):
    """Cursor-based paginated response for the timeline endpoint."""

    items: list[MediaItemSummary]
    next_cursor: Optional[str] = Field(
        None,
        description="Opaque cursor for the next page. None means end of data.",
    )
    total_count: int = Field(
        description="Total number of media items in the library."
    )


# ---------------------------------------------------------------------------
# Scan requests / responses
# ---------------------------------------------------------------------------
class ScanRequest(BaseModel):
    """Request body for triggering a directory scan."""

    path: str = Field(description="Absolute path to the directory to scan.")
    generate_thumbs: bool = Field(
        True,
        description="Generate thumbnails inline during scan.",
    )


class TakeoutRequest(BaseModel):
    """Request body for triggering a Google Takeout import."""

    path: str = Field(description="Path to the Takeout export directory.")
    generate_thumbs: bool = True


class ScanProgress(BaseModel):
    total_found: int = 0
    processed: int = 0
    new_inserted: int = 0
    duplicates_skipped: int = 0
    errors: int = 0
    current_file: Optional[str] = None
    start_time: Optional[float] = None


class ScanStatusResponse(BaseModel):
    """Status of a background scan task."""

    task_id: str
    status: str = Field(description="'pending', 'running', 'pausing', 'paused', 'complete', or 'error'.")
    progress: Optional[ScanProgress] = None
    result: Optional[dict] = None
    path: Optional[str] = None
    mode: str = "scan"
    generate_thumbs: bool = True
    error_message: Optional[str] = None


class ScanEnqueuedResponse(BaseModel):
    """Response after successfully enqueuing a scan task."""

    task_id: str
    message: str = "Scan task enqueued"

# ---------------------------------------------------------------------------
# Synced Directories
# ---------------------------------------------------------------------------

class SyncedDirectoryCreate(BaseModel):
    path: str

class SyncedDirectoryResponse(BaseModel):
    id: str
    path: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    task_id: Optional[str] = None
    total_files: int = 0
    synced_files: int = 0

    model_config = ConfigDict(from_attributes=True)

# ---------------------------------------------------------------------------
# Albums
# ---------------------------------------------------------------------------
class AlbumCreate(BaseModel):
    title: str

class AlbumResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    cover_media_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}

class AlbumMediaAdd(BaseModel):
    media_ids: list[str]

# ---------------------------------------------------------------------------
# Audit Log Response
# ---------------------------------------------------------------------------
class AuditLogResponse(BaseModel):
    id: str
    timestamp: datetime
    action: str
    level: str
    details: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BulkDeleteRequest(BaseModel):
    media_ids: list[str]
