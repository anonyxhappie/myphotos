"""
Directory Watcher
=================

Monitors specific directories in real-time using `watchdog`.
"""

import logging
import os
from pathlib import Path
from typing import Dict
from threading import Lock
from concurrent.futures import ThreadPoolExecutor

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent

from backend.db.engine import SessionLocal
from backend.db.models import SyncedDirectory, MediaItem
from backend.services.scanner import scan_file
from backend.config import settings

logger = logging.getLogger(__name__)

class SyncEventHandler(FileSystemEventHandler):
    def __init__(self, executor: ThreadPoolExecutor):
        super().__init__()
        self.executor = executor

    def process_path(self, file_path: str):
        path = Path(file_path)
        if path.is_file() and path.suffix.lower() in settings.SUPPORTED_EXTENSIONS:
            self.executor.submit(self._run_scan, path)

    def _run_scan(self, path: Path):
        try:
            with SessionLocal() as session:
                inserted = scan_file(path, session, generate_thumbs=True)
                if inserted:
                    session.commit()
                    logger.info("Real-time sync: ingested %s", path.name)
                    from backend.db.engine import log_audit_entry
                    log_audit_entry("file_synced", "info", f"Real-time sync: ingested {path.name} in {path.parent}")
                    
                    # Run ML analysis on the new item to generate CLIP embedding
                    item = session.query(MediaItem).filter(MediaItem.original_path == str(path)).first()
                    if item and item.mime_type and item.mime_type.startswith("image/"):
                        try:
                            from backend.services.ml import index_unprocessed_items
                            index_unprocessed_items(session, batch_size=1)
                            
                            # Match the item against all existing tags
                            from backend.db.models import Tag
                            from backend.db.vector import get_clip_table
                            from backend.services.ml import generate_text_embedding
                            import numpy as np
                            
                            tags = session.query(Tag).all()
                            if tags:
                                clip_table = get_clip_table()
                                results = clip_table.search().where(f"media_id = '{item.id}'").to_list()
                                if results:
                                    item_vector = results[0]["vector"]
                                    item_arr = np.array(item_vector)
                                    
                                    for tag in tags:
                                        tag_vector = generate_text_embedding(tag.name)
                                        if tag_vector:
                                            tag_arr = np.array(tag_vector)
                                            similarity = np.dot(item_arr, tag_arr)
                                            if similarity >= 0.2: # default threshold
                                                if tag not in item.tags:
                                                    item.tags.append(tag)
                                    session.commit()
                        except Exception as ml_err:
                            logger.error("Failed to run real-time ML tag matching: %s", ml_err)
                    
                    # Notify frontend via redis pubsub to trigger a timeline refresh
                    import redis
                    import json
                    r = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
                    payload = {"task_id": "realtime_sync", "status": "complete", "result": {"file": str(path)}}
                    try:
                        r.publish("scan_progress", json.dumps(payload))
                    except Exception:
                        pass
        except Exception as e:
            logger.error("Real-time sync failed for %s: %s", path, e)
            from backend.db.engine import log_audit_entry
            log_audit_entry("sync_error", "error", f"Real-time sync failed for {path.name}: {e}")

    def on_created(self, event):
        if not event.is_directory:
            self.process_path(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self.process_path(event.dest_path)


class WatcherService:
    def __init__(self):
        self.observer = Observer()
        self.watches: Dict[str, object] = {}
        self.lock = Lock()
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.event_handler = SyncEventHandler(self.executor)

    def start(self):
        self.observer.start()
        self._sync_watches_from_db()

    def stop(self):
        self.observer.stop()
        self.observer.join()
        self.executor.shutdown(wait=False)

    def _sync_watches_from_db(self):
        with self.lock:
            with SessionLocal() as session:
                synced_dirs = session.query(SyncedDirectory).filter(SyncedDirectory.is_active.is_(True)).all()
                active_paths = {sd.path for sd in synced_dirs if os.path.isdir(sd.path)}

            current_paths = set(self.watches.keys())

            # Remove stopped paths
            for path in current_paths - active_paths:
                watch = self.watches.pop(path)
                self.observer.unschedule(watch)
                logger.info("Stopped watching directory: %s", path)

            # Add new paths
            for path in active_paths - current_paths:
                try:
                    watch = self.observer.schedule(self.event_handler, path, recursive=True)
                    self.watches[path] = watch
                    logger.info("Started watching directory: %s", path)
                except Exception as e:
                    logger.error("Failed to watch %s: %s", path, e)

    def add_directory(self, path: str):
        with SessionLocal() as session:
            existing = session.query(SyncedDirectory).filter_by(path=path).first()
            if not existing:
                sd = SyncedDirectory(path=path, is_active=True)
                session.add(sd)
                session.commit()
            elif not existing.is_active:
                existing.is_active = True
                session.commit()
        self._sync_watches_from_db()

    def remove_directory(self, id: str):
        self._sync_watches_from_db()

watcher_service = WatcherService()
