import type {
  MediaItemDetail,
  MediaItemSummary,
  ScanEnqueuedResponse,
  ScanStatusResponse,
  TimelineResponse,
  VolumeResponse,
  SyncedDirectory,
  Album,
  AuditLog,
  TagWithCount,
} from './types';

// ─── Base URL ───────────────────────────────────────────────────
// Vite proxy forwards /api to the FastAPI backend during dev.
const BASE = '/api';

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

// ─── Timeline ───────────────────────────────────────────────────

export interface TimelineOptions {
  cursor?: string | null;
  limit?: number;
  favorites_only?: boolean;
  videos_only?: boolean;
  locked_only?: boolean;
  dir_id?: string;
  sort?: string;
}

export async function fetchTimeline(opts: TimelineOptions = {}): Promise<TimelineResponse> {
  const params = new URLSearchParams({ limit: String(opts.limit || 200) });
  if (opts.cursor) params.set('cursor', opts.cursor);
  if (opts.favorites_only) params.set('favorites_only', 'true');
  if (opts.videos_only) params.set('videos_only', 'true');
  if (opts.locked_only) params.set('locked_only', 'true');
  if (opts.dir_id) params.set('dir_id', opts.dir_id);
  if (opts.sort) params.set('sort', opts.sort);
  
  return fetchJson<TimelineResponse>(`${BASE}/timeline?${params}`);
}

// ─── Media Detail ───────────────────────────────────────────────

export async function fetchMediaDetail(id: string): Promise<MediaItemDetail> {
  return fetchJson<MediaItemDetail>(`${BASE}/media/${id}`);
}

// ─── URL builders (no fetch, just returns the URL) ──────────────

export function getThumbUrl(id: string): string {
  return `${BASE}/media/${id}/thumb?v=2`;
}

export function getPreviewUrl(id: string): string {
  return `${BASE}/media/${id}/preview?v=2`;
}

export function getOriginalUrl(id: string): string {
  return `${BASE}/media/${id}/original`;
}

// ─── Volumes ────────────────────────────────────────────────────

export async function fetchVolumes(): Promise<VolumeResponse[]> {
  return fetchJson<VolumeResponse[]>(`${BASE}/volumes`);
}

// ─── Scan ───────────────────────────────────────────────────────

export async function selectFolder(): Promise<{ path: string | null }> {
  return fetchJson<{ path: string | null }>(`${BASE}/select-folder`);
}

export async function triggerScan(
  path: string,
  generateThumbs = true,
): Promise<ScanEnqueuedResponse> {
  return fetchJson<ScanEnqueuedResponse>(`${BASE}/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, generate_thumbs: generateThumbs }),
  });
}

export async function triggerTakeout(
  path: string,
  generateThumbs = true,
): Promise<ScanEnqueuedResponse> {
  return fetchJson<ScanEnqueuedResponse>(`${BASE}/scan/takeout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, generate_thumbs: generateThumbs }),
  });
}

export async function fetchScanStatus(
  taskId: string,
): Promise<ScanStatusResponse> {
  return fetchJson<ScanStatusResponse>(`${BASE}/scan/status/${taskId}`);
}

export async function fetchScans(
  includeComplete = false,
): Promise<ScanStatusResponse[]> {
  const params = new URLSearchParams();
  if (includeComplete) params.set('include_complete', 'true');
  const query = params.toString();
  return fetchJson<ScanStatusResponse[]>(
    `${BASE}/scans${query ? `?${query}` : ''}`,
  );
}

export async function pauseScan(taskId: string): Promise<ScanStatusResponse> {
  return fetchJson<ScanStatusResponse>(`${BASE}/scan/${taskId}/pause`, {
    method: 'POST',
  });
}

export async function resumeScan(taskId: string): Promise<ScanStatusResponse> {
  return fetchJson<ScanStatusResponse>(`${BASE}/scan/${taskId}/resume`, {
    method: 'POST',
  });
}

export async function retryScan(taskId: string): Promise<ScanStatusResponse> {
  return fetchJson<ScanStatusResponse>(`${BASE}/scan/${taskId}/retry`, {
    method: 'POST',
  });
}

export async function deleteScan(
  taskId: string,
): Promise<{ status: string; message: string }> {
  return fetchJson<{ status: string; message: string }>(`${BASE}/scan/${taskId}`, {
    method: 'DELETE',
  });
}

// ─── ML Pipeline & Search ───────────────────────────────────────

export async function triggerMLPipeline(): Promise<ScanEnqueuedResponse> {
  return fetchJson<ScanEnqueuedResponse>(`${BASE}/ml/start`, {
    method: 'POST',
  });
}

export async function retrainML(): Promise<ScanEnqueuedResponse> {
  return fetchJson<ScanEnqueuedResponse>(`${BASE}/ml/retrain`, {
    method: 'POST',
  });
}

