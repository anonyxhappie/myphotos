import { useEffect, useState } from 'react';
import { fetchPeople, fetchPets, triggerClusterFaces, bulkDeletePeoplePets } from '../api/people';
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

  const [selectedPeopleIds, setSelectedPeopleIds] = useState<Set<string>>(new Set());
  const [selectedPetsSelected, setSelectedPetsSelected] = useState<boolean>(false);

  const isSelectionMode = selectedPeopleIds.size > 0 || selectedPetsSelected;

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

  const handleTogglePerson = (id: string) => {
    setSelectedPeopleIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleTogglePets = () => {
    setSelectedPetsSelected(prev => !prev);
  };

  const handleDeleteSelected = async () => {
    const peopleCount = selectedPeopleIds.size;
    const hasPets = selectedPetsSelected;
    let message = "";
    if (peopleCount > 0 && hasPets) {
      message = `Are you sure you want to delete ${peopleCount} selected people and the pets category?`;
    } else if (peopleCount > 0) {
      message = `Are you sure you want to delete ${peopleCount} selected people?`;
    } else if (hasPets) {
      message = `Are you sure you want to delete the pets category?`;
    }

    if (!confirm(message)) return;

    try {
      await bulkDeletePeoplePets(Array.from(selectedPeopleIds), hasPets);
      setSelectedPeopleIds(new Set());
      setSelectedPetsSelected(false);
      await loadData();
    } catch (e) {
      console.error(e);
      alert('Failed to delete selected items');
    }
  };

  if (loading) {
    return (
      <div className="timeline-view text-white">
        <div className="timeline-toolbar">
          <div className="timeline-heading">
            <h1>People & Pets</h1>
          </div>
        </div>
        <div className="timeline-scroller flex items-center justify-center">
          <div className="loading-spinner" />
        </div>
      </div>
    );
  }

  return (
    <div className="timeline-view text-white relative">
      <div className="timeline-toolbar">
        <div className="timeline-heading flex items-center gap-4">
          <h1>People & Pets</h1>
          {isAnalyzing && (
             <div className="text-xs text-indigo-400 flex items-center gap-2">
                <div className="w-3 h-3 rounded-full border-2 border-indigo-400/20 border-t-indigo-400 animate-spin shrink-0" />
                Analyzing media...
             </div>
          )}
        </div>
        <button 
          className="outlined-action-button" 
          onClick={handleCluster} 
          disabled={clustering || isAnalyzing || isSelectionMode}
          title={isAnalyzing ? "Wait for AI Analysis to complete" : "Group similar faces into people"}
        >
          {clustering ? 'Clustering...' : 'Find People'}
        </button>
      </div>

      <div className="timeline-scroller overflow-y-auto px-7 py-6">
        <section className="mb-8 block">
          <h2 className="text-xl font-medium mb-4">People</h2>
          {people.length === 0 ? (
            <div className="text-sm text-white/60">
              <p>{isAnalyzing ? "AI is analyzing your media to find people... This may take a while." : "No people found. If you just added photos, make sure AI analysis has finished, then click 'Find People'."}</p>
            </div>
          ) : (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-5">
              {people.map(person => (
                <div 
                  key={person.id} 
                  onClick={() => {
                    if (isSelectionMode) {
                      handleTogglePerson(person.id);
                    } else {
                      onPersonClick(person);
                    }
                  }}
                  className="cursor-pointer flex flex-col items-center group relative"
                >
                  <div className="relative w-[120px] h-[120px] rounded-full bg-white/5 mb-3">
                    <div className={`w-full h-full rounded-full overflow-hidden transition-all ${
                      selectedPeopleIds.has(person.id) ? 'ring-4 ring-[var(--color-accent)] ring-offset-2 ring-offset-[var(--color-bg-primary)]' : ''
                    }`}>
                      {person.cover_media_id ? (
                        <img 
                          src={getThumbUrl(person.cover_media_id)} 
                          alt={person.name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-white/20 text-2xl">?</div>
                      )}
                    </div>

                    {/* Selection Checkmark */}
                    <div 
                      className={`absolute top-0 left-0 z-10 w-6 h-6 rounded-full border-2 transition-all flex items-center justify-center cursor-pointer
                        ${selectedPeopleIds.has(person.id) 
                          ? 'bg-[var(--color-accent)] border-[var(--color-accent)] opacity-100' 
                          : 'border-white/50 bg-black/20 opacity-0 group-hover:opacity-100 hover:border-white'}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleTogglePerson(person.id);
                      }}
                    >
                      {selectedPeopleIds.has(person.id) && (
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      )}
                    </div>
                  </div>
                  <span className="font-medium text-center">{person.name}</span>
                  <span className="text-xs text-white/60 mt-1">
                    {person.face_count} photo{person.face_count !== 1 ? 's' : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="block mb-20">
          <h2 className="text-xl font-medium mb-4">Pets</h2>
          {(!pets || pets.items.length === 0) ? (
            <div className="text-sm text-white/60">
              <p>No pets found yet.</p>
            </div>
          ) : (
            <div 
              onClick={() => {
                if (isSelectionMode) {
                  handleTogglePets();
                } else {
                  onPetsClick();
                }
              }}
              className="cursor-pointer flex flex-col items-center w-[140px] group relative"
            >
              <div className="relative w-[120px] h-[120px] rounded-full bg-white/5 mb-3">
                <div className={`w-full h-full rounded-full overflow-hidden transition-all ${
                  selectedPetsSelected ? 'ring-4 ring-[var(--color-accent)] ring-offset-2 ring-offset-[var(--color-bg-primary)]' : ''
                }`}>
                  <img 
                    src={getThumbUrl(pets.items[0].id)} 
                    alt="Pets"
                    className="w-full h-full object-cover"
                  />
                </div>

                {/* Selection Checkmark */}
                <div 
                  className={`absolute top-0 left-0 z-10 w-6 h-6 rounded-full border-2 transition-all flex items-center justify-center cursor-pointer
                    ${selectedPetsSelected 
                      ? 'bg-[var(--color-accent)] border-[var(--color-accent)] opacity-100' 
                      : 'border-white/50 bg-black/20 opacity-0 group-hover:opacity-100 hover:border-white'}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleTogglePets();
                  }}
                >
                  {selectedPetsSelected && (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  )}
                </div>
              </div>
              <span className="font-medium text-center">All Pets</span>
              <span className="text-xs text-white/60 mt-1">
                {pets.items.length} photo{pets.items.length !== 1 ? 's' : ''}
              </span>
            </div>
          )}
        </section>
      </div>

      {isSelectionMode && (
        <div className="selection-action-bar">
          <span className="text-sm font-medium text-white">
            {selectedPeopleIds.size + (selectedPetsSelected ? 1 : 0)} selected
          </span>
          <div className="flex items-center gap-2">
            <button 
              className="action-button text-[var(--color-danger)] hover:bg-[var(--color-danger-hover)] flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-all"
              onClick={handleDeleteSelected}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                <line x1="10" y1="11" x2="10" y2="17" />
                <line x1="14" y1="11" x2="14" y2="17" />
              </svg>
              Delete
            </button>
            <button 
              className="text-button flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-white/80 hover:text-white transition-all"
              onClick={() => {
                setSelectedPeopleIds(new Set());
                setSelectedPetsSelected(false);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
