import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchSyncedDirectories, addSyncedDirectory, getThumbUrl, selectFolder } from '../api/client';
import type { SyncedDirectory } from '../api/types';
import { dialog } from './DialogContainer';

export default function Folders() {
  const [folders, setFolders] = useState<SyncedDirectory[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const navigate = useNavigate();

  const loadFolders = () => {
    fetchSyncedDirectories()
      .then(setFolders)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadFolders();
  }, []);

  const handleAddClick = async () => {
    if (adding) return;
    setAdding(true);
    try {
      const res = await selectFolder();
      if (res.path) {
        await addSyncedDirectory(res.path);
        loadFolders();
      }
    } catch (e) {
      console.error(e);
      dialog.alert('Failed to add directory');
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="timeline-view text-white">
      <div className="timeline-toolbar">
        <div className="timeline-heading">
          <h1>Folders</h1>
        </div>
        <button
          onClick={handleAddClick}
          disabled={adding}
          className="outlined-action-button"
        >
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          {adding ? 'Adding...' : 'Add folder'}
        </button>
      </div>

      <div className="timeline-scroller overflow-y-auto px-7 py-6">
        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="animate-pulse">
                <div className="aspect-square bg-white/5 rounded-2xl mb-3" />
                <div className="h-5 bg-white/5 rounded w-2/3 mb-2" />
                <div className="h-4 bg-white/5 rounded w-1/2" />
              </div>
            ))}
          </div>
        ) : folders.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-[var(--color-text-secondary)]">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" className="mb-4 text-white/20">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            </svg>
            <h2 className="text-xl font-medium text-[var(--color-text-primary)] mb-2">No folders synced</h2>
            <p className="text-sm">Go to Settings to add local folders to your library.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
            {folders.map((folder) => (
              <button
                key={folder.id}
                onClick={() => navigate(`/folders/${folder.id}`)}
                className="group text-left"
              >
                <div className="aspect-square bg-white/5 rounded-2xl mb-3 flex items-center justify-center overflow-hidden border border-white/5 group-hover:border-white/20 transition-colors relative">
                  {folder.cover_media_ids && folder.cover_media_ids.length > 0 ? (
                    <div className={`w-full h-full grid ${folder.cover_media_ids.length >= 4 ? 'grid-cols-2 grid-rows-2' : 'grid-cols-1'} gap-0.5 bg-black`}>
                      {folder.cover_media_ids.slice(0, 4).map(id => (
                        <img key={id} src={getThumbUrl(id)} alt="" className="w-full h-full object-cover" />
                      ))}
                    </div>
                  ) : (
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" className="text-white/20 group-hover:text-[var(--color-accent)] transition-colors">
                      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                    </svg>
                  )}
                </div>
                <h3 className="font-medium text-[var(--color-text-primary)] truncate" title={folder.path}>
                  {folder.path.split('/').pop() || folder.path}
                </h3>
                <p className="text-sm text-[var(--color-text-secondary)]">
                  {folder.synced_files.toLocaleString()} items
                </p>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
