import { useState } from 'react';
import Timeline from './Timeline';
import type { MediaItemSummary } from '../api/types';

interface LockedFolderProps {
  onPhotoClick: (item: MediaItemSummary, list: MediaItemSummary[]) => void;
}

export default function LockedFolder({ onPhotoClick }: LockedFolderProps) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [pin, setPin] = useState('');
  const [error, setError] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Simplified PIN for local MVP Phase 1
    if (pin === '1234') {
      setIsAuthenticated(true);
      setError(false);
    } else {
      setError(true);
      setPin('');
    }
  };

  if (isAuthenticated) {
    return (
      <Timeline 
        searchQuery="" 
        lockedOnly={true} 
        onPhotoClick={onPhotoClick} 
        onTotalCountChange={() => {}} 
      />
    );
  }

  return (
    <div className="flex flex-col items-center justify-center w-full h-full p-8">
      <div className="bg-white/5 border border-white/10 rounded-2xl p-8 w-full max-w-sm text-center">
        <svg className="w-16 h-16 mx-auto mb-6 text-white/40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
        </svg>
        <h2 className="text-2xl font-medium text-[var(--color-text-primary)] mb-2">Locked Folder</h2>
        <p className="text-sm text-[var(--color-text-secondary)] mb-8">Enter your PIN to view locked photos.</p>
        
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <input 
            type="password" 
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            className="bg-black/20 border border-white/10 rounded-lg px-4 py-3 text-center tracking-[0.5em] text-xl outline-none focus:border-[var(--color-accent)] transition-colors"
            placeholder="****"
            maxLength={4}
            autoFocus
          />
          {error && <p className="text-[var(--color-danger)] text-sm">Incorrect PIN. Try 1234.</p>}
          <button 
            type="submit"
            className="bg-[var(--color-accent)] text-white font-medium rounded-lg px-4 py-3 hover:bg-opacity-90 transition-colors mt-2"
          >
            Unlock
          </button>
        </form>
      </div>
    </div>
  );
}
