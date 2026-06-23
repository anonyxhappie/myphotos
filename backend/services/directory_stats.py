import os
import threading
import time
from pathlib import Path
from backend.config import settings

# Global cache: path -> (timestamp, count)
_dir_stats_cache = {}
_cache_lock = threading.Lock()
# Track paths currently being computed to avoid redundant threads
_computing_paths = set()

def _compute_total_files(path_obj: Path, path_str: str):
    total_files = 0
    try:
        if path_obj.is_dir():
            for dirpath, dirnames, filenames in os.walk(path_obj):
                # Ignore hidden directories (starting with '.')
                dirnames[:] = [d for d in dirnames if not d.startswith('.')]
                for fname in filenames:
                    # Ignore hidden files (starting with '.') and macOS shadow/metadata files (starting with '._')
                    if fname.startswith('.'):
                        continue
                    ext = Path(fname).suffix.lower()
                    if ext in settings.SUPPORTED_EXTENSIONS:
                        total_files += 1
    except Exception:
        pass

    with _cache_lock:
        _dir_stats_cache[path_str] = (time.time(), total_files)
        _computing_paths.discard(path_str)

def get_cached_total_files(path_obj: Path, ttl_seconds: int = 300) -> int:
    """
    Returns the cached total_files count for a directory.
    If the cache is empty or stale, it spawns a background thread to compute it
    and returns 0 (or the stale count) immediately.
    """
    path_str = str(path_obj)
    now = time.time()

    with _cache_lock:
        cached_data = _dir_stats_cache.get(path_str)

        needs_update = False
        if cached_data is None:
            needs_update = True
            count = 0
        else:
            timestamp, count = cached_data
            if now - timestamp > ttl_seconds:
                needs_update = True

        if needs_update and path_str not in _computing_paths:
            _computing_paths.add(path_str)
            # Spawn a daemon thread to compute the stat without blocking
            t = threading.Thread(target=_compute_total_files, args=(path_obj, path_str), daemon=True)
            t.start()

        return count
