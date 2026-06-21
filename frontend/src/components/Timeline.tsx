import { useState, useEffect, useCallback, useRef, useMemo, useLayoutEffect } from 'react';
import { Virtuoso } from 'react-virtuoso';
import type { MediaItemSummary } from '../api/types';
import { fetchTimeline, searchPhotos, bulkDeleteMedia, fetchAlbumMedia } from '../api/client';
import PhotoCard from './PhotoCard';
import AddToAlbumModal from './AddToAlbumModal';

interface TimelineProps {
  title?: string;
  searchQuery: string;
  favoritesOnly?: boolean;
  videosOnly?: boolean;
  lockedOnly?: boolean;
  albumId?: string;
  dirId?: string;
  personId?: string;
  petsOnly?: boolean;
  sort?: string;
  refreshToken?: number;
  onPhotoClick: (item: MediaItemSummary, list: MediaItemSummary[]) => void;
  onTotalCountChange: (count: number, size: number) => void;
}

// ─── Date grouping ──────────────────────────────────────────────

type GroupingMode = 'day' | 'week' | 'month' | 'year';

function formatDateGroup(dateStr: string | null, mode: GroupingMode): string {
  if (!dateStr) return 'UNKNOWN DATE';
  try {
    let d = new Date(dateStr);
    // Fix for python datetime lacking Z causing local time parse issues or invalid dates
    if (isNaN(d.getTime()) && !dateStr.endsWith('Z')) {
       d = new Date(dateStr + 'Z');
    }
    if (isNaN(d.getTime())) return 'UNKNOWN DATE';
    
    if (mode === 'day') {
      return d.toLocaleDateString('en-US', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
    } else if (mode === 'week') {
      const startOfWeek = new Date(d);
      startOfWeek.setDate(d.getDate() - d.getDay());
      return `Week of ${startOfWeek.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`;
    } else if (mode === 'month') {
      return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
    } else if (mode === 'year') {
      return d.getFullYear().toString();
    }
  } catch {
    return 'UNKNOWN DATE';
  }
  return 'UNKNOWN DATE';
}

interface DayGroup {
  dateStr: string;
  items: MediaItemSummary[];
}

function buildDayGroups(items: MediaItemSummary[], mode: GroupingMode): DayGroup[] {
  const groups: DayGroup[] = [];
  let currentGroup: DayGroup | null = null;
  for (const item of items) {
    const dateStr = formatDateGroup(item.date_taken || item.date_modified, mode);
    if (!currentGroup || currentGroup.dateStr !== dateStr) {
      currentGroup = { dateStr, items: [] };
      groups.push(currentGroup);
    }
    currentGroup.items.push(item);
  }
  return groups;
}

interface JustifiedRow {
  items: Array<{ item: MediaItemSummary; width: number }>;
  height: number;
  isLast: boolean;
}

function getAspectRatio(item: MediaItemSummary): number {
  if (!item.width || !item.height) return 1;
  return Math.min(2.6, Math.max(0.55, item.width / item.height));
}

function buildJustifiedRows(
  items: MediaItemSummary[],
  containerWidth: number,
  targetHeight: number,
  gap: number,
): JustifiedRow[] {
  if (!containerWidth || items.length === 0) return [];

  const rows: JustifiedRow[] = [];
  let pending: MediaItemSummary[] = [];
  let aspectSum = 0;

  const commitRow = (isLast: boolean) => {
    if (pending.length === 0) return;
    const availableWidth = containerWidth - gap * (pending.length - 1);
    const naturalHeight = availableWidth / aspectSum;
    const height = isLast
      ? Math.min(targetHeight, naturalHeight)
      : Math.max(targetHeight * 0.72, Math.min(targetHeight * 1.25, naturalHeight));

    rows.push({
      height,
      isLast,
      items: pending.map((item) => ({ item, width: getAspectRatio(item) * height })),
    });
    pending = [];
    aspectSum = 0;
  };

  items.forEach((item) => {
    pending.push(item);
    aspectSum += getAspectRatio(item);
    const availableWidth = containerWidth - gap * (pending.length - 1);
    const projectedHeight = availableWidth / aspectSum;

    if (projectedHeight <= targetHeight * 1.18 || pending.length >= 6) {
      commitRow(false);
    }
  });

  commitRow(true);
  return rows;
}

interface JustifiedPhotoGridProps {
  items: MediaItemSummary[];
  allItems: MediaItemSummary[];
  selectedIds: Set<string>;
  onSelectToggle: (item: MediaItemSummary, event?: React.MouseEvent) => void;
  onPhotoClick: (item: MediaItemSummary, list: MediaItemSummary[]) => void;
}

function JustifiedPhotoGrid({
  items,
  allItems,
  selectedIds,
  onSelectToggle,
  onPhotoClick,
}: JustifiedPhotoGridProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  useLayoutEffect(() => {
    const element = containerRef.current;
    if (!element) return;

    const updateWidth = () => setContainerWidth(element.clientWidth);
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const targetHeight = containerWidth < 640 ? 112 : containerWidth < 960 ? 150 : 184;
  const gap = containerWidth < 640 ? 2 : 4;
  const rows = useMemo(
    () => buildJustifiedRows(items, containerWidth, targetHeight, gap),
    [containerWidth, gap, items, targetHeight],
  );

  const renderCard = (item: MediaItemSummary) => (
    <PhotoCard
      key={item.id}
      item={item}
      selectionMode={selectedIds.size > 0}
      isSelected={selectedIds.has(item.id)}
      onSelectToggle={onSelectToggle}
      onClick={(clickedItem) => {
        if (selectedIds.size > 0) {
          onSelectToggle(clickedItem);
        } else {
          onPhotoClick(clickedItem, allItems);
        }
      }}
    />
  );

  return (
    <div ref={containerRef} className="justified-photo-grid">
      {containerWidth === 0 ? (
        <div className="photo-grid-fallback">{items.map(renderCard)}</div>
      ) : (
        rows.map((row, rowIndex) => (
          <div
            key={`${items[0]?.id}-${rowIndex}`}
            className="justified-photo-row"
            style={{ height: `${row.height}px`, gap: `${gap}px` }}
          >
            {row.items.map(({ item, width }) => (
              <div
                key={item.id}
                className="justified-photo-cell"
                style={{
                  width: `${width}px`,
                  flexGrow: row.isLast ? 0 : getAspectRatio(item),
                }}
              >
                {renderCard(item)}
              </div>
            ))}
          </div>
        ))
      )}
    </div>
  );
}

// ─── Timeline Component ────────────────────────────────────────

export default function Timeline({ 
  title,
  searchQuery, 
  favoritesOnly = false,
  videosOnly = false,
  lockedOnly = false,
  albumId,
  dirId,
  personId,
  petsOnly = false,
  sort = "date_taken",
  refreshToken = 0,
  onPhotoClick, 
  onTotalCountChange 
}: TimelineProps) {
  const [items, setItems] = useState<MediaItemSummary[]>([]);
  const [resultCount, setResultCount] = useState(0);
  const [resultSize, setResultSize] = useState(0);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);
  const [grouping, setGrouping] = useState<GroupingMode>('day');
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showAddToAlbum, setShowAddToAlbum] = useState(false);
  const initialLoadDone = useRef(false);
  const lastRefreshToken = useRef(0);

  const [lastSelectedIndex, setLastSelectedIndex] = useState<number | null>(null);

  const handleSelectToggle = useCallback((item: MediaItemSummary, event?: React.MouseEvent) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      const isSelected = next.has(item.id);

      // Find the index of the clicked item in the current loaded items list
      const clickedIndex = items.findIndex(x => x.id === item.id);

      if (event?.shiftKey && lastSelectedIndex !== null && clickedIndex !== -1) {
        const start = Math.min(lastSelectedIndex, clickedIndex);
        const end = Math.max(lastSelectedIndex, clickedIndex);
        const rangeItems = items.slice(start, end + 1);

        if (isSelected) {
          rangeItems.forEach(x => next.delete(x.id));
        } else {
          rangeItems.forEach(x => next.add(x.id));
        }
      } else {
        if (isSelected) {
          next.delete(item.id);
        } else {
          next.add(item.id);
        }
      }

      if (clickedIndex !== -1) {
        setLastSelectedIndex(clickedIndex);
      }
      return next;
    });
  }, [items, lastSelectedIndex]);

  const dayGroups = useMemo(() => buildDayGroups(items, grouping), [items, grouping]);

  const loadMore = useCallback(async () => {
    if (isLoading || !hasMore) return;
    setIsLoading(true);

    try {
      let res;
      if (personId) {
        // Use person media endpoint
        const response = await fetch(`/api/people/${personId}/media`);
        res = await response.json();
      } else if (petsOnly) {
        // Use pets endpoint
        const response = await fetch(`/api/pets`);
        res = await response.json();
      } else if (searchQuery) {
        res = await searchPhotos(searchQuery);
        setHasMore(false);
      } else if (albumId) {
        res = await fetchAlbumMedia(albumId);
        setHasMore(false);
      } else {
        res = await fetchTimeline({
          cursor: nextCursor || undefined,
          limit: 100,
          favorites_only: favoritesOnly,
          videos_only: videosOnly,
          locked_only: lockedOnly,
          dir_id: dirId,
          sort
        });
      }
      setNextCursor(res.next_cursor);
      if (!res.next_cursor) setHasMore(false);
      
      if (!searchQuery.trim()) {
        onTotalCountChange(res.total_count, res.total_size_bytes);
      }
      setResultCount(res.total_count);
      setResultSize(res.total_size_bytes || 0);

      setItems((prev) => {
        const newItems = res.items || [];
        const appendedItems = (searchQuery || personId || petsOnly || albumId) ? newItems : [...prev, ...newItems];
        // Deduplicate by ID
        return Array.from(new Map(appendedItems.map((item: MediaItemSummary) => [item.id, item])).values()) as MediaItemSummary[];
      });

    } catch (err) {
      console.error('Failed to fetch timeline:', err);
    } finally {
      setIsLoading(false);
      setHasLoadedOnce(true);
    }
  }, [
    albumId,
    dirId,
    favoritesOnly,
    hasMore,
    isLoading,
    lockedOnly,
    nextCursor,
    onTotalCountChange,
    searchQuery,
    sort,
    videosOnly,
  ]);

  useEffect(() => {
    if (initialLoadDone.current) return;
    const timeoutId = window.setTimeout(() => {
      if (initialLoadDone.current) return;
      initialLoadDone.current = true;
      void loadMore();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadMore]);

  useEffect(() => {
    if (!refreshToken || refreshToken === lastRefreshToken.current) return;
    if (searchQuery.trim() || albumId || !hasLoadedOnce) return;

    lastRefreshToken.current = refreshToken;

    void (async () => {
      try {
        const res = await fetchTimeline({
          limit: 200,
          favorites_only: favoritesOnly,
          videos_only: videosOnly,
          locked_only: lockedOnly,
          dir_id: dirId,
          sort,
        });
        onTotalCountChange(res.total_count, res.total_size_bytes);
        setResultCount(res.total_count);
        setItems((prev) => {
          const existingIds = new Set(prev.map((item) => item.id));
          const newItems = res.items.filter((item) => !existingIds.has(item.id));
          if (newItems.length === 0) return prev;
          return [...newItems, ...prev];
        });
      } catch (err) {
        console.error('Failed to refresh timeline during scan:', err);
      }
    })();
  }, [
    albumId,
    dirId,
    favoritesOnly,
    hasLoadedOnce,
    lockedOnly,
    onTotalCountChange,
    refreshToken,
    searchQuery,
    sort,
    videosOnly,
  ]);

  const handleDeleteSelected = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    if (!confirm(`Are you sure you want to permanently delete these ${ids.length} item(s)? This will also clean up database records, vectors, and cached thumbnail files.`)) {
      return;
    }
    try {
      await bulkDeleteMedia(ids);
      setItems((prev) => prev.filter((item) => !selectedIds.has(item.id)));
      onTotalCountChange(items.length - ids.length, resultSize);
      setSelectedIds(new Set());
    } catch (e) {
      console.error(e);
      alert('Failed to delete selected media');
    }
  };

  return (
    <div className="timeline-view">
      <div className="timeline-toolbar">
        <div className="timeline-heading">
          <h1>{title || (searchQuery ? 'Search results' : 'Photos')}</h1>
          <div className="flex items-center gap-4">
            <span>
              {resultCount.toLocaleString()} {resultCount === 1 ? 'item' : 'items'}
            </span>
            {dirId && resultCount > 0 && (
              <button 
                onClick={() => {
                  setSelectedIds(new Set()); // ensure no selected ids when passing dirId
                  setShowAddToAlbum(true);
                }}
                className="bg-[var(--color-accent)]/10 text-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-white px-3 py-1 rounded-md text-sm font-medium transition-colors border border-[var(--color-accent)]/20"
              >
                Add all to Album
              </button>
            )}
          </div>
        </div>

        {items.length > 0 && (
          <div className="grouping-control" aria-label="Group photos by date range">
          {(['day', 'week', 'month', 'year'] as GroupingMode[]).map(mode => (
            <button
              key={mode}
              onClick={() => setGrouping(mode)}
              className={grouping === mode ? 'is-active' : ''}
              aria-pressed={grouping === mode}
            >
              {mode}
            </button>
          ))}
          </div>
        )}
      </div>

      {hasLoadedOnce && items.length === 0 ? (
        <div className="timeline-empty-state">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
            <rect x="3" y="3" width="18" height="18" rx="3" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <path d="m4 17 4.5-4.5 3.5 3 3-3 5 5" />
          </svg>
          <p>No photos found</p>
        </div>
      ) : (
        <Virtuoso
          className="timeline-scroller"
          data={dayGroups}
          overscan={600}
          itemContent={(_, group) => {
            return (
              <section className="timeline-date-group">
                <div className="timeline-date-label">
                  {group.dateStr}
                </div>
                <JustifiedPhotoGrid
                  items={group.items}
                  allItems={items}
                  selectedIds={selectedIds}
                  onSelectToggle={handleSelectToggle}
                  onPhotoClick={onPhotoClick}
                />
              </section>
            );
          }}
          endReached={() => {
            if (hasMore && !isLoading) {
              loadMore();
            }
          }}
        />
      )}

      {/* Loading indicator */}
      {isLoading && (
        <div className="timeline-loading">
          <div className="flex gap-1.5">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="w-2 h-2 rounded-full"
                style={{
                  background: 'var(--color-accent)',
                  animation: `pulse 1.4s ease-in-out ${i * 0.2}s infinite`,
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Floating Action Bar */}
      {selectedIds.size > 0 && (
        <div className="selection-action-bar">
          <span className="text-sm font-medium text-white">{selectedIds.size} selected</span>
          <div className="w-px h-4 bg-white/20" />
          <button 
            onClick={() => setShowAddToAlbum(true)}
            className="text-sm font-medium hover:text-[var(--color-accent)] transition-colors"
          >
            Add to Album
          </button>
          <div className="w-px h-4 bg-white/20" />
          <button 
            onClick={handleDeleteSelected}
            className="text-sm font-medium text-[var(--color-danger)] hover:text-red-400 transition-colors"
          >
            Delete
          </button>
          <div className="w-px h-4 bg-white/20" />
          <button 
            onClick={() => setSelectedIds(new Set())}
            className="text-sm font-medium text-[var(--color-text-secondary)] hover:text-white transition-colors p-1"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      )}

      {/* Add to Album Modal */}
      {showAddToAlbum && (
        <AddToAlbumModal 
          selectedIds={Array.from(selectedIds)} 
          dirId={dirId && selectedIds.size === 0 ? dirId : undefined}
          onClose={() => setShowAddToAlbum(false)}
          onSuccess={() => {
            setShowAddToAlbum(false);
            setSelectedIds(new Set());
          }}
        />
      )}
    </div>
  );
}
