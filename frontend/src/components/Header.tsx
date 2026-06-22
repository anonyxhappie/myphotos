import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { triggerMLPipeline } from '../api/client';

interface HeaderProps {
  onMenuClick: () => void;
  onScanClick: () => void;
  onSearch: (query: string) => void;
  onScanStarted?: (taskId: string, path: string, mode: 'scan' | 'takeout') => void;
  searchQuery?: string;
}

function BrandMark() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
      <circle cx="14" cy="7" r="6" fill="#ea4335" />
      <circle cx="21" cy="14" r="6" fill="#fbbc04" />
      <circle cx="14" cy="21" r="6" fill="#34a853" />
      <circle cx="7" cy="14" r="6" fill="#4285f4" />
      <circle cx="14" cy="14" r="3.25" fill="var(--color-bg-primary)" />
    </svg>
  );
}

export default function Header({ onMenuClick, onScanClick, onSearch, onScanStarted, searchQuery = '' }: HeaderProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const [inputValue, setInputValue] = useState('');
  const [isIndexing, setIsIndexing] = useState(false);

  useEffect(() => {
    setInputValue(searchQuery);
  }, [searchQuery]);

  const submitSearch = () => {
    onSearch(inputValue.trim());
  };

  const handleStartML = async () => {
    setIsIndexing(true);
    try {
      const res = await triggerMLPipeline();
      if (res.task_id && onScanStarted) {
        onScanStarted(res.task_id, 'AI Media Analysis', 'scan');
      }
    } catch (error) {
      console.error(error);
    } finally {
      setTimeout(() => setIsIndexing(false), 1200);
    }
  };

  const clearSearch = () => {
    setInputValue('');
    onSearch('');
  };

  return (
    <header id="app-header" className="app-header">
      <div className="header-leading">
        <button
          type="button"
          className="icon-button mobile-menu-button"
          onClick={onMenuClick}
          aria-label="Open navigation"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="4" y1="7" x2="20" y2="7" />
            <line x1="4" y1="12" x2="20" y2="12" />
            <line x1="4" y1="17" x2="20" y2="17" />
          </svg>
        </button>

        <div className="mobile-brand" aria-label="MyPhotos">
          <BrandMark />
          <span>MyPhotos</span>
        </div>
      </div>

      <form
        className={`header-search ${location.pathname === '/settings' ? 'invisible' : ''}`}
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          submitSearch();
        }}
      >
        <button type="submit" className="search-icon-button" aria-label="Search" disabled={location.pathname === '/settings'}>
          <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="7" />
            <line x1="20" y1="20" x2="16.2" y2="16.2" />
          </svg>
        </button>
        <input
          type="search"
          aria-label="Search photos"
          placeholder="Search your photos"
          value={inputValue}
          onChange={(event) => setInputValue(event.target.value)}
          disabled={location.pathname === '/settings'}
        />
        {inputValue && location.pathname !== '/settings' && (
          <button type="button" className="search-clear-button" onClick={clearSearch} aria-label="Clear search">
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        )}
      </form>

      <div className="header-actions">
        {location.pathname !== '/settings' && (
          <>
            <button
              type="button"
              className={`icon-button header-desktop-action ${isIndexing ? 'is-busy' : ''}`}
              title="Refresh smart search index"
              aria-label="Refresh smart search index"
              onClick={handleStartML}
              disabled={isIndexing}
            >
              <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M12 3a9 9 0 1 0 8.5 6" />
                <polyline points="20 3 20 9 14 9" />
                <path d="M9.5 9.5 12 7l2.5 2.5L12 12z" />
              </svg>
            </button>

            <button type="button" className="add-photos-button" onClick={onScanClick} aria-label="Add photos">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              <span>Add photos</span>
            </button>
            
            <button
              type="button"
              className="icon-button header-desktop-action"
              title="Settings"
              aria-label="Open settings"
              onClick={() => navigate('/settings')}
            >
              <svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.85l.05.05-2.9 2.9-.05-.05A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 1.55V21h-4v-.05A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.85.34l-.05.05-2.9-2.9.05-.05A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3v-4h.05A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.85L4.2 7.1l2.9-2.9.05.05A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3h4v.05A1.7 1.7 0 0 0 15 4.6a1.7 1.7 0 0 0 1.85-.34l.05-.05 2.9 2.9-.05.05A1.7 1.7 0 0 0 19.4 9a1.7 1.7 0 0 0 1.55 1H21v4h-.05A1.7 1.7 0 0 0 19.4 15Z" />
              </svg>
            </button>
          </>
        )}

        <button type="button" className="profile-button" aria-label="Account">
          A
        </button>
      </div>
    </header>
  );
}
