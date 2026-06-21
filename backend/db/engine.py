"""
SQLite Engine Configuration
===========================

Key design decisions:
    1.  WAL journal mode — allows concurrent readers while a single writer
        is active, eliminating "database is locked" errors from the
        FastAPI ↔ Huey worker contention pattern.
    2.  busy_timeout=5000 — instead of immediately raising SQLITE_BUSY,
        the connection will spin-wait for up to 5 s for the write lock.
    3.  synchronous=NORMAL — safe with WAL; avoids an fsync on every
        commit, yielding ~2-3× write throughput improvement.
    4.  mmap_size — memory-maps the database file for faster reads on
        large libraries (set to 256 MiB here).
    5.  cache_size — negative value = KiB; -64000 ≈ 64 MiB page cache.
    6.  foreign_keys — enforced at the connection level (SQLite default
        is OFF, which silently ignores FK violations).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# ---------------------------------------------------------------------------
# Database path – defaults to  <project_root>/data/myphotos.db
# Override via the MYPHOTOS_DB_PATH environment variable.
# ---------------------------------------------------------------------------
_DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "myphotos.db"

DATABASE_PATH: Path = Path(os.environ.get("MYPHOTOS_DB_PATH", str(_DEFAULT_DB_PATH)))
DATABASE_URL: str = f"sqlite:///{DATABASE_PATH}"

# Ensure the parent directory exists so SQLite can create the file.
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# • check_same_thread=False is required because FastAPI/Uvicorn serves
#   requests across multiple threads, but SQLite only allows the creating
#   thread to use a connection by default.
# • pool_size=1 + max_overflow=0 would serialise all writes to a single
#   connection – acceptable because SQLite only supports one writer anyway.
#   For the *read-heavy* API layer we use a NullPool so each request gets
#   its own lightweight connection (cheap with WAL).
# ---------------------------------------------------------------------------

engine: Engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,  # Set True for SQL-level debugging
    pool_pre_ping=True,  # Reconnect stale connections after drive sleeps
)


# ---------------------------------------------------------------------------
# PRAGMA event listener – applied to every raw DBAPI connection
# ---------------------------------------------------------------------------
@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    """Apply performance-critical PRAGMAs on every new connection.

    These cannot be set via the connection URL and must be executed as
    raw SQL before the ORM does anything with the connection.
    """
    cursor = dbapi_connection.cursor()

    # -- Concurrency & durability ------------------------------------------
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=5000;")
    cursor.execute("PRAGMA synchronous=NORMAL;")

    # -- Performance -------------------------------------------------------
    cursor.execute("PRAGMA mmap_size=268435456;")   # 256 MiB
    cursor.execute("PRAGMA cache_size=-64000;")      # 64 MiB page cache
    cursor.execute("PRAGMA temp_store=MEMORY;")      # temp tables in RAM

    # -- Correctness -------------------------------------------------------
    cursor.execute("PRAGMA foreign_keys=ON;")

    cursor.close()


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # Avoid lazy-loads after commit in async code
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a scoped database session.

    Usage::

        @app.get("/photos")
        def list_photos(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def log_audit_entry(action: str, level: str, details: str) -> None:
    """Log an event to the audit_logs table."""
    try:
        from backend.db.models import AuditLog
        with SessionLocal() as session:
            entry = AuditLog(action=action, level=level, details=details)
            session.add(entry)
            session.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Failed to write audit log: %s", e)
