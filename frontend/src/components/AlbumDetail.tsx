import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Timeline from './Timeline';
import type { MediaItemSummary, Album } from '../api/types';
import { fetchAlbums } from '../api/client';


import AddPhotosToAlbumModal from './AddPhotosToAlbumModal';

interface AlbumDetailProps {
  onPhotoClick: (item: MediaItemSummary, list: MediaItemSummary[]) => void;
  onTotalCountChange: (count: number, size: number) => void;
}

export default function AlbumDetail({ onPhotoClick, onTotalCountChange }: AlbumDetailProps) {
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
      <div className="timeline-toolbar">
        <div className="timeline-heading flex items-center gap-4">
          <button 
            onClick={() => navigate('/albums')}
            className="text-[var(--color-text-secondary)] hover:text-white flex items-center"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <h1>{album ? album.title : 'Album'}</h1>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="outlined-action-button"
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
          hideHeader={true}
          onPhotoClick={onPhotoClick} 
          onTotalCountChange={onTotalCountChange} 
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
