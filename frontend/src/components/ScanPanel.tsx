import { useState } from 'react';
import { selectFolder, triggerScan, triggerTakeout } from '../api/client';

interface ScanPanelProps {
  onClose: () => void;
  onScanStarted: (taskId: string, path: string, mode: 'scan' | 'takeout') => void;
}

export default function ScanPanel({ onClose, onScanStarted }: ScanPanelProps) {
  const [path, setPath] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const [mode, setMode] = useState<'scan' | 'takeout'>('scan');

  const handleBrowse = async () => {
    try {
      const result = await selectFolder();
      if (result.path) {
        setPath(result.path);
      }
    } catch (err) {
      console.error('Failed to select folder', err);
    }
  };

  const handleSubmit = async () => {
    if (!path.trim()) return;
    setStatus('loading');
    setMessage('');

    try {
      const result = mode === 'scan'
        ? await triggerScan(path.trim())
        : await triggerTakeout(path.trim());

      setStatus('success');
      setMessage(`✓ ${result.message} (Task: ${result.task_id.slice(0, 8)}…)`);
      
      // Notify parent that scan has started and close panel
      onScanStarted(result.task_id, path.trim(), mode);
      onClose();
    } catch (err) {
      setStatus('error');
      setMessage(err instanceof Error ? err.message : 'Failed to enqueue scan');
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-content glass"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Title */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            {mode === 'scan' ? 'Scan Directory' : 'Import Google Takeout'}
          </h2>
          <button
            className="btn-ghost"
            onClick={onClose}
            aria-label="Close"
            style={{ padding: '0.375rem' }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Mode toggle */}
        <div
          className="flex rounded-lg p-0.5 mb-4"
          style={{ background: 'var(--color-bg-primary)' }}
        >
          <button
            className="flex-1 py-2 rounded-md text-sm font-medium transition-colors"
            style={{
              background: mode === 'scan' ? 'var(--color-surface)' : 'transparent',
              color: mode === 'scan' ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
            }}
            onClick={() => setMode('scan')}
          >
            Directory Scan
          </button>
          <button
            className="flex-1 py-2 rounded-md text-sm font-medium transition-colors"
            style={{
              background: mode === 'takeout' ? 'var(--color-surface)' : 'transparent',
              color: mode === 'takeout' ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
            }}
            onClick={() => setMode('takeout')}
          >
            Google Takeout
          </button>
        </div>

        {/* Path input */}
        <label className="block mb-1.5 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
          {mode === 'scan' ? 'Photos directory path' : 'Takeout export directory path'}
        </label>
        
        <div className="flex gap-2 mb-4">
          <input
            id="scan-path-input"
            type="text"
            className="input-field flex-1"
            placeholder={mode === 'scan' ? '/Users/you/Photos' : '/Users/you/Downloads/Takeout'}
            value={path}
            onChange={(e) => setPath(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            autoFocus
          />
          <button
            type="button"
            className="btn-ghost"
            onClick={handleBrowse}
            style={{
              padding: '0.75rem 1.25rem',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-md)',
              whiteSpace: 'nowrap',
            }}
          >
            Browse…
          </button>
        </div>

        {/* Hint */}
        <p className="text-xs mb-5" style={{ color: 'var(--color-text-muted)' }}>
          {mode === 'scan'
            ? 'The scanner will recursively find all photos and videos, compute content hashes, extract EXIF data, and generate WebP thumbnails.'
            : 'Point this to your Google Takeout export folder. The parser will merge companion JSON metadata (GPS, timestamps) with your photos.'}
        </p>

        {/* Status message */}
        {message && (
          <div
            className="mb-4 p-3 rounded-lg text-sm"
            style={{
              background: status === 'success' ? 'rgba(52,211,153,0.1)' : 'rgba(248,113,113,0.1)',
              color: status === 'success' ? 'var(--color-success)' : 'var(--color-danger)',
              border: `1px solid ${status === 'success' ? 'rgba(52,211,153,0.2)' : 'rgba(248,113,113,0.2)'}`,
            }}
          >
            {message}
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3 justify-end">
          <button className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn-primary"
            onClick={handleSubmit}
            disabled={status === 'loading' || !path.trim()}
            style={{ opacity: status === 'loading' || !path.trim() ? 0.5 : 1 }}
          >
            {status === 'loading' ? (
              <>
                <div
                  className="w-4 h-4 rounded-full border-2 border-white/30"
                  style={{ borderTopColor: 'white', animation: 'spin 0.8s linear infinite' }}
                />
                Scanning…
              </>
            ) : (
              mode === 'scan' ? 'Start Scan' : 'Import Takeout'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
