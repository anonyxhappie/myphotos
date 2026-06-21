interface EmptyStateProps {
  onScanClick: () => void;
}

export default function EmptyState({ onScanClick }: EmptyStateProps) {
  return (
    <div className="empty-state">
      {/* Icon */}
      <div className="empty-state-icon">
        <svg
          width="48"
          height="48"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <polyline points="21 15 16 10 5 21" />
        </svg>
      </div>

      {/* Text */}
      <div>
        <h2
          className="text-xl font-semibold mb-2"
          style={{ color: 'var(--color-text-primary)' }}
        >
          Your library is empty
        </h2>
        <p
          className="text-sm max-w-md"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          Scan a folder of photos to get started. MyPhotos will extract metadata,
          generate thumbnails, and build your timeline automatically.
        </p>
      </div>

      {/* CTA */}
      <button className="btn-primary text-base px-6 py-3" onClick={onScanClick}>
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
          <line x1="12" y1="11" x2="12" y2="17" />
          <line x1="9" y1="14" x2="15" y2="14" />
        </svg>
        Scan Your First Folder
      </button>

      {/* Keyboard hint */}
      <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
        Or import from Google Takeout
      </p>
    </div>
  );
}
