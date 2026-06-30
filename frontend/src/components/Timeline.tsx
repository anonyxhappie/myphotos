import { useState, useEffect, useCallback, useRef, useMemo, useLayoutEffect } from 'react';
import { Virtuoso } from 'react-virtuoso';
import type { MediaItemSummary, TimelineMetadataResponse } from '../api/types';
import { fetchTimeline, searchPhotos, bulkDeleteMedia, fetchAlbumMedia, fetchTagMedia, fetchTimelineMetadata, fetchBin, emptyBin } from '../api/client';
import PhotoCard from './PhotoCard';
import AddToAlbumModal from './AddToAlbumModal';

interface TimelineProps {
  title?: string;
  searchQuery: string;
  favoritesOnly?: boolean;
  videosOnly?: boolean;
  lockedOnly?: boolean;
  albumId?: string;
  tagId?: string;
  dirId?: string;
  personId?: string;
  petsOnly?: boolean;
  isBin?: boolean;
  sort?: string;
  refreshToken?: number;
  hideHeader?: boolean;
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
  zoomLevel: number = 4,
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

  const maxItemsPerRow = zoomLevel === 1 ? 18 : zoomLevel === 2 ? 12 : zoomLevel === 3 ? 8 : 6;

  items.forEach((item) => {
    pending.push(item);
    aspectSum += getAspectRatio(item);
    const availableWidth = containerWidth - gap * (pending.length - 1);
    const projectedHeight = availableWidth / aspectSum;

    if (projectedHeight <= targetHeight * 1.18 || pending.length >= maxItemsPerRow) {
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
  zoomLevel: number;
  onSelectToggle: (item: MediaItemSummary, event?: React.MouseEvent) => void;
  onPhotoClick: (item: MediaItemSummary, list: MediaItemSummary[]) => void;
}

function JustifiedPhotoGrid({
  items,
  allItems,
  selectedIds,
  zoomLevel,
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

  const baseHeight = containerWidth < 640 ? 112 : containerWidth < 960 ? 150 : 184;
  const scale = zoomLevel === 3 ? 0.75 : zoomLevel === 2 ? 0.55 : zoomLevel === 1 ? 0.38 : 1.0;
  const targetHeight = baseHeight * scale;
  const gap = (containerWidth < 640 ? 2 : 4) * (zoomLevel === 1 ? 0.5 : 1);
  const rows = useMemo(
    () => buildJustifiedRows(items, containerWidth, targetHeight, gap, zoomLevel),
    [containerWidth, gap, items, targetHeight, zoomLevel],
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
  tagId,
  dirId,
  personId,
  petsOnly = false,
  isBin = false,
  sort = "date_taken",
  refreshToken = 0,
  hideHeader = false,
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
  const virtuosoRef = useRef<any>(null);
  const scrubberContainerRef = useRef<HTMLDivElement>(null);
  const isDraggingRef = useRef(false);
  const [isDragging, setIsDragging] = useState(false);
  const [scrollPercent, setScrollPercent] = useState(0);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [zoomLevel, setZoomLevel] = useState<number>(() => {
    const saved = localStorage.getItem('timeline_zoom');
    if (saved) {
      const val = parseInt(saved, 10);
      if (val >= 1 && val <= 4) return val;
    }
    return 4; // Default to max zoom in
  });

  const changeZoom = useCallback((level: number) => {
    setZoomLevel(level);
    localStorage.setItem('timeline_zoom', String(level));
  }, []);

  const loadMoreTimeoutRef = useRef<number | null>(null);
  const lastFetchTimeRef = useRef(0);
  
  const [timelineMetadata, setTimelineMetadata] = useState<TimelineMetadataResponse | null>(null);

  useEffect(() => {
    if (searchQuery.trim() || albumId || tagId || isBin || personId || petsOnly) return;
    fetchTimelineMetadata({
      favorites_only: favoritesOnly,
      videos_only: videosOnly,
      locked_only: lockedOnly,
      dir_id: dirId,
      sort,
    })
      .then(res => setTimelineMetadata(res))
      .catch(err => console.error('Failed to fetch timeline metadata', err));
  }, [searchQuery, albumId, tagId, isBin, personId, petsOnly, favoritesOnly, videosOnly, lockedOnly, dirId, sort]);

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

  const scrubberMarkers = useMemo(() => {
    if (timelineMetadata && timelineMetadata.total_count > 0) {
      const markers: { label: string; index: number; percent: number; isYear: boolean; dateStr: string }[] = [];
      let cumulative = 0;
      let lastYear = 0;
      
      for (let i = 0; i < timelineMetadata.items.length; i++) {
        const item = timelineMetadata.items[i];
        const percent = cumulative / timelineMetadata.total_count;
        if (item.year !== lastYear) {
          markers.push({ label: String(item.year), index: i, percent, isYear: true, dateStr: `${item.year}` });
          lastYear = item.year;
        } else {
          markers.push({ label: '•', index: i, percent, isYear: false, dateStr: `${item.year}-${item.month}` });
        }
        cumulative += item.count;
      }
      return markers;
    }
    
    const markers: { label: string; index: number; percent: number; isYear: boolean; dateStr: string }[] = [];
    let lastYear = '';
    let lastMonth = '';
    
    dayGroups.forEach((group, index) => {
      const yearMatch = group.dateStr.match(/\b(20\d{2}|19\d{2})\b/);
      const year = yearMatch ? yearMatch[1] : '';
      const percent = dayGroups.length > 1 ? index / (dayGroups.length - 1) : 0;
      
      if (year && year !== lastYear) {
        markers.push({ label: year, index, percent, isYear: true, dateStr: group.dateStr });
        lastYear = year;
        lastMonth = '';
      } else {
        const monthMatch = group.dateStr.match(/^[a-zA-Z]{3,}/);
        const month = monthMatch ? monthMatch[0] : '';
        if (month && month !== lastMonth) {
          markers.push({ label: '•', index, percent, isYear: false, dateStr: group.dateStr });
          lastMonth = month;
        }
      }
    });
    return markers;
  }, [dayGroups, grouping, timelineMetadata]);


  const loadMore = useCallback(async (overrideCursor?: string, replace = false) => {
    if (isLoading || (!hasMore && !overrideCursor)) return;
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
      } else if (isBin) {
        res = await fetchBin();
        setHasMore(false);
      } else if (searchQuery) {
        res = await searchPhotos(searchQuery);
        setHasMore(false);
      } else if (albumId) {
        res = await fetchAlbumMedia(albumId);
        setHasMore(false);
      } else if (tagId) {
        res = await fetchTagMedia(tagId);
        setHasMore(false);
      } else {
        res = await fetchTimeline({
          cursor: overrideCursor !== undefined ? (overrideCursor || undefined) : (nextCursor || undefined),
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

      const newItems = res.items || [];
      if (overrideCursor !== undefined && replace) {
        setItems(newItems);
      } else {
        setItems((prev) => {
          const appendedItems = (searchQuery || personId || petsOnly || albumId || tagId || isBin) ? newItems : [...prev, ...newItems];
          // Deduplicate by ID
          return Array.from(new Map(appendedItems.map((item: MediaItemSummary) => [item.id, item])).values()) as MediaItemSummary[];
        });
      }


    } catch (err) {
      console.error('Failed to fetch timeline:', err);
    } finally {
      setIsLoading(false);
      setHasLoadedOnce(true);
    }
  }, [
    albumId,
    tagId,
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
    personId,
    petsOnly,
    isBin
  ]);

  const scrubToY = useCallback((y: number) => {
    if (timelineMetadata && timelineMetadata.total_count > 0 && scrubberContainerRef.current) {
      const { top, height } = scrubberContainerRef.current.getBoundingClientRect();
      const percent = Math.min(1, Math.max(0, (y - top) / height));
      setScrollPercent(percent); // immediate visual feedback
      const targetGlobalIndex = Math.floor(percent * timelineMetadata.total_count);
      
      let cumulative = 0;
      let targetItem = timelineMetadata.items[0];
      for (const item of timelineMetadata.items) {
        cumulative += item.count;
        if (cumulative >= targetGlobalIndex) {
          targetItem = item;
          break;
        }
      }
      
      if (targetItem) {
        const nextMonth = targetItem.month === 12 ? 1 : targetItem.month + 1;
        const nextYear = targetItem.month === 12 ? targetItem.year + 1 : targetItem.year;
        const targetCursor = `${nextYear}-${String(nextMonth).padStart(2, '0')}-01T00:00:00Z`;
        
        const now = Date.now();
        if (now - lastFetchTimeRef.current > 150) {
          lastFetchTimeRef.current = now;
          if (loadMoreTimeoutRef.current) window.clearTimeout(loadMoreTimeoutRef.current);
          loadMore(targetCursor, true);
        } else {
          if (loadMoreTimeoutRef.current) window.clearTimeout(loadMoreTimeoutRef.current);
          loadMoreTimeoutRef.current = window.setTimeout(() => {
            lastFetchTimeRef.current = Date.now();
            loadMore(targetCursor, true);
          }, 150);
        }
      }
    } else {
      if (!virtuosoRef.current || dayGroups.length === 0 || !scrubberContainerRef.current) return;
      const { top, height } = scrubberContainerRef.current.getBoundingClientRect();
      const relativeY = Math.max(0, Math.min(y - top, height));
      const targetIndex = Math.floor((relativeY / height) * (dayGroups.length - 1));
      virtuosoRef.current.scrollToIndex({ index: Math.max(0, targetIndex), align: 'start' });
    }
  }, [dayGroups.length, timelineMetadata, loadMore]);

  const handleScrubberPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const container = scrubberContainerRef.current;
    if (container) {
      container.setPointerCapture(e.pointerId);
    }
    isDraggingRef.current = true;
    setIsDragging(true);
    scrubToY(e.clientY);
  }, [scrubToY]);

  const handlePointerMove = useCallback((e: PointerEvent) => {
    if (isDraggingRef.current) {
      e.preventDefault();
      scrubToY(e.clientY);
    }
  }, [scrubToY]);

  const handlePointerUp = useCallback((e: PointerEvent) => {
    if (isDraggingRef.current) {
      isDraggingRef.current = false;
      setIsDragging(false);
      const container = scrubberContainerRef.current;
      if (container && container.hasPointerCapture(e.pointerId)) {
        container.releasePointerCapture(e.pointerId);
      }
    }
  }, []);

  useEffect(() => {
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, [handlePointerMove, handlePointerUp]);

  const loadedChunkGlobalOffset = useMemo(() => {
    if (!timelineMetadata || items.length === 0) return 0;
    const firstItem = items[0];
    const date = new Date(firstItem.date_taken || firstItem.date_modified || Date.now());
    const year = date.getFullYear();
    const month = date.getMonth() + 1;

    let cumulative = 0;
    for (const metaItem of timelineMetadata.items) {
      if (sort === 'date_taken_asc' || sort === 'date_asc' || sort === 'name_asc') {
        if (metaItem.year < year || (metaItem.year === year && metaItem.month < month)) {
          cumulative += metaItem.count;
        } else break;
      } else {
        if (metaItem.year > year || (metaItem.year === year && metaItem.month > month)) {
          cumulative += metaItem.count;
        } else break;
      }
    }
    return cumulative;
  }, [items, timelineMetadata, sort]);

  const handleScroll = useCallback((e: React.UIEvent<HTMLElement>) => {
    if (isDraggingRef.current || !timelineMetadata || timelineMetadata.total_count === 0) return;
    
    const scrollTop = e.currentTarget.scrollTop;
    const windowWidth = typeof window !== 'undefined' ? window.innerWidth : 1000;
    const zoomScale = zoomLevel === 3 ? 0.75 : zoomLevel === 2 ? 0.55 : zoomLevel === 1 ? 0.38 : 1.0;
    const rowHeight = ((windowWidth < 640 ? 112 : windowWidth < 960 ? 150 : 184) + (windowWidth < 640 ? 2 : 4)) * zoomScale;
    const effectiveRowHeight = rowHeight + 10; 
    const scrolledRows = scrollTop / effectiveRowHeight;
    const itemsPerRow = windowWidth / (rowHeight * 1.5);
    const scrolledItemsLocal = Math.floor(scrolledRows * itemsPerRow);
    
    const currentGlobalIndex = loadedChunkGlobalOffset + scrolledItemsLocal;
    const percent = Math.min(1, Math.max(0, currentGlobalIndex / timelineMetadata.total_count));
    
    setScrollPercent(percent);
  }, [loadedChunkGlobalOffset, timelineMetadata, zoomLevel]);

  const toggleGroupCollapse = useCallback((dateStr: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev);
      if (next.has(dateStr)) next.delete(dateStr);
      else next.add(dateStr);
      return next;
    });
  }, []);

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
    if (searchQuery.trim() || albumId || tagId || !hasLoadedOnce) return;

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
    tagId,
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
    if (isBin) {
      if (!confirm(`Are you sure you want to permanently delete these ${ids.length} item(s)? This will also clean up database records, vectors, and cached thumbnail files.`)) {
        return;
      }
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
    <div className="timeline-view" data-zoom={zoomLevel}>
      {!hideHeader && (
        <div className="timeline-toolbar">
          <div className="timeline-heading">
            <h1>{title || (searchQuery ? 'Search results' : 'Photos')}</h1>
            <div className="flex items-center gap-4">
              <span>
                {resultCount.toLocaleString()} {resultCount === 1 ? 'item' : 'items'}
              </span>
              {dirId && resultCount > 0 && !isBin && (
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
              {isBin && resultCount > 0 && (
                <button 
                  onClick={async () => {
                    if (!confirm('Empty bin permanently?')) return;
                    try { await emptyBin(); setItems([]); onTotalCountChange(0, 0); } catch (e) { console.error(e); }
                  }}
                  className="bg-[var(--color-danger)]/10 text-[var(--color-danger)] hover:bg-[var(--color-danger)] hover:text-white px-3 py-1 rounded-md text-sm font-medium transition-colors border border-[var(--color-danger)]/20"
                >
                  Empty Bin
                </button>
              )}
            </div>
          </div>

          {items.length > 0 && (
            <div className="flex items-center gap-3">
              {/* Zoom Control */}
              <div className="zoom-control" aria-label="Zoom photos">
                <button
                  onClick={() => changeZoom(Math.max(1, zoomLevel - 1))}
                  disabled={zoomLevel === 1}
                  title="Zoom out"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                </button>
                <div className="zoom-indicator">
                  {[1, 2, 3, 4].map((level) => (
                    <span 
                      key={level} 
                      className={`zoom-dot ${zoomLevel === level ? 'is-active' : ''}`}
                    />
                  ))}
                </div>
                <button
                  onClick={() => changeZoom(Math.min(4, zoomLevel + 1))}
                  disabled={zoomLevel === 4}
                  title="Zoom in"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19" />
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                </button>
              </div>

              {/* Grouping Control */}
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
            </div>
          )}
        </div>
      )}

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
          ref={virtuosoRef}
          className="timeline-scroller"
          data={dayGroups}
          overscan={600}
          onScroll={handleScroll}
          itemContent={(_, group) => {
            const isCollapsed = collapsedGroups.has(group.dateStr);
            return (
              <section className={`timeline-date-group ${isCollapsed ? 'is-collapsed' : ''}`}>
                <button 
                  className="timeline-date-label"
                  onClick={() => toggleGroupCollapse(group.dateStr)}
                  aria-expanded={!isCollapsed}
                >
                  <span className="date-label-text">{group.dateStr}</span>
                  <span className="date-label-count">{group.items.length}</span>
                  <svg 
                    className={`collapse-chevron ${isCollapsed ? 'is-collapsed' : ''}`}
                    width="16" 
                    height="16" 
                    viewBox="0 0 24 24" 
                    fill="none" 
                    stroke="currentColor" 
                    strokeWidth="2" 
                    strokeLinecap="round" 
                    strokeLinejoin="round"
                    style={{ marginLeft: 'auto' }}
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </button>
                {!isCollapsed && (
                  <JustifiedPhotoGrid
                    items={group.items}
                    allItems={items}
                    selectedIds={selectedIds}
                    zoomLevel={zoomLevel}
                    onSelectToggle={handleSelectToggle}
                    onPhotoClick={onPhotoClick}
                  />
                )}
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

      {scrubberMarkers.length > 0 && (
        <div 
          className="timeline-scrubber-container" 
          ref={scrubberContainerRef}
          onPointerDown={handleScrubberPointerDown}
        >
          {scrubberMarkers.map((marker, i) => (
            <div 
              key={i} 
              className={`scrubber-marker ${marker.isYear ? 'is-year' : 'is-dot'}`}
              style={{ position: 'absolute', top: `${marker.percent * 100}%`, right: '14px', transform: 'translateY(-50%)' }}
              title={marker.dateStr}
            >
              {marker.label}
            </div>
          ))}
          <div 
            className="timeline-scrubber-thumb" 
            style={{ 
              top: `${scrollPercent * 100}%`,
              transition: isDragging ? 'none' : 'top 0.25s ease-out, width 0.15s ease, background-color 0.15s ease',
            }} 
          />
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
