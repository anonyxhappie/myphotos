import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Timeline from './Timeline';
import type { MediaItemSummary, SyncedDirectory } from '../api/types';
import { fetchSyncedDirectory } from '../api/client';

interface FolderDetailProps {
  onPhotoClick: (item: MediaItemSummary, list: MediaItemSummary[]) => void;
  onTotalCountChange: (count: number, size: number) => void;
}

export default function FolderDetail({ onPhotoClick, onTotalCountChange }: FolderDetailProps) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [folder, setFolder] = useState<SyncedDirectory | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchSyncedDirectory(id)
      .then(setFolder)
      .catch(console.error);
  }, [id]);

  if (!id) return null;

  return (
    <div className="w-full h-full flex flex-col relative">
      <div className="px-8 py-6 flex items-center justify-between shrink-0 border-b border-white/5 bg-[var(--color-bg-primary)] z-10 sticky top-0">
        <div className="flex items-center gap-4">
          <button 
            onClick={() => navigate('/folders')}
            className="btn-ghost text-[var(--color-text-secondary)] hover:text-white"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <h2 className="text-xl font-medium tracking-tight text-[var(--color-text-primary)]">
            {folder ? (folder.path.split('/').pop() || folder.path) : 'Folder'}
          </h2>
        </div>
      </div>

      <div className="flex-1 overflow-hidden relative">
        <Timeline 
          searchQuery="" 
          dirId={id}
          onPhotoClick={onPhotoClick} 
          onTotalCountChange={onTotalCountChange} 
        />
      </div>
    </div>
  );
}
