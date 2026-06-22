import { NavLink } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { fetchAlbums, fetchTags } from '../api/client';
import type { Album, TagWithCount } from '../api/types';
interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  currentCount?: number;
  currentSize?: number;
}

function formatBytes(bytes: number) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

type IconName =
  | 'photos'
  | 'albums'
  | 'folders'
  | 'heart'
  | 'recent'
  | 'videos'
  | 'documents'
  | 'screenshots'
  | 'lock'
  | 'people'
  | 'settings'
  | 'tag';

function BrandMark() {
  return (
    <svg width="30" height="30" viewBox="0 0 28 28" aria-hidden="true">
      <circle cx="14" cy="7" r="6" fill="#ea4335" />
      <circle cx="21" cy="14" r="6" fill="#fbbc04" />
      <circle cx="14" cy="21" r="6" fill="#34a853" />
      <circle cx="7" cy="14" r="6" fill="#4285f4" />
      <circle cx="14" cy="14" r="3.25" fill="var(--color-bg-primary)" />
    </svg>
  );
}

function NavigationIcon({ name }: { name: IconName }) {
  const common = {
    width: 22,
    height: 22,
    viewBox: '0 0 24 24',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    fill: 'none',
  };

  if (name === 'photos') {
    return (
      <svg {...common}>
        <rect x="3" y="3" width="18" height="18" rx="3" />
        <circle cx="8.5" cy="8.5" r="1.5" />
        <path d="m4 17 4.5-4.5 3.5 3 3-3 5 5" />
      </svg>
    );
  }
  if (name === 'albums') {
    return (
      <svg {...common}>
        <rect x="4" y="4" width="16" height="16" rx="3" />
        <path d="M8 2h8M8 22h8" />
        <circle cx="9" cy="9" r="1.25" />
        <path d="m5 17 4-4 3 2.5 2-2 5 4" />
      </svg>
    );
  }
  if (name === 'folders') {
    return (
      <svg {...common}>
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
      </svg>
    );
  }
  if (name === 'heart') {
    return (
      <svg {...common}>
        <path d="M20.8 4.7a5.4 5.4 0 0 0-7.7 0L12 5.8l-1.1-1.1a5.4 5.4 0 0 0-7.7 7.7L12 21l8.8-8.6a5.4 5.4 0 0 0 0-7.7Z" />
      </svg>
    );
  }
  if (name === 'recent') {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3.5 2" />
      </svg>
    );
  }
  if (name === 'videos') {
    return (
      <svg {...common}>
        <rect x="3" y="5" width="18" height="14" rx="3" />
        <path d="m10 9 5 3-5 3Z" />
      </svg>
    );
  }
  if (name === 'documents') {
    return (
      <svg {...common}>
        <path d="M6 3h8l4 4v14H6z" />
        <path d="M14 3v5h5M9 12h6M9 16h6" />
      </svg>
    );
  }
  if (name === 'screenshots') {
    return (
      <svg {...common}>
        <path d="M8 3H4a1 1 0 0 0-1 1v4M16 3h4a1 1 0 0 1 1 1v4M8 21H4a1 1 0 0 1-1-1v-4M16 21h4a1 1 0 0 0 1-1v-4" />
        <rect x="7" y="7" width="10" height="10" rx="2" />
      </svg>
    );
  }
  if (name === 'lock') {
    return (
      <svg {...common}>
        <rect x="4" y="10" width="16" height="11" rx="3" />
        <path d="M8 10V7a4 4 0 0 1 8 0v3" />
      </svg>
    );
  }
  if (name === 'settings') {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.85l.05.05-2.9 2.9-.05-.05A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 1.55V21h-4v-.05A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.85.34l-.05.05-2.9-2.9.05-.05A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3v-4h.05A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.85L4.2 7.1l2.9-2.9.05.05A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3h4v.05A1.7 1.7 0 0 0 15 4.6a1.7 1.7 0 0 0 1.85-.34l.05-.05 2.9 2.9-.05.05A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 1.55 1H21v4h-.05A1.7 1.7 0 0 0 19.4 15Z" />
      </svg>
    );
  }
  if (name === 'people') {
    return (
      <svg {...common}>
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
        <circle cx="9" cy="7" r="4"></circle>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
        <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
      </svg>
    );
  }
  if (name === 'tag') {
    return (
      <svg {...common}>
        <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
        <circle cx="6.5" cy="6.5" r="1.5" fill="currentColor" />
      </svg>
    );
  }
  return null;
}


