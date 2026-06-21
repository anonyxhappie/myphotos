import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Timeline from './Timeline';
import type { MediaItemSummary, Album } from '../api/types';
import { fetchAlbums } from '../api/client';


import AddPhotosToAlbumModal from './AddPhotosToAlbumModal';

interface AlbumDetailProps {
  onPhotoClick: (item: MediaItemSummary, list: MediaItemSummary[]) => void;
}

export default function AlbumDetail({ onPhotoClick }: AlbumDetailProps) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [album, setAlbum] = useState<Album | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [timelineKey, setTimelineKey] = useState(0);

  useEffect(() => {
    if (!id) return;
    fetchAlbums().then(albums => {
      const found = albums.find(a => a.id === id);
      if (found) setAlbum(found);
    }).catch(console.error);
  }, [id, timelineKey]);

  if (!id) return null;

  return (
    <div className="w-full h-full flex flex-col relative">
      <div className="px-8 py-6 flex items-center justify-between shrink-0 border-b border-white/5 bg-[var(--color-bg-primary)] z-10 sticky top-0">
        <div className="flex items-center gap-4">
          <button 
            onClick={() => navigate('/albums')}
            className="btn-ghost text-[var(--color-text-secondary)] hover:text-white"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <h2 className="text-xl font-medium tracking-tight text-[var(--color-text-primary)]">
            {album ? album.title : 'Album'}
          </h2>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="bg-[var(--color-accent)] text-white px-4 py-2 rounded-lg font-medium hover:bg-opacity-90 transition-opacity text-sm flex items-center gap-2"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Add Photos
        </button>
      </div>

      <div className="flex-1 overflow-hidden relative">
        <Timeline 
          key={timelineKey}
          searchQuery="" 
          albumId={id}
          onPhotoClick={onPhotoClick} 
          onTotalCountChange={() => {}} 
        />
      </div>

      {showAddModal && (
        <AddPhotosToAlbumModal
          albumId={id}
          onClose={() => setShowAddModal(false)}
          onSuccess={() => {
            setShowAddModal(false);
            setTimelineKey(prev => prev + 1);
          }}
        />
      )}
    </div>
  );
}
