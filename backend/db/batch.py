"""
Batch Insert Utilities
======================

High-throughput write helpers for the ingestion pipeline.

Why batching matters with SQLite
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
SQLite acquires a *file-level write lock* for every transaction.  If the
ingestion pipeline does one INSERT per commit, each commit triggers:

    1. WAL frame write  →  2. fsync  →  3. lock release

At ~500 fsyncs/sec on a good SSD this caps throughput at ~500 rows/sec.

By grouping 500–1000 rows into a single transaction we amortise the
fsync cost and reach **50,000+ rows/sec** on NVMe storage.

Usage from the Huey worker::

    from backend.db.batch import batch_insert_media_items
    from backend.db.engine import SessionLocal

    with SessionLocal() as session:
        inserted = batch_insert_media_items(session, records, batch_size=500)
        print(f"Inserted {inserted} new media items")
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.orm import Session

from backend.db.models import MediaItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type alias for a row dict that maps column names → values
# ---------------------------------------------------------------------------
MediaItemDict = dict[str, Any]


def batch_insert_media_items(
    session: Session,
    records: list[MediaItemDict],
    *,
    batch_size: int = 500,
    on_conflict: str = "skip",  # "skip" | "update"
) -> int:
    """Insert media item records in batched transactions.

    Parameters
    ----------
    session:
        An *uncommitted* SQLAlchemy ``Session``.  The caller is
        responsible for closing it.
    records:
        List of dicts whose keys match ``MediaItem`` column names.
        At minimum each dict **must** contain ``sha256``,
        ``original_path``, and ``filename``.
    batch_size:
        Number of rows per ``INSERT`` statement / commit cycle.
        500 is a good default — large enough to amortise the WAL
        fsync, small enough to keep the write-lock window short so
        concurrent readers (the FastAPI timeline endpoint) are not
        blocked for more than a few milliseconds.
    on_conflict:
        ``"skip"``  – silently ignore duplicates (``INSERT OR IGNORE``).
        ``"update"`` – upsert: on SHA-256 collision, overwrite the
        mutable metadata columns (useful for re-scanning a drive).

    Returns
    -------
    int
        Total number of rows actually written (excluding skipped dupes).
    """
    if not records:
        return 0

    table = MediaItem.__table__
    total_inserted = 0

    # Columns we allow the upsert to overwrite (never overwrite the PK or sha256).
    _updatable_cols = {
        c.key
        for c in inspect(MediaItem).mapper.column_attrs
        if c.key not in ("id", "sha256", "ingested_at")
    }

    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]

        try:
            if on_conflict == "update":
                # SQLite-specific INSERT … ON CONFLICT … DO UPDATE
                stmt = sqlite_upsert(table).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["sha256"],
                    set_={col: stmt.excluded[col] for col in _updatable_cols if col in batch[0]},
                )
            else:
                # INSERT OR IGNORE – skip rows whose sha256 already exists
                stmt = sqlite_upsert(table).values(batch)
                stmt = stmt.on_conflict_do_nothing(index_elements=["sha256"])

            result = session.execute(stmt)
            session.commit()

            # rowcount reflects rows actually written (not skipped)
            total_inserted += result.rowcount  # type: ignore[union-attr]

            logger.debug(
                "Batch [%d–%d]: wrote %d rows",
                start,
                start + len(batch),
                result.rowcount,
            )

        except Exception:
            session.rollback()
            logger.exception("Batch insert failed at offset %d", start)
            raise

    logger.info("Batch insert complete: %d / %d records written", total_inserted, len(records))
    return total_inserted


def batch_insert_media_items_simple(
    session: Session,
    records: list[MediaItemDict],
    *,
    batch_size: int = 500,
) -> int:
    """Simpler alternative using ``Session.bulk_insert_mappings``.

    This is slightly faster when you are **certain** there are no
    duplicates (e.g. the caller has already filtered by sha256).
    It does **not** handle conflicts — a duplicate sha256 will raise
    ``IntegrityError``.

    Parameters
    ----------
    session:
        An *uncommitted* SQLAlchemy ``Session``.
    records:
        List of dicts mapping ``MediaItem`` column names to values.
    batch_size:
        Rows per commit.

    Returns
    -------
    int
        Total rows inserted.
    """
    if not records:
        return 0

    total = 0

    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        try:
            session.bulk_insert_mappings(MediaItem, batch)
            session.commit()
            total += len(batch)
        except Exception:
            session.rollback()
            logger.exception("bulk_insert_mappings failed at offset %d", start)
            raise

    logger.info("Simple batch insert complete: %d rows", total)
    return total
