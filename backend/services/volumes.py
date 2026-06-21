"""
Volume Manager
==============

Detects and tracks physical storage devices (internal + external drives)
using macOS ``diskutil``.  Each mounted volume is identified by its
OS-level Volume UUID, which is stable across mounts/unmounts.

This allows the app to:
    • Know which originals are accessible right now.
    • Show cached previews with an "offline" badge when a drive is
      disconnected.
    • Automatically match new files to the correct volume record.
"""

from __future__ import annotations

import logging
import os
import plistlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Volume

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data transfer object
# ---------------------------------------------------------------------------
@dataclass
class DetectedVolume:
    """Lightweight DTO for a mounted volume discovered via the OS."""

    os_uuid: str
    label: str
    mount_point: str
    total_bytes: int = 0
    free_bytes: int = 0


# ---------------------------------------------------------------------------
# macOS volume detection
# ---------------------------------------------------------------------------
def _run_diskutil(*args: str) -> bytes:
    """Run a ``diskutil`` subcommand and return raw stdout."""
    cmd = ["diskutil", *args]
    try:
        result = subprocess.run(cmd, capture_output=True, check=True, timeout=10)
        return result.stdout
    except FileNotFoundError:
        logger.warning("diskutil not found – volume detection unavailable (non-macOS?)")
        return b""
    except subprocess.CalledProcessError as exc:
        logger.warning("diskutil %s failed: %s", " ".join(args), exc.stderr[:200])
        return b""


def detect_volumes_macos() -> list[DetectedVolume]:
    """Discover all mounted volumes on macOS via ``diskutil``.

    Returns a list of ``DetectedVolume`` objects for every partition
    that has a Volume UUID (filters out virtual/system partitions
    without UUIDs).
    """
    raw = _run_diskutil("list", "-plist")
    if not raw:
        return []

    try:
        plist = plistlib.loads(raw)
    except Exception:
        logger.exception("Failed to parse diskutil list output")
        return []

    volumes: list[DetectedVolume] = []
    all_disks = plist.get("AllDisksAndPartitions", [])

    for disk in all_disks:
        # Check both top-level (whole disk) and Partitions sub-key
        partitions = disk.get("Partitions", [disk])
        for part in partitions:
            dev_id = part.get("DeviceIdentifier", "")
            if not dev_id:
                continue

            # Get detailed info for this partition
            info_raw = _run_diskutil("info", "-plist", dev_id)
            if not info_raw:
                continue

            try:
                info = plistlib.loads(info_raw)
            except Exception:
                continue

            vol_uuid = info.get("VolumeUUID", "")
            mount_point = info.get("MountPoint", "")

            # Skip partitions without a UUID or that aren't mounted
            if not vol_uuid or not mount_point:
                continue

            label = info.get("VolumeName", "") or info.get("MediaName", "") or dev_id

            # Get disk usage via os.statvfs (faster than diskutil for size)
            total_bytes = 0
            free_bytes = 0
            try:
                stat = os.statvfs(mount_point)
                total_bytes = stat.f_blocks * stat.f_frsize
                free_bytes = stat.f_bavail * stat.f_frsize
            except OSError:
                pass

            volumes.append(
                DetectedVolume(
                    os_uuid=vol_uuid,
                    label=label,
                    mount_point=mount_point,
                    total_bytes=total_bytes,
                    free_bytes=free_bytes,
                )
            )

    logger.info("Detected %d mounted volumes", len(volumes))
    return volumes


# ---------------------------------------------------------------------------
# Database synchronisation
# ---------------------------------------------------------------------------
def sync_volumes_to_db(session: Session) -> dict[str, str]:
    """Detect mounted volumes and sync them to the ``volumes`` table.

    - New volumes → INSERT.
    - Known volumes that are mounted → UPDATE ``is_online=True``, refresh
      mount point and space stats.
    - Known volumes that are *not* in the mounted list → mark
      ``is_online=False`` (drive disconnected).

    Returns
    -------
    dict[str, str]
        Mapping of ``{os_uuid: volume_id}`` for all volumes now in the DB.
    """
    detected = detect_volumes_macos()
    detected_uuids = {v.os_uuid for v in detected}

    # Load all existing volume records
    existing: list[Volume] = session.query(Volume).all()
    existing_by_uuid: dict[str, Volume] = {v.os_uuid: v for v in existing}

    uuid_to_id: dict[str, str] = {}

    # Upsert detected volumes
    for dv in detected:
        if dv.os_uuid in existing_by_uuid:
            vol = existing_by_uuid[dv.os_uuid]
            vol.label = dv.label
            vol.mount_point = dv.mount_point
            vol.is_online = True
            vol.total_bytes = dv.total_bytes
            vol.free_bytes = dv.free_bytes
            logger.debug("Updated volume %s (%s)", vol.label, vol.os_uuid)
        else:
            vol = Volume(
                os_uuid=dv.os_uuid,
                label=dv.label,
                mount_point=dv.mount_point,
                is_online=True,
                total_bytes=dv.total_bytes,
                free_bytes=dv.free_bytes,
            )
            session.add(vol)
            logger.info("New volume registered: %s (%s)", dv.label, dv.os_uuid)

        uuid_to_id[dv.os_uuid] = vol.id

    # Mark disconnected drives offline
    for vol in existing:
        if vol.os_uuid not in detected_uuids:
            if vol.is_online:
                vol.is_online = False
                logger.info("Volume offline: %s (%s)", vol.label, vol.os_uuid)
            uuid_to_id[vol.os_uuid] = vol.id

    session.commit()
    return uuid_to_id


def get_volume_for_path(session: Session, file_path: str | Path) -> Optional[Volume]:
    """Determine which tracked volume a file path resides on.

    Matches by finding the volume whose ``mount_point`` is the longest
    prefix of the given path (handles nested mounts correctly).
    """
    file_path = str(Path(file_path).resolve())
    volumes: list[Volume] = session.query(Volume).filter(Volume.is_online.is_(True)).all()

    best_match: Optional[Volume] = None
    best_len = 0

    for vol in volumes:
        mp = vol.mount_point or ""
        if file_path.startswith(mp) and len(mp) > best_len:
            best_match = vol
            best_len = len(mp)

    return best_match
