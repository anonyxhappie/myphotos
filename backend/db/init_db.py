"""
Database initialisation script
==============================

Run this once (or on every app startup — it's idempotent) to:
    1. Create all tables defined in ``backend.db.models``.
    2. Verify that the critical SQLite PRAGMAs are active.
    3. Optionally seed demo data for development.

Usage::

    python -m backend.db.init_db          # create tables
    python -m backend.db.init_db --seed   # create tables + seed demo data
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone

from backend.db.batch import batch_insert_media_items
from backend.db.engine import SessionLocal, engine
from backend.db.models import Base, Volume


def _verify_pragmas() -> None:
    """Check that the event listener set the PRAGMAs we care about."""
    from sqlalchemy import text

    with engine.connect() as conn:
        pragmas = {
            "journal_mode": "wal",
            "busy_timeout": "5000",
            "synchronous": "1",       # NORMAL = 1
            "foreign_keys": "1",
        }
        all_ok = True
        for pragma, expected in pragmas.items():
            row = conn.execute(text(f"PRAGMA {pragma};")).scalar()
            actual = str(row).lower()
            status = "✓" if actual == expected else "✗"
            if actual != expected:
                all_ok = False
            print(f"  {status} PRAGMA {pragma} = {actual} (expected {expected})")

        if not all_ok:
            print("\n  ⚠  Some PRAGMAs did not match. Check engine.py.\n")
        else:
            print("\n  All PRAGMAs verified.\n")


def _seed_demo_data() -> None:
    """Insert a handful of fake records for local development."""
    with SessionLocal() as session:
        # -- Seed a volume ---------------------------------------------------
        vol = Volume(
            id=str(uuid.uuid4()),
            os_uuid="550e8400-e29b-41d4-a716-446655440000",
            label="MacintoshHD",
            mount_point="/",
            is_online=True,
        )
        session.add(vol)
        session.commit()

        # -- Seed media items via batch insert --------------------------------
        demo_records = [
            {
                "id": str(uuid.uuid4()),
                "sha256": f"{'0' * 56}{i:08x}",  # unique fake hashes
                "original_path": f"/Users/demo/Photos/IMG_{i:04d}.jpg",
                "filename": f"IMG_{i:04d}.jpg",
                "mime_type": "image/jpeg",
                "file_size_bytes": 3_500_000 + i * 1000,
                "volume_id": vol.id,
                "width": 4032,
                "height": 3024,
                "date_taken": datetime(2024, 1, 1 + (i % 28), 12, 0, 0, tzinfo=timezone.utc),
            }
            for i in range(50)
        ]

        inserted = batch_insert_media_items(session, demo_records, batch_size=25)
        print(f"  Seeded {inserted} demo media items across 1 volume.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialise the MyPhotos SQLite database.")
    parser.add_argument("--seed", action="store_true", help="Populate with demo data for development.")
    args = parser.parse_args()

    print("\n╔══════════════════════════════════════════╗")
    print("║    MyPhotos – Database Initialisation    ║")
    print("╚══════════════════════════════════════════╝\n")

    # 1. Create tables
    print("Creating tables …")
    Base.metadata.create_all(bind=engine)
    print("  Done.\n")

    # 2. Verify PRAGMAs
    print("Verifying SQLite PRAGMAs …")
    _verify_pragmas()

    # 3. Optional seeding
    if args.seed:
        print("Seeding demo data …")
        _seed_demo_data()

    print(f"Database ready at: {engine.url}\n")


if __name__ == "__main__":
    main()
