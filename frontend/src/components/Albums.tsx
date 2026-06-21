import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchAlbums, createAlbum, getThumbUrl } from '../api/client';
import type { Album } from '../api/types';

export default function Albums() {
  const navigate = useNavigate();
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');

  const loadAlbums = async () => {
    try {
      const data = await fetchAlbums();
      setAlbums(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let isActive = true;
    fetchAlbums()
      .then((data) => {
        if (isActive) setAlbums(data);
      })
      .catch((error) => console.error(error))
      .finally(() => {
        if (isActive) setLoading(false);
      });

    return () => {
      isActive = false;
    };
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    try {
      await createAlbum(newTitle.trim());
      setNewTitle('');
      setShowCreate(false);
      loadAlbums();
    } catch (e) {
      console.error(e);
      alert('Failed to create album');
    }
  };

  return (
    <div className="page-scroll albums-page">
      <div className="page-heading-row">
        <div>
          <h1>Albums</h1>
          <p>Keep related photos together and easy to find.</p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="outlined-action-button"
        >
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Create album
        </button>
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="album-create-panel">
          <h2>New album</h2>
          <div className="album-create-fields">
            <input
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Album title"
              className="input-field"
              autoFocus
            />
            <button type="submit" className="btn-primary">
              Create
            </button>
            <button type="button" onClick={() => setShowCreate(false)} className="text-button">
              Cancel
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="albums-grid" aria-label="Loading albums">
          <div className="album-skeleton skeleton" />
          <div className="album-skeleton skeleton" />
          <div className="album-skeleton skeleton" />
        </div>
      ) : albums.length === 0 ? (
        <div className="albums-empty-state">
          <div className="albums-empty-icon">
            <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="4" y="4" width="16" height="16" rx="3" />
              <path d="M8 2h8M8 22h8" />
              <line x1="12" y1="8" x2="12" y2="16" />
              <line x1="8" y1="12" x2="16" y2="12" />
            </svg>
          </div>
          <h2>Create your first album</h2>
          <p>Albums make it easier to revisit trips, events, and favourite moments.</p>
        </div>
      ) : (
        <div className="albums-grid">
          {albums.map((album) => (
            <button
              type="button"
              key={album.id} 
              className="album-card"
              onClick={() => navigate(`/albums/${album.id}`)}
            >
              <div className="album-cover">
                {album.cover_media_id ? (
                  <img src={getThumbUrl(album.cover_media_id)} alt="" />
                ) : (
                  <div className="album-cover-placeholder">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                      <circle cx="8.5" cy="8.5" r="1.5" />
                      <polyline points="21 15 16 10 5 21" />
                    </svg>
                  </div>
                )}
              </div>
              <span className="album-title">{album.title}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
