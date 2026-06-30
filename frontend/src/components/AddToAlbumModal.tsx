import { useState, useEffect } from 'react';
import { fetchAlbums, createAlbum, addMediaToAlbum, addDirectoryToAlbums } from '../api/client';
import type { Album } from '../api/types';
import { dialog } from './DialogContainer';

interface AddToAlbumModalProps {
  selectedIds: string[];
  dirId?: string;
  onClose: () => void;
  onSuccess: () => void;
}

export default function AddToAlbumModal({ selectedIds, dirId, onClose, onSuccess }: AddToAlbumModalProps) {
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [newTitle, setNewTitle] = useState('');

  useEffect(() => {
    fetchAlbums().then(data => {
      setAlbums(data);
      setLoading(false);
    }).catch(err => {
      console.error(err);
      setLoading(false);
    });
  }, []);

  const handleSelectAlbum = async (albumId: string) => {
    if (submitting) return;
    setSubmitting(true);
    try {
      if (dirId) {
        await addDirectoryToAlbums(dirId, [albumId]);
      } else {
        await addMediaToAlbum(albumId, selectedIds);
      }
      onSuccess();
    } catch (e) {
      console.error(e);
      dialog.alert('Failed to add to album');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCreateAndAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim() || submitting) return;
    setSubmitting(true);
    try {
      const album = await createAlbum(newTitle.trim());
      if (dirId) {
        await addDirectoryToAlbums(dirId, [album.id]);
      } else {
        await addMediaToAlbum(album.id, selectedIds);
      }
      onSuccess();
    } catch (e) {
      console.error(e);
      dialog.alert('Failed to create album or add photos');
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div 
        className="bg-[#1a1a1a] rounded-2xl border border-white/10 w-full max-w-md shadow-2xl overflow-hidden flex flex-col max-h-[80vh]"
        onClick={e => e.stopPropagation()}
      >
        <div className="p-6 border-b border-white/5 flex justify-between items-center shrink-0">
          <h3 className="text-xl font-medium text-white">Add to Album</h3>
          <button onClick={onClose} className="text-white/50 hover:text-white transition-colors">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1">
          <form onSubmit={handleCreateAndAdd} className="mb-6 flex gap-3">
            <input 
              type="text" 
              placeholder="New album title..."
              value={newTitle}
              onChange={e => setNewTitle(e.target.value)}
              className="flex-1 bg-black/20 border border-white/10 rounded-lg px-4 py-2 text-white outline-none focus:border-[var(--color-accent)] transition-colors"
            />
            <button 
              type="submit"
              disabled={!newTitle.trim() || submitting}
              className="bg-[var(--color-accent)] text-white px-4 py-2 rounded-lg font-medium hover:bg-opacity-90 disabled:opacity-50 transition-opacity"
            >
              Create
            </button>
          </form>

          <div className="space-y-2">
            <h4 className="text-sm font-medium text-white/50 mb-3 px-1 uppercase tracking-wider">Your Albums</h4>
            {loading ? (
              <div className="animate-pulse space-y-2">
                {[1, 2, 3].map(i => (
                  <div key={i} className="h-14 bg-white/5 rounded-xl" />
                ))}
              </div>
            ) : albums.length === 0 ? (
              <div className="text-center py-8 text-white/40">
                No albums yet. Create one above!
              </div>
            ) : (
              albums.map(album => (
                <button
                  key={album.id}
                  disabled={submitting}
                  onClick={() => handleSelectAlbum(album.id)}
                  className="w-full flex items-center gap-4 p-3 rounded-xl hover:bg-white/5 transition-colors text-left border border-transparent hover:border-white/5 group disabled:opacity-50"
                >
                  <div className="w-12 h-12 bg-white/5 rounded-lg overflow-hidden shrink-0 relative">
                    {album.cover_media_id ? (
                      <img src={`http://127.0.0.1:8000/api/media/${album.cover_media_id}/thumb`} className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-white/20">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                          <circle cx="8.5" cy="8.5" r="1.5" />
                          <polyline points="21 15 16 10 5 21" />
                        </svg>
                      </div>
                    )}
                  </div>
                  <span className="font-medium text-white/90 group-hover:text-white truncate">
                    {album.title}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