export async function resyncAll(): Promise<ScanEnqueuedResponse[]> {
  return fetchJson<ScanEnqueuedResponse[]>(`${BASE}/scan/resync_all`, {
    method: 'POST',
  });
}

export async function searchPhotos(query: string): Promise<TimelineResponse> {
  const params = new URLSearchParams({ q: query });
  return fetchJson<TimelineResponse>(`${BASE}/search?${params}`);
}

// ─── Health ─────────────────────────────────────────────────────

export async function fetchHealth(): Promise<{
  status: string;
  total_media_items: number;
  total_volumes: number;
  total_size_bytes: number;
}> {
  return fetchJson(`${BASE}/health`);
}

// ─── Settings ───────────────────────────────────────────────────

export async function fetchSyncedDirectories(): Promise<SyncedDirectory[]> {
  return fetchJson<SyncedDirectory[]>(`${BASE}/settings/synced-directories`);
}

export async function fetchSyncedDirectory(id: string): Promise<SyncedDirectory> {
  return fetchJson<SyncedDirectory>(`${BASE}/settings/synced-directories/${id}`);
}

export async function addSyncedDirectory(path: string): Promise<SyncedDirectory> {
  return fetchJson<SyncedDirectory>(`${BASE}/settings/synced-directories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
}

export async function removeSyncedDirectory(id: string): Promise<{status: string}> {
  return fetchJson<{status: string}>(`${BASE}/settings/synced-directories/${id}`, {
    method: 'DELETE',
  });
}

export async function factoryReset(): Promise<{status: string; message: string}> {
  return fetchJson<{status: string; message: string}>(`${BASE}/settings/factory-reset`, {
    method: 'POST',
  });
}

export async function fetchAuditLogs(): Promise<AuditLog[]> {
  return fetchJson<AuditLog[]>(`${BASE}/settings/audit-logs`);
}

export async function toggleFavorite(mediaId: string): Promise<MediaItemSummary> {
  return fetchJson<MediaItemSummary>(`${BASE}/media/${mediaId}/favorite`, { method: 'POST' });
}

export async function toggleLock(mediaId: string): Promise<MediaItemSummary> {
  return fetchJson<MediaItemSummary>(`${BASE}/media/${mediaId}/lock`, { method: 'POST' });
}

export async function bulkDeleteMedia(mediaIds: string[]): Promise<{status: string; deleted_count: number}> {
  return fetchJson<{status: string; deleted_count: number}>(`${BASE}/media/delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ media_ids: mediaIds }),
  });
}

export async function openInFinder(mediaId: string): Promise<{status: string}> {
  return fetchJson<{status: string}>(`${BASE}/media/${mediaId}/open-in-finder`, {
    method: 'POST',
  });
}

// ─── Albums ─────────────────────────────────────────────────────

export async function fetchAlbums(): Promise<Album[]> {
  return fetchJson<Album[]>(`${BASE}/albums`);
}

export async function createAlbum(title: string): Promise<Album> {
  return fetchJson<Album>(`${BASE}/albums`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
}

export async function fetchAlbumMedia(albumId: string): Promise<TimelineResponse> {
  return fetchJson<TimelineResponse>(`${BASE}/albums/${albumId}/media`);
}

export async function addMediaToAlbum(albumId: string, mediaIds: string[]): Promise<{status: string}> {
  return fetchJson<{status: string}>(`${BASE}/albums/${albumId}/media`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ media_ids: mediaIds }),
  });
}

export async function addDirectoryToAlbums(dirId: string, albumIds: string[]): Promise<{status: string; added: number}> {
  return fetchJson<{status: string; added: number}>(`${BASE}/synced-directories/${dirId}/add-to-albums`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ album_ids: albumIds }),
  });
}

// ─── Tags ───────────────────────────────────────────────────────

export async function fetchTags(source?: string): Promise<TagWithCount[]> {
  const url = source ? `${BASE}/tags?source=${encodeURIComponent(source)}` : `${BASE}/tags`;
  return fetchJson<TagWithCount[]>(url);
}

export async function createTag(name: string): Promise<TagWithCount> {
  return fetchJson<TagWithCount>(`${BASE}/tags`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

export async function deleteTag(tagId: string): Promise<{status: string}> {
  return fetchJson<{status: string}>(`${BASE}/tags/${tagId}`, {
    method: 'DELETE',
  });
}

export async function fetchTagMedia(tagId: string): Promise<TimelineResponse> {
  return fetchJson<TimelineResponse>(`${BASE}/tags/${tagId}/media`);
}

export async function triggerTagScan(tagId: string): Promise<ScanEnqueuedResponse> {
  return fetchJson<ScanEnqueuedResponse>(`${BASE}/tags/${tagId}/scan`, {
    method: 'POST',
  });
}

export async function fetchTagScanStatus(tagId: string): Promise<ScanStatusResponse> {
  return fetchJson<ScanStatusResponse>(`${BASE}/tags/${tagId}/scan/status`);
}
