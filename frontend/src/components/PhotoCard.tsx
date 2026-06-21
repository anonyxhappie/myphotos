import { useState, useCallback } from 'react';
import type { MediaItemSummary } from '../api/types';
import { getThumbUrl } from '../api/client';

interface PhotoCardProps {
  item: MediaItemSummary;
  selectionMode?: boolean;
  isSelected?: boolean;
  onSelectToggle?: (item: MediaItemSummary, event?: React.MouseEvent) => void;
  onClick: (item: MediaItemSummary) => void;
}

export default function PhotoCard({ item, selectionMode, isSelected, onSelectToggle, onClick }: PhotoCardProps) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  const handleLoad = useCallback(() => setLoaded(true), []);
  const handleError = useCallback(() => setError(true), []);

  return (
    <div
      className={`photo-card w-full h-full group ${isSelected ? 'ring-2 ring-[var(--color-accent)] ring-offset-2 ring-offset-[var(--color-bg-primary)]' : ''}`}
      onClick={(e) => {
        if ((selectionMode || isSelected) && onSelectToggle) {
          onSelectToggle(item, e);
        } else {
          onClick(item);
        }
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        if ((selectionMode || isSelected) && onSelectToggle) {
          onSelectToggle(item);
        } else {
          onClick(item);
        }
      }}
      aria-label={`Photo ${item.id}`}
    >
      {/* Skeleton while loading */}
      {!loaded && !error && (
        <div className="skeleton absolute inset-0" />
      )}

      {/* Thumbnail image */}
      {item.thumb_path && !error ? (
        <img
          src={getThumbUrl(item.id)}
          alt=""
          loading="lazy"
          decoding="async"
          onLoad={handleLoad}
          onError={handleError}
          className={loaded ? 'img-loaded' : ''}
          style={{ opacity: loaded ? 1 : 0 }}
        />
      ) : (
        <div
          className="w-full h-full flex items-center justify-center"
          style={{ background: 'var(--color-bg-tertiary)' }}
        >
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--color-text-muted)"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
        </div>
      )}

      {/* Hover overlay with gradient */}
      <div className={`overlay ${isSelected ? 'opacity-100 bg-black/20' : ''}`} />

      {/* Selection Checkmark */}
      <div 
        className={`absolute top-2 left-2 z-10 w-6 h-6 rounded-full border-2 transition-all flex items-center justify-center cursor-pointer
          ${isSelected ? 'bg-[var(--color-accent)] border-[var(--color-accent)]' : 'border-white/50 bg-black/20 opacity-0 group-hover:opacity-100 hover:border-white'}`}
        onClick={(e) => {
          e.stopPropagation();
          onSelectToggle?.(item, e);
        }}
      >
        {isSelected && (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        )}
      </div>

      {/* Badges */}
      <div className="absolute top-1.5 right-1.5 flex gap-1">
        {item.is_favorite && (
          <span className="badge-favorite text-[var(--color-danger)] bg-black/50 p-1 rounded-full" title="Favorite">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
            </svg>
          </span>
        )}
        {item.is_locked && (
          <span className="badge-locked text-[var(--color-warning)] bg-black/50 p-1 rounded-full" title="Locked">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          </span>
        )}
        {!item.is_online && (
          <span className="badge badge-offline" title="Drive offline">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="1" y1="1" x2="23" y2="23" />
              <path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55" />
              <path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39" />
              <path d="M10.71 5.05A16 16 0 0 1 22.56 9" />
              <path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88" />
              <path d="M8.53 16.11a6 6 0 0 1 6.95 0" />
              <line x1="12" y1="20" x2="12.01" y2="20" />
            </svg>
          </span>
        )}
      </div>

      {item.mime_type?.startsWith('video/') && (
        <div className="video-indicator" title="Video">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="m9 7 8 5-8 5z" />
          </svg>
        </div>
      )}
    </div>
  );
}
