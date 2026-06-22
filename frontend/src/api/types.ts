// ─── API Response Types ─────────────────────────────────────────
// Mirror the Pydantic schemas from the backend.

export interface MediaItemSummary {
  id: string;
  sha256: string;
  thumb_path: string | null;
  date_taken: string | null;
  date_modified: string | null;
  width: number | null;
  height: number | null;
  mime_type: string | null;
  is_favorite: boolean;
  is_locked: boolean;
  is_online: boolean;
}

export interface MediaItemDetail {
  id: string;
  sha256: string;
  phash: string | null;

  volume_id: string | null;
  original_path: string;
  filename: string;
  mime_type: string | null;
  file_size_bytes: number | null;

  thumb_path: string | null;
  preview_path: string | null;

  date_taken: string | null;
  date_modified: string | null;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  camera_make: string | null;
  camera_model: string | null;
  lens_model: string | null;
  iso: number | null;
  focal_length_mm: number | null;
  aperture: number | null;
  exposure_time: string | null;

  latitude: number | null;
  longitude: number | null;
  altitude_m: number | null;

  google_description: string | null;
  is_favorite: boolean;
  is_archived: boolean;
  is_trashed: boolean;
  is_locked: boolean;

  clip_embedded: boolean;
  faces_scanned: boolean;

  ingested_at: string;
  updated_at: string;

  is_online: boolean;
  original_available: boolean;
  volume_label: string | null;
  offline_message: string | null;
  tags: Tag[];
}

export interface Tag {
  id: string;
  name: string;
  source: string;
}

export interface TimelineResponse {
  items: MediaItemSummary[];
  next_cursor: string | null;
  total_count: number;
  total_size_bytes: number;
}

export interface VolumeResponse {
  id: string;
  os_uuid: string;
  label: string | null;
  mount_point: string | null;
  is_online: boolean;
  total_bytes: number | null;
  free_bytes: number | null;
  created_at: string;
  updated_at: string;
}

export interface ScanEnqueuedResponse {
  task_id: string;
  message: string;
  path?: string;
}

export interface ScanProgress {
  total_found: number;
  processed: number;
  new_inserted: number;
  duplicates_skipped: number;
  errors: number;
  faces_found?: number;
  labels_found?: number;
  current_file?: string | null;
  start_time?: number | null;
}

export interface ScanStatusResponse {
  task_id: string;
  status: 'pending' | 'running' | 'pausing' | 'paused' | 'complete' | 'error';
  progress?: ScanProgress | null;
  result?: Record<string, unknown> | null;
  path?: string | null;
  mode?: 'scan' | 'takeout';
  generate_thumbs?: boolean;
  error_message?: string | null;
}

// ─── Date grouping helper types ─────────────────────────────────

export interface DateGroup {
  label: string;  // e.g. "January 2024"
  items: MediaItemSummary[];
}

// ─── Settings ─────────────────────────────────

export interface SyncedDirectory {
  id: string;
  path: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  task_id?: string;
  total_files: number;
  synced_files: number;
  cover_media_ids: string[];
}

export interface Album {
  id: string;
  title: string;
  description: string | null;
  cover_media_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface AuditLog {
  id: string;
  timestamp: string;
  action: string;
  level: 'info' | 'success' | 'warning' | 'error';
  details: string | null;
}
