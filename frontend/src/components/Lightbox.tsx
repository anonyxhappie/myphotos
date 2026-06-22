import { useCallback, useEffect, useRef, useState } from 'react';
import type { MediaItemDetail, MediaItemSummary } from '../api/types';
import {
  fetchMediaDetail,
  getOriginalUrl,
  getPreviewUrl,
  getThumbUrl,
  toggleFavorite,
  toggleLock,
  openInFinder,
} from '../api/client';

interface LightboxProps {
  mediaId: string;
  item: MediaItemSummary;
  previousItem?: MediaItemSummary;
  nextItem?: MediaItemSummary;
  direction: -1 | 0 | 1;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
}

function formatFileSize(bytes: number | null): string {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function isVideoType(mimeType: string): boolean {
  return mimeType.startsWith('video/');
}

function isGifType(mimeType: string): boolean {
  return mimeType === 'image/gif';
}

const COMMON_VIDEO_EXTENSIONS = new Set([
  '.mp4', '.mov', '.avi', '.mkv', '.m4v', '.3gp', '.wmv', '.webm', '.ogv',
]);

function inferMediaType(mime: string | null | undefined, filename?: string): 'image' | 'video' | 'unknown' {
  if (mime) {
    if (mime.startsWith('video/')) return 'video';
    if (mime.startsWith('image/')) return 'image';
    return 'unknown';
  }
  if (filename) {
    const ext = filename.slice(filename.lastIndexOf('.')).toLowerCase();
    if (COMMON_VIDEO_EXTENSIONS.has(ext)) return 'video';
  }
  return 'unknown';
}

export default function Lightbox({
  mediaId,
  item,
  previousItem,
  nextItem,
  direction,
  onClose,
  onPrev,
  onNext,
}: LightboxProps) {
  const [detail, setDetail] = useState<MediaItemDetail | null>(null);
  const [detailError, setDetailError] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const [previewLoaded, setPreviewLoaded] = useState(false);
  const [originalLoaded, setOriginalLoaded] = useState(false);
  const [originalFailed, setOriginalFailed] = useState(false);
  const [videoFailed, setVideoFailed] = useState(false);
  const touchStartX = useRef<number | null>(null);

  // Use summary's mime_type for type detection — it's always fresh (from props),
  // unlike detail which lags by one render during navigation.
  const mediaType = inferMediaType(item.mime_type);
  const isVideo = mediaType === 'video';
  const isGif = isGifType(item.mime_type || detail?.mime_type || '');
  const isImage = mediaType === 'image';
  const hasPreview = Boolean(detail?.preview_path);
  const originalAvailable = detail?.original_available ?? item.is_online;
  const transitionClass = direction > 0
    ? 'media-enter-next'
    : direction < 0
      ? 'media-enter-previous'
      : 'media-enter';

  useEffect(() => {
    let cancelled = false;

    fetchMediaDetail(mediaId)
      .then((response) => {
        if (!cancelled) setDetail(response);
      })
      .catch((error) => {
        console.error('Failed to load media detail:', error);
        if (!cancelled) setDetailError(true);
      });

    return () => {
      cancelled = true;
    };
  }, [mediaId]);

  // Reset states when navigating to a different media item.
  // Clearing detail prevents stale mime_type from the previous item
  // causing incorrect video/image classification during transition.
  useEffect(() => {
    setDetail(null);
    setDetailError(false);
    setPreviewLoaded(false);
    setOriginalLoaded(false);
    setOriginalFailed(false);
    setVideoFailed(false);
  }, [mediaId]);

  // Warm the adjacent previews so arrow navigation replaces the current
  // image immediately instead of revealing a blank frame.
  useEffect(() => {
    const preloaders = [previousItem, nextItem]
      .filter((candidate): candidate is MediaItemSummary => Boolean(candidate))
      .filter((candidate) => !isVideoType(candidate.mime_type || ''))
      .map((candidate) => {
        const image = new Image();
        image.src = getPreviewUrl(candidate.id);
        return image;
      });
    return () => {
      preloaders.forEach((image) => {
        image.src = '';
      });
    };
  }, [nextItem, previousItem]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA') return;

      if (event.key === 'Escape') onClose();
      if (event.key.toLowerCase() === 'i') setShowInfo((value) => !value);
      if (event.key === 'ArrowLeft' && onPrev) {
        event.preventDefault();
        onPrev();
      }
      if (event.key === 'ArrowRight' && onNext) {
        event.preventDefault();
        onNext();
      }
    },
    [onClose, onNext, onPrev],
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, []);

  const handleToggleFavorite = async () => {
    if (!detail) return;
    try {
      await toggleFavorite(mediaId);
      setDetail((current) => current ? { ...current, is_favorite: !current.is_favorite } : current);
    } catch (error) {
      console.error('Failed to update favorite:', error);
    }
  };

  const handleToggleLock = async () => {
    if (!detail) return;
    try {
      await toggleLock(mediaId);
      setDetail((current) => current ? { ...current, is_locked: !current.is_locked } : current);
    } catch (error) {
      console.error('Failed to update lock:', error);
    }
  };

  const handleOpenInFinder = async () => {
    try {
      await openInFinder(mediaId);
    } catch (error) {
      console.error('Failed to open in Finder:', error);
      alert(error instanceof Error ? error.message : 'Failed to open in Finder');
    }
  };

  const handleTouchEnd = (event: React.TouchEvent) => {
    if (touchStartX.current === null) return;
    const distance = event.changedTouches[0].clientX - touchStartX.current;
    touchStartX.current = null;
    if (Math.abs(distance) < 55) return;
    if (distance > 0) onPrev?.();
    else onNext?.();
  };

  const showLoading = isVideo
    ? !originalLoaded && !videoFailed
    : originalAvailable
      ? !(previewLoaded || originalLoaded) && !originalFailed
      : !previewLoaded && !originalFailed;
  const fallbackUrl = hasPreview ? getPreviewUrl(mediaId) : getThumbUrl(mediaId);

  return (
    <div className={`lightbox-backdrop ${showInfo ? 'has-info-panel' : ''}`} role="dialog" aria-modal="true">
      <header className="lightbox-toolbar">
        <button className="lightbox-icon-button" onClick={onClose} aria-label="Close viewer">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="m15 18-6-6 6-6" />
          </svg>
        </button>

        <div className="lightbox-title" title={detail?.filename || ''}>
          {detail?.filename || ''}
        </div>

        <div className="lightbox-actions">
          {originalAvailable && (
            <a
              className="lightbox-icon-button"
              href={getOriginalUrl(mediaId)}
              target="_blank"
              rel="noreferrer"
              aria-label="Open original"
              title="Open original"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M14 5h5v5M19 5l-8 8" />
                <path d="M19 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5" />
              </svg>
            </a>
          )}
          {originalAvailable && (
            <button
              className="lightbox-icon-button"
              onClick={handleOpenInFinder}
              aria-label="Open in Finder"
              title="Open in Finder"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ width: '20px', height: '20px' }}>
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
              </svg>
            </button>
          )}
          <button
            className={`lightbox-icon-button ${detail?.is_favorite ? 'is-active is-favorite' : ''}`}
            onClick={handleToggleFavorite}
            aria-label={detail?.is_favorite ? 'Remove from favorites' : 'Add to favorites'}
            title="Favorite"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78Z" />
            </svg>
          </button>
          <button
            className={`lightbox-icon-button ${detail?.is_locked ? 'is-active is-locked' : ''}`}
            onClick={handleToggleLock}
            aria-label={detail?.is_locked ? 'Unlock item' : 'Lock item'}
            title="Locked folder"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <rect x="4" y="10" width="16" height="10" rx="2" />
              <path d="M8 10V7a4 4 0 0 1 8 0v3" />
            </svg>
          </button>
          <button
            className={`lightbox-icon-button ${showInfo ? 'is-active' : ''}`}
            onClick={() => setShowInfo((value) => !value)}
            aria-label="Toggle media information"
            title="Info"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 11v5M12 8h.01" />
            </svg>
          </button>
        </div>
      </header>

      <main
        className="lightbox-viewer"
        onTouchStart={(event) => {
          touchStartX.current = event.touches[0].clientX;
        }}
        onTouchEnd={handleTouchEnd}
      >
        {onPrev && (
          <button className="lightbox-nav lightbox-nav-previous" onClick={onPrev} aria-label="Previous item">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg>
          </button>
        )}

        <div key={mediaId} className={`lightbox-media-stage ${transitionClass}`}>
          {showLoading && (
            <div className="lightbox-loading" aria-label="Loading full-resolution media">
              <span />
            </div>
          )}

          {isVideo ? (
            originalAvailable ? (
              <video
                key={mediaId}
                className={`lightbox-video ${originalLoaded ? 'is-loaded' : ''}`}
                controls
                autoPlay
                playsInline
                preload="metadata"
                poster={fallbackUrl}
                onLoadedMetadata={() => setOriginalLoaded(true)}
                onError={() => setVideoFailed(true)}
              >
                <source src={getOriginalUrl(mediaId)} type={detail?.mime_type || item.mime_type || undefined} />
                Your browser does not support this video format.
              </video>
            ) : (
              <MediaUnavailable message={detail?.offline_message} />
            )
          ) : isImage ? (
            <>
              {(detail?.thumb_path || item.thumb_path) && (
                <img
                  className={`lightbox-media-layer lightbox-thumbnail ${previewLoaded || originalLoaded ? 'is-hidden' : ''}`}
                  src={getThumbUrl(mediaId)}
                  alt=""
                  aria-hidden="true"
                />
              )}

              {hasPreview && !isGif && (
                <img
                  className={`lightbox-media-layer lightbox-preview ${previewLoaded && !originalLoaded ? 'is-visible' : ''}`}
                  src={getPreviewUrl(mediaId)}
                  alt=""
                  aria-hidden="true"
                  decoding="async"
                  onLoad={() => setPreviewLoaded(true)}
                />
              )}

              {hasPreview && isGif && !originalAvailable && (
                <img
                  className={`lightbox-media-layer lightbox-preview ${previewLoaded ? 'is-visible' : ''}`}
                  src={getPreviewUrl(mediaId)}
                  alt={detail?.filename || 'Media preview'}
                  decoding="async"
                  onLoad={() => setPreviewLoaded(true)}
                />
              )}

              {originalAvailable && (
                <img
                  className={`lightbox-media-layer lightbox-original ${originalLoaded ? 'is-visible' : ''}`}
                  src={getOriginalUrl(mediaId)}
                  alt={detail?.filename || 'Media preview'}
                  decoding="async"
                  onLoad={() => setOriginalLoaded(true)}
                  onError={() => setOriginalFailed(true)}
                />
              )}

              {!originalAvailable && !hasPreview && <MediaUnavailable message={detail?.offline_message} />}
              {originalFailed && !hasPreview && (
                <MediaUnavailable message="This image format cannot be displayed by this browser." />
              )}
            </>
          ) : (
            <MediaUnavailable message="This media format cannot be previewed in the browser." />
          )}
        </div>

        {onNext && (
          <button className="lightbox-nav lightbox-nav-next" onClick={onNext} aria-label="Next item">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6" /></svg>
          </button>
        )}

        {videoFailed && (
          <div className="lightbox-format-warning">
            This video codec is not supported by your browser.
            <a href={getOriginalUrl(mediaId)} target="_blank" rel="noreferrer">Open original</a>
          </div>
        )}
        {detailError && (
          <div className="lightbox-format-warning">Media details could not be loaded.</div>
        )}
      </main>

      {showInfo && detail && (
        <aside className="metadata-panel" aria-label="Media information">
          <div className="metadata-header">
            <div>
              <h2>{detail.filename}</h2>
              <p>{detail.original_path}</p>
            </div>
            <button className="lightbox-icon-button" onClick={() => setShowInfo(false)} aria-label="Close information">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" /></svg>
            </button>
          </div>
          <div className="metadata-content">
            <InfoSection title="Date">
              <InfoRow label="Taken" value={formatDate(detail.date_taken)} />
              <InfoRow label="Modified" value={formatDate(detail.date_modified)} />
              <InfoRow label="Ingested" value={formatDate(detail.ingested_at)} />
            </InfoSection>

            {(detail.camera_make || detail.camera_model) && (
              <InfoSection title="Camera">
                <InfoRow label="Device" value={[detail.camera_make, detail.camera_model].filter(Boolean).join(' ')} />
                {detail.lens_model && <InfoRow label="Lens" value={detail.lens_model} />}
                {detail.aperture && <InfoRow label="Aperture" value={`ƒ/${detail.aperture}`} />}
                {detail.exposure_time && <InfoRow label="Shutter" value={detail.exposure_time} />}
                {detail.iso && <InfoRow label="ISO" value={String(detail.iso)} />}
                {detail.focal_length_mm && <InfoRow label="Focal length" value={`${detail.focal_length_mm} mm`} />}
              </InfoSection>
            )}

            <InfoSection title="File">
              <InfoRow label="Size" value={formatFileSize(detail.file_size_bytes)} />
              <InfoRow label="Type" value={detail.mime_type || '—'} />
              <InfoRow
                label="Resolution"
                value={detail.width && detail.height ? `${detail.width} × ${detail.height}` : '—'}
              />
              {detail.duration_seconds && <InfoRow label="Duration" value={`${detail.duration_seconds.toFixed(1)} s`} />}
            </InfoSection>

            {(detail.latitude || detail.longitude) && (
              <InfoSection title="Location">
                <InfoRow label="Coordinates" value={`${detail.latitude?.toFixed(6)}, ${detail.longitude?.toFixed(6)}`} />
                {detail.altitude_m && <InfoRow label="Altitude" value={`${detail.altitude_m.toFixed(0)} m`} />}
              </InfoSection>
            )}

            <InfoSection title="Storage">
              <InfoRow label="Drive" value={detail.volume_label || 'Local storage'} />
              <InfoRow label="Original" value={detail.original_available ? 'Available' : 'Offline'} />
            </InfoSection>

            {detail.google_description && (
              <InfoSection title="Description">
                <p className="metadata-description">{detail.google_description}</p>
              </InfoSection>
            )}

            {detail.tags && detail.tags.length > 0 && (
              <InfoSection title="AI Tags">
                <div className="metadata-tags">
                  {detail.tags.filter(t => t.source !== 'ai_ocr').map(tag => (
                    <span key={tag.id} className="tag-chip" title={`Source: ${tag.source}`}>
                      {tag.name}
                    </span>
                  ))}
                </div>
              </InfoSection>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}

function MediaUnavailable({ message }: { message?: string | null }) {
  return (
    <div className="media-unavailable">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 16.5V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v10.5" />
        <path d="m4 15 4-4 3 3 2-2 7 7M8.5 8.5h.01" />
        <path d="M3 20h18" />
      </svg>
      <p>{message || 'The original media is unavailable.'}</p>
    </div>
  );
}

function InfoSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="metadata-section">
      <h3>{title}</h3>
      <div>{children}</div>
    </section>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="metadata-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
