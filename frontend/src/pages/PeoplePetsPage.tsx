import { useEffect, useState } from 'react';
import { fetchPeople, fetchPets, triggerClusterFaces } from '../api/people';
import type { PersonResponse } from '../api/people';
import { getThumbUrl } from '../api/client';
import type { TimelineResponse } from '../api/types';

interface PeoplePetsPageProps {
  onPersonClick: (person: PersonResponse) => void;
  onPetsClick: () => void;
  isAnalyzing?: boolean;
}

export default function PeoplePetsPage({ onPersonClick, onPetsClick, isAnalyzing = false }: PeoplePetsPageProps) {
  const [people, setPeople] = useState<PersonResponse[]>([]);
  const [pets, setPets] = useState<TimelineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [clustering, setClustering] = useState(false);

  const loadData = async () => {
    try {
      const [peopleData, petsData] = await Promise.all([
        fetchPeople(),
        fetchPets()
      ]);
      setPeople(peopleData);
      setPets(petsData);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [isAnalyzing]);

  const handleCluster = async () => {
    setClustering(true);
    try {
      await triggerClusterFaces();
      await loadData();
    } catch (e) {
      console.error("Failed to cluster faces", e);
    } finally {
      setClustering(false);
    }
  };

  if (loading) return <div className="page-loading">Loading...</div>;

  return (
    <div className="page-content">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1 className="settings-page-title" style={{ margin: 0 }}>People & Pets</h1>
          {isAnalyzing && (
             <div style={{ fontSize: '12px', color: 'var(--color-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <div
                    className="w-3 h-3 rounded-full border-2 border-primary/20 shrink-0"
                    style={{
                      borderTopColor: 'currentColor',
                      animation: 'spin 0.8s linear infinite',
                    }}
                />
                Analyzing media...
             </div>
          )}
        </div>
        <button 
          className="outlined-action-button" 
          onClick={handleCluster} 
          disabled={clustering || isAnalyzing}
          title={isAnalyzing ? "Wait for AI Analysis to complete" : "Group similar faces into people"}
          style={{ padding: '8px 16px', minWidth: '120px', justifyContent: 'center' }}
        >
          {clustering ? 'Clustering...' : 'Find People'}
        </button>
      </div>

      <section style={{ marginBottom: '40px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 500, marginBottom: '16px' }}>People</h2>
        {people.length === 0 ? (
          <div style={{ padding: '24px 0', color: 'var(--color-text-secondary)', fontSize: '14px' }}>
            <p>{isAnalyzing ? "AI is analyzing your media to find people... This may take a while." : "No people found. If you just added photos, make sure AI analysis has finished, then click 'Find People'."}</p>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '20px' }}>
            {people.map(person => (
              <div 
                key={person.id} 
                onClick={() => onPersonClick(person)}
                style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center' }}
              >
                <div style={{ width: '120px', height: '120px', borderRadius: '50%', overflow: 'hidden', background: 'var(--color-bg-tertiary)', marginBottom: '12px' }}>
                  {person.cover_media_id ? (
                    <img 
                      src={getThumbUrl(person.cover_media_id)} 
                      alt={person.name}
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                    />
                  ) : (
                    <div className="album-cover-placeholder">?</div>
                  )}
                </div>
                <span style={{ fontWeight: 500, textAlign: 'center' }}>{person.name}</span>
                <span style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>
                  {person.face_count} photo{person.face_count !== 1 ? 's' : ''}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 style={{ fontSize: '20px', fontWeight: 500, marginBottom: '16px' }}>Pets</h2>
        {(!pets || pets.items.length === 0) ? (
          <div style={{ padding: '24px 0', color: 'var(--color-text-secondary)', fontSize: '14px' }}>
            <p>No pets found yet.</p>
          </div>
        ) : (
          <div 
            onClick={onPetsClick}
            style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', width: '140px', alignItems: 'center' }}
          >
            <div style={{ width: '120px', height: '120px', borderRadius: '50%', overflow: 'hidden', background: 'var(--color-bg-tertiary)', marginBottom: '12px' }}>
              <img 
                src={getThumbUrl(pets.items[0].id)} 
                alt="Pets"
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            </div>
            <span style={{ fontWeight: 500, textAlign: 'center' }}>All Pets</span>
            <span style={{ fontSize: '12px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>
              {pets.items.length} photo{pets.items.length !== 1 ? 's' : ''}
            </span>
          </div>
        )}
      </section>
    </div>
  );
}