const libraryItems: Array<{ to: string; label: string; icon: IconName }> = [
  { to: '/favourites', label: 'Favourites', icon: 'heart' },
  { to: '/people', label: 'People & Pets', icon: 'people' },
  { to: '/recent', label: 'Recently added', icon: 'recent' },
  { to: '/videos', label: 'Videos', icon: 'videos' },
  { to: '/documents', label: 'Documents', icon: 'documents' },
  { to: '/screenshots', label: 'Screenshots', icon: 'screenshots' },
];

const utilityItems: Array<{ to: string; label: string; icon: IconName }> = [
  { to: '/locked', label: 'Locked folder', icon: 'lock' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
];

function NavItem({
  to,
  label,
  icon,
  end,
  onClick,
}: {
  to: string;
  label: string;
  icon: IconName;
  end?: boolean;
  onClick?: () => void;
}) {
  return (
    <NavLink to={to} end={end} className="sidebar-nav-item" onClick={onClick}>
      <NavigationIcon name={icon} />
      <span>{label}</span>
    </NavLink>
  );
}

export default function Sidebar({ isOpen, onClose, currentCount = 0, currentSize = 0 }: SidebarProps) {
  const [albums, setAlbums] = useState<Album[]>([]);
  const [albumsLoading, setAlbumsLoading] = useState(true);
  const [albumsExpanded, setAlbumsExpanded] = useState(true);
  const [tags, setTags] = useState<TagWithCount[]>([]);
  const [tagsLoading, setTagsLoading] = useState(true);
  const [tagsExpanded, setTagsExpanded] = useState(true);

  useEffect(() => {
    fetchAlbums()
      .then(setAlbums)
      .catch(console.error)
      .finally(() => setAlbumsLoading(false));

    fetchTags('user')
      .then(setTags)
      .catch(console.error)
      .finally(() => setTagsLoading(false));
  }, []);

  return (
    <>
      <button
        type="button"
        className={`sidebar-backdrop ${isOpen ? 'is-visible' : ''}`}
        onClick={onClose}
        aria-label="Close navigation"
      />

      <aside className={`app-sidebar ${isOpen ? 'is-open' : ''}`}>
        <div className="sidebar-brand">
          <BrandMark />
          <span>MyPhotos</span>
          <button type="button" className="icon-button sidebar-close-button" onClick={onClose} aria-label="Close navigation">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <nav className="sidebar-navigation" aria-label="Main navigation">
          <div className="sidebar-nav-group">
            <NavItem to="/" label="Photos" icon="photos" end onClick={onClose} />
            
            <div className="sidebar-albums-section">
              <div className="sidebar-nav-item-wrapper">
                <NavLink to="/albums" className="sidebar-nav-item" onClick={onClose} style={{ paddingRight: '40px' }}>
                  <NavigationIcon name="albums" />
                  <span>Albums</span>
                </NavLink>
                {!albumsLoading && albums.length > 0 && (
                  <button 
                    className="sidebar-expand-button"
                    onClick={(e) => { e.preventDefault(); setAlbumsExpanded(!albumsExpanded); }}
                    aria-label="Toggle albums"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: albumsExpanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
                      <path d="M6 9l6 6 6-6" />
                    </svg>
                  </button>
                )}
              </div>
              
              <div className={`sidebar-albums-list ${albumsExpanded ? 'expanded' : ''}`}>
                <div className="sidebar-albums-list-inner">
                  {albumsLoading ? (
                    <div className="sidebar-albums-skeleton">
                      <div className="skeleton-item"></div>
                      <div className="skeleton-item"></div>
                      <div className="skeleton-item"></div>
                    </div>
                  ) : (
                    <>
                      {albums.slice(0, 5).map(album => (
                        <NavLink 
                          key={album.id} 
                          to={`/albums/${album.id}`}
                          className="sidebar-album-item"
                          onClick={onClose}
                        >
                          {album.title}
                        </NavLink>
                      ))}
                      {albums.length > 5 && (
                        <NavLink 
                          to="/albums"
                          className="sidebar-view-all"
                          onClick={onClose}
                        >
                          View all
                        </NavLink>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>

            <div className="sidebar-albums-section">
              <div className="sidebar-nav-item-wrapper">
                <NavLink to="/tags" className="sidebar-nav-item" onClick={onClose} style={{ paddingRight: '40px' }}>
                  <NavigationIcon name="tag" />
                  <span>Tags</span>
                  {!tagsLoading && tags.length > 0 && (
                    <span className="sidebar-album-count">{tags.length}</span>
                  )}
                </NavLink>
                {!tagsLoading && tags.length > 0 && (
                  <button 
                    className="sidebar-expand-button"
                    onClick={(e) => { e.preventDefault(); setTagsExpanded(!tagsExpanded); }}
                    aria-label="Toggle tags"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: tagsExpanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>
                      <path d="M6 9l6 6 6-6" />
                    </svg>
                  </button>
                )}
              </div>
              
              <div className={`sidebar-albums-list ${tagsExpanded ? 'expanded' : ''}`}>
                <div className="sidebar-albums-list-inner">
                  {tagsLoading ? (
                    <div className="sidebar-albums-skeleton">
                      <div className="skeleton-item"></div>
                      <div className="skeleton-item"></div>
                      <div className="skeleton-item"></div>
                    </div>
                  ) : (
                    <>
                      {tags.slice(0, 5).map(tag => (
                        <NavLink 
                          key={tag.id} 
                          to={`/tags/${tag.id}`}
                          className="sidebar-album-item"
                          onClick={onClose}
                        >
                          #{tag.name}
                        </NavLink>
                      ))}
                      {tags.length > 5 && (
                        <NavLink 
                          to="/tags"
                          className="sidebar-view-all"
                          onClick={onClose}
                        >
                          View all tags
                        </NavLink>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>

            <NavItem to="/folders" label="Folders" icon="folders" onClick={onClose} />
          </div>

          <div className="sidebar-section-label">Library</div>
          <div className="sidebar-nav-group">
            {libraryItems.map((item) => (
              <NavItem key={item.to} {...item} onClick={onClose} />
            ))}
          </div>

          <div className="sidebar-section-label">Manage</div>
          <div className="sidebar-nav-group">
            {utilityItems.map((item) => (
              <NavItem key={item.to} {...item} onClick={onClose} />
            ))}
          </div>
        </nav>

        <div className="sidebar-storage">
          <div className="storage-icon">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <ellipse cx="12" cy="5" rx="8" ry="3" />
              <path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7" />
            </svg>
          </div>
          <div>
            <div className="storage-title">Local storage</div>
            <div className="storage-caption" style={{ lineHeight: '1.4' }}>
              {currentCount.toLocaleString()} item{currentCount === 1 ? '' : 's'} ({formatBytes(currentSize)})
            </div>
          </div>
        </div>
      </aside>

      <nav className="mobile-bottom-nav" aria-label="Mobile navigation">
        <NavItem to="/" label="Photos" icon="photos" end />
        <NavItem to="/albums" label="Albums" icon="albums" />
        <NavItem to="/folders" label="Folders" icon="folders" />
        <NavItem to="/settings" label="Settings" icon="settings" />
      </nav>
    </>
  );
}
