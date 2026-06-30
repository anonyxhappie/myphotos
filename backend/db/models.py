"""
SQLAlchemy ORM Models
=====================

Schema design principles for a Terabyte-scale local photo library:

    • **Volumes** track physical drives by OS-level UUID so the app knows
      which originals are online vs offline.
    • **MediaItems** is the central table.  It stores *only metadata* –
      never binary blobs.  Thumbnails and previews live on-disk under
      ``~/.local_cache/myphotos/``.
    • **Albums** and **Tags** are many-to-many via association tables so
      a single photo can appear in multiple albums and carry multiple tags.
    • All datetime columns default to UTC.
    • SHA-256 and pHash columns have unique/index constraints to support
      fast exact- and near-duplicate lookups.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Shared declarative base for all models."""


# ---------------------------------------------------------------------------
# Association tables (many-to-many)
# ---------------------------------------------------------------------------

media_albums = Table(
    "media_albums",
    Base.metadata,
    Column("media_item_id", String(36), ForeignKey("media_items.id", ondelete="CASCADE"), primary_key=True),
    Column("album_id", String(36), ForeignKey("albums.id", ondelete="CASCADE"), primary_key=True),
)

media_tags = Table(
    "media_tags",
    Base.metadata,
    Column("media_item_id", String(36), ForeignKey("media_items.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _new_uuid() -> str:
    return str(_uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Volumes – track physical storage devices
# ---------------------------------------------------------------------------
class Volume(Base):
    """Represents a mounted filesystem / external drive.

    ``os_uuid`` is the Volume UUID reported by the OS
    (``diskutil info`` on macOS, ``blkid`` on Linux).
    """

    __tablename__ = "volumes"

    id: str = Column(String(36), primary_key=True, default=_new_uuid)
    os_uuid: str = Column(String(128), unique=True, nullable=False, index=True, comment="OS-level volume UUID")
    label: str = Column(String(255), nullable=True, comment="Human-friendly drive label")
    mount_point: str = Column(Text, nullable=True, comment="Last-known mount path, e.g. /Volumes/BackupDrive")
    is_online: bool = Column(Boolean, default=True, nullable=False, comment="True when drive is currently mounted")
    total_bytes: int = Column(Integer, nullable=True, comment="Total capacity in bytes")
    free_bytes: int = Column(Integer, nullable=True, comment="Free space in bytes at last scan")

    created_at: datetime = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: datetime = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # relationships
    media_items = relationship("MediaItem", back_populates="volume", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Volume label={self.label!r} uuid={self.os_uuid!r} online={self.is_online}>"


# ---------------------------------------------------------------------------
# MediaItems – one row per unique photo / video
# ---------------------------------------------------------------------------
class MediaItem(Base):
    """Core metadata record for a single photo or video file.

    Heavy binary data (thumbnails, previews) is stored on the filesystem
    under ``~/.local_cache/myphotos/<sha256_prefix>/<sha256>.webp``.
    Only the hash and relative paths are persisted here.
    """

    __tablename__ = "media_items"

    # -- identity ----------------------------------------------------------
    id: str = Column(String(36), primary_key=True, default=_new_uuid)
    sha256: str = Column(String(64), unique=True, nullable=False, index=True, comment="Hex-encoded SHA-256 of original file")
    phash: str = Column(String(16), nullable=True, index=True, comment="Perceptual hash for near-duplicate detection")

    # -- file location -----------------------------------------------------
    volume_id: str = Column(String(36), ForeignKey("volumes.id", ondelete="SET NULL"), nullable=True, index=True)
    original_path: str = Column(Text, nullable=False, comment="Absolute path to the original file at ingest time")
    filename: str = Column(String(512), nullable=False, comment="Original filename with extension")
    mime_type: str = Column(String(128), nullable=True, comment="e.g. image/jpeg, video/mp4")
    file_size_bytes: int = Column(Integer, nullable=True, comment="Size of original file in bytes")

    # -- cache paths -------------------------------------------------------
    thumb_path: str = Column(Text, nullable=True, comment="Relative path to 256px WebP thumbnail in .local_cache")
    preview_path: str = Column(Text, nullable=True, comment="Relative path to 1080p WebP preview in .local_cache")

    # -- EXIF & Google Takeout metadata ------------------------------------
    date_taken: datetime = Column(DateTime(timezone=True), nullable=True, index=True, comment="EXIF DateTimeOriginal or Takeout timestamp")
    date_modified: datetime = Column(DateTime(timezone=True), nullable=True)
    width: int = Column(Integer, nullable=True)
    height: int = Column(Integer, nullable=True)
    duration_seconds: float = Column(Float, nullable=True, comment="Video duration; NULL for images")
    camera_make: str = Column(String(128), nullable=True)
    camera_model: str = Column(String(128), nullable=True)
    lens_model: str = Column(String(128), nullable=True)
    iso: int = Column(Integer, nullable=True)
    focal_length_mm: float = Column(Float, nullable=True)
    aperture: float = Column(Float, nullable=True)
    exposure_time: str = Column(String(32), nullable=True, comment="e.g. 1/250")

    # -- GPS ---------------------------------------------------------------
    latitude: float = Column(Float, nullable=True, index=True)
    longitude: float = Column(Float, nullable=True, index=True)
    altitude_m: float = Column(Float, nullable=True)

    # -- Google Takeout specifics ------------------------------------------
    google_description: str = Column(Text, nullable=True, comment="Description from Takeout JSON")
    google_url: str = Column(Text, nullable=True, comment="Original Google Photos URL if present")
    is_favorite: bool = Column(Boolean, default=False, nullable=False)
    is_archived: bool = Column(Boolean, default=False, nullable=False)
    is_trashed: bool = Column(Boolean, default=False, nullable=False)
    trashed_at: datetime = Column(DateTime(timezone=True), nullable=True, comment="Timestamp when the item was moved to the bin")
    is_locked: bool = Column(Boolean, default=False, nullable=False)

    # -- AI processing status ----------------------------------------------
    clip_embedded: bool = Column(Boolean, default=False, nullable=False, comment="True once CLIP embedding is stored in LanceDB")
    faces_scanned: bool = Column(Boolean, default=False, nullable=False, comment="True once DeepFace has processed this item")

    # -- timestamps --------------------------------------------------------
    ingested_at: datetime = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: datetime = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # -- relationships -----------------------------------------------------
    volume = relationship("Volume", back_populates="media_items")
    albums = relationship("Album", secondary=media_albums, back_populates="media_items", lazy="selectin")
    tags = relationship("Tag", secondary=media_tags, back_populates="media_items", lazy="selectin")
    faces = relationship("Face", back_populates="media_item", cascade="all, delete-orphan", lazy="selectin")

    # -- composite indexes for common query patterns -----------------------
    __table_args__ = (
        Index("ix_media_date_volume", "date_taken", "volume_id"),
        Index("ix_media_mime_date", "mime_type", "date_taken"),
        UniqueConstraint("sha256", name="uq_media_sha256"),
    )

    def __repr__(self) -> str:
        return f"<MediaItem filename={self.filename!r} sha256={self.sha256[:12]}…>"


# ---------------------------------------------------------------------------
# Albums
# ---------------------------------------------------------------------------
class Album(Base):
    """User-created or auto-generated album (e.g. from Takeout folder names)."""

    __tablename__ = "albums"

    id: str = Column(String(36), primary_key=True, default=_new_uuid)
    title: str = Column(String(512), nullable=False, index=True)
    description: str = Column(Text, nullable=True)
    cover_media_id: str = Column(String(36), ForeignKey("media_items.id", ondelete="SET NULL"), nullable=True)

    created_at: datetime = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: datetime = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    # relationships
    media_items = relationship("MediaItem", secondary=media_albums, back_populates="albums", lazy="dynamic")
    cover = relationship("MediaItem", foreign_keys=[cover_media_id], lazy="joined")

    def __repr__(self) -> str:
        return f"<Album title={self.title!r}>"


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------
class Tag(Base):
    """Flat tag that can be applied to any media item.

    Tags come from multiple sources: user-applied, AI-generated
    (CLIP categories), or imported from Google Takeout.
    """

    __tablename__ = "tags"

    id: str = Column(String(36), primary_key=True, default=_new_uuid)
    name: str = Column(String(255), unique=True, nullable=False, index=True)
    source: str = Column(
        String(32),
        nullable=False,
        default="user",
        comment="Origin: 'user', 'ai_clip', 'ai_deepface', 'takeout'",
    )

    created_at: datetime = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # relationships
    media_items = relationship("MediaItem", secondary=media_tags, back_populates="tags", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<Tag name={self.name!r} source={self.source!r}>"


# ---------------------------------------------------------------------------
# People & Faces
# ---------------------------------------------------------------------------
class Person(Base):
    """A distinct person identified via face clustering."""
    __tablename__ = "people"

    id: str = Column(String(36), primary_key=True, default=_new_uuid)
    name: str = Column(String(255), nullable=False, default="Unknown Person")
    cover_face_id: str = Column(String(36), ForeignKey("faces.id", ondelete="SET NULL", use_alter=True), nullable=True)

    created_at: datetime = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: datetime = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    faces = relationship("Face", back_populates="person", foreign_keys="Face.person_id", lazy="dynamic")
    cover_face = relationship("Face", foreign_keys=[cover_face_id], post_update=True)

    def __repr__(self) -> str:
        return f"<Person name={self.name!r}>"


class Face(Base):
    """A detected face in a specific media item."""
    __tablename__ = "faces"

    id: str = Column(String(36), primary_key=True, default=_new_uuid)
    media_item_id: str = Column(String(36), ForeignKey("media_items.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id: str = Column(String(36), ForeignKey("people.id", ondelete="SET NULL"), nullable=True, index=True)

    # Bounding box
    box_x1: float = Column(Float, nullable=True)
    box_y1: float = Column(Float, nullable=True)
    box_x2: float = Column(Float, nullable=True)
    box_y2: float = Column(Float, nullable=True)

    created_at: datetime = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    media_item = relationship("MediaItem", back_populates="faces")
    person = relationship("Person", back_populates="faces", foreign_keys=[person_id])

    def __repr__(self) -> str:
        return f"<Face id={self.id!r} media={self.media_item_id!r}>"


# ---------------------------------------------------------------------------
# Synced Directories
# ---------------------------------------------------------------------------
class SyncedDirectory(Base):
    """A user-specified folder on disk to watch for real-time filesystem events."""

    __tablename__ = "synced_directories"

    id: str = Column(String(36), primary_key=True, default=_new_uuid)
    path: str = Column(Text, unique=True, nullable=False, comment="Absolute path to the monitored folder")
    is_active: bool = Column(Boolean, default=True, nullable=False, comment="Whether real-time syncing is currently active")

    created_at: datetime = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: datetime = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<SyncedDirectory path={self.path!r} active={self.is_active}>"


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------
class AuditLog(Base):
    """Activity and audit logs tracking sync actions, deletions, and moves."""

    __tablename__ = "audit_logs"

    id: str = Column(String(36), primary_key=True, default=_new_uuid)
    timestamp: datetime = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    action: str = Column(String(64), nullable=False)  # 'sync_dir_added', 'sync_dir_removed', 'file_synced', 'file_deleted', 'bulk_sync_complete', 'sync_error'
    level: str = Column(String(16), default="info", nullable=False)  # 'info', 'success', 'warning', 'error'
    details: str = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AuditLog action={self.action!r} level={self.level!r}>"
