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
    <div className="timeline-view text-white">
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
          disabled={clustering || isAnalyzing}
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
                  onClick={() => onPersonClick(person)}
                  className="cursor-pointer flex flex-col items-center"
                >
                  <div className="w-[120px] h-[120px] rounded-full overflow-hidden bg-white/5 mb-3">
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
                  <span className="font-medium text-center">{person.name}</span>
                  <span className="text-xs text-white/60 mt-1">
                    {person.face_count} photo{person.face_count !== 1 ? 's' : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="block">
          <h2 className="text-xl font-medium mb-4">Pets</h2>
          {(!pets || pets.items.length === 0) ? (
            <div className="text-sm text-white/60">
              <p>No pets found yet.</p>
            </div>
          ) : (
            <div 
              onClick={onPetsClick}
              className="cursor-pointer flex flex-col items-center w-[140px]"
            >
              <div className="w-[120px] h-[120px] rounded-full overflow-hidden bg-white/5 mb-3">
                <img 
                  src={getThumbUrl(pets.items[0].id)} 
                  alt="Pets"
                  className="w-full h-full object-cover"
                />
              </div>
              <span className="font-medium text-center">All Pets</span>
              <span className="text-xs text-white/60 mt-1">
                {pets.items.length} photo{pets.items.length !== 1 ? 's' : ''}
              </span>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
