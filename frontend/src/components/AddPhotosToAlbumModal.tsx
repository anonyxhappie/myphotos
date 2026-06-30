import { useState, useEffect } from 'react';
import type { MediaItemSummary } from '../api/types';
import { fetchTimeline, addMediaToAlbum, fetchAlbumMedia } from '../api/client';
import PhotoCard from './PhotoCard';
import { dialog } from './DialogContainer';

interface AddPhotosToAlbumModalProps {
  albumId: string;
  onClose: () => void;
  onSuccess: () => void;
}

export default function AddPhotosToAlbumModal({ albumId, onClose, onSuccess }: AddPhotosToAlbumModalProps) {
  const [items, setItems] = useState<MediaItemSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  const [albumItemIds, setAlbumItemIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    // Fetch album media first to know what to exclude
    fetchAlbumMedia(albumId).then((res: { items: MediaItemSummary[] }) => {
      const ids = new Set<string>(res.items.map((x: MediaItemSummary) => x.id));
      setAlbumItemIds(ids);
      
      return fetchTimeline({ limit: 500 });
    }).then((res: { items: MediaItemSummary[] }) => {
      setItems(res.items);
      setLoading(false);
    }).catch((err: unknown) => {
      console.error(err);
      setLoading(false);
    });
  }, [albumId]);

  const [lastSelectedIndex, setLastSelectedIndex] = useState<number | null>(null);

  const handleSelectToggle = (item: MediaItemSummary, index: number, event?: React.MouseEvent) => {
    if (albumItemIds.has(item.id)) return; // Prevent selection of items already in the album
    setSelectedIds((prev) => {
      const next = new Set(prev);
      const isSelected = next.has(item.id);

      if (event?.shiftKey && lastSelectedIndex !== null) {
        const start = Math.min(lastSelectedIndex, index);
        const end = Math.max(lastSelectedIndex, index);
        const itemsInRange = items.slice(start, end + 1);
        
        // If the clicked item is already selected, we are deselecting the range
        // Otherwise, we are selecting the range
        if (isSelected) {
          itemsInRange.forEach(x => next.delete(x.id));
        } else {
          itemsInRange.forEach(x => next.add(x.id));
        }
      } else {
        if (isSelected) {
          next.delete(item.id);
        } else {
          next.add(item.id);
        }
      }
      return next;
    });
    setLastSelectedIndex(index);
  };

  const handleAdd = async () => {
    if (selectedIds.size === 0 || submitting) return;
    setSubmitting(true);
    try {
      await addMediaToAlbum(albumId, Array.from(selectedIds));
      onSuccess();
    } catch (e) {
      console.error(e);
      dialog.alert('Failed to add photos to album');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex flex-col bg-[#1a1a1a]" onClick={e => e.stopPropagation()}>
      <div className="p-6 border-b border-white/5 flex justify-between items-center shrink-0">
        <div>
          <h3 className="text-xl font-medium text-white">Add Photos to Album</h3>
          <p className="text-xs text-white/50 mt-1">Select photos from your library to add to this album</p>
        </div>
        <button onClick={onClose} className="text-white/50 hover:text-white transition-colors">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      <div className="p-6 overflow-y-auto flex-1">
        {loading ? (
          <div className="flex justify-center items-center h-full">
            <div className="w-8 h-8 rounded-full border-2 border-white/30 border-t-white animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-20 text-white/40">
            No photos found in your library. Scan a folder first!
          </div>
        ) : (
          <div className="grid gap-[4px]" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))' }}>
            {items.map((item, index) => {
              const inAlbum = albumItemIds.has(item.id);
              return (
                <div 
                  key={item.id} 
                  className={`relative aspect-square rounded-lg overflow-hidden group border border-white/5 ${inAlbum ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}
                >
                  <PhotoCard
                    item={item}
                    selectionMode={true}
                    isSelected={inAlbum || selectedIds.has(item.id)}
                    onSelectToggle={(itm, e) => !inAlbum && handleSelectToggle(itm, index, e)}
                    onClick={() => !inAlbum && handleSelectToggle(item, index)}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="p-6 border-t border-white/5 flex justify-between items-center bg-black/10 shrink-0">
        <span className="text-sm font-medium text-white/70">{selectedIds.size} selected</span>
        <div className="flex gap-3">
          <button onClick={onClose} className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/15 text-white font-medium transition-colors text-sm">
            Cancel
          </button>
          <button 
            onClick={handleAdd}
            disabled={selectedIds.size === 0 || submitting}
            className="px-5 py-2 rounded-lg bg-[var(--color-accent)] hover:bg-opacity-95 text-white font-semibold transition-opacity text-sm disabled:opacity-50"
          >
            {submitting ? 'Adding...' : 'Add to Album'}
          </button>
        </div>
      </div>
    </div>
  );
}
