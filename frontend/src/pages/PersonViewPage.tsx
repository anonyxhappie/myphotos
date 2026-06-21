import { useState } from 'react';
import { updatePersonName } from '../api/people';
import type { PersonResponse } from '../api/people';
import { getThumbUrl } from '../api/client';
import type { MediaItemSummary } from '../api/types';
import Timeline from '../components/Timeline';

interface PersonViewPageProps {
  person: PersonResponse;
  onBack: () => void;
  onPersonUpdate: (person: PersonResponse) => void;
  onPhotoClick: (item: MediaItemSummary, list: MediaItemSummary[]) => void;
  onTotalCountChange: (count: number, size: number) => void;
}

export default function PersonViewPage({ person, onBack, onPersonUpdate, onPhotoClick, onTotalCountChange }: PersonViewPageProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [nameInput, setNameInput] = useState(person.name);

  const handleSaveName = async () => {
    if (!nameInput.trim() || nameInput.trim() === person.name) {
      setIsEditing(false);
      return;
    }
    try {
      const updated = await updatePersonName(person.id, nameInput.trim());
      onPersonUpdate(updated);
      setIsEditing(false);
    } catch (e) {
      console.error("Failed to update name", e);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSaveName();
    if (e.key === 'Escape') {
      setNameInput(person.name);
      setIsEditing(false);
    }
  };

  return (
    <div className="page-content" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '24px', gap: '16px', flexShrink: 0 }}>
        <button className="button button-outline" onClick={onBack}>
          ← Back
        </button>
        <div style={{ width: '48px', height: '48px', borderRadius: '50%', overflow: 'hidden', background: 'var(--color-bg-tertiary)' }}>
          {person.cover_media_id && (
            <img 
              src={getThumbUrl(person.cover_media_id)} 
              alt={person.name}
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
          )}
        </div>
        {isEditing ? (
          <div style={{ display: 'flex', gap: '8px' }}>
            <input 
              autoFocus
              className="text-input" 
              value={nameInput} 
              onChange={e => setNameInput(e.target.value)} 
              onKeyDown={handleKeyDown}
            />
            <button className="button" onClick={handleSaveName}>Save</button>
          </div>
        ) : (
          <h1 className="settings-page-title" style={{ margin: 0, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }} onClick={() => setIsEditing(true)}>
            {person.name}
            <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--color-text-secondary)' }}>
              <path d="M12 20h9"></path>
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
            </svg>
          </h1>
        )}
      </div>

      <div style={{ flex: 1, overflow: 'hidden', position: 'relative', margin: '-24px', marginTop: '0', padding: '24px', paddingTop: '0' }}>
        <Timeline 
          personId={person.id}
          searchQuery=""
          onPhotoClick={onPhotoClick}
          onTotalCountChange={onTotalCountChange}
        />
      </div>
    </div>
  );
}
