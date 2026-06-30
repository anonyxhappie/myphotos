import json

with open('/Users/akshay/Desktop/code/myphotos/frontend/src/components/Timeline.tsx', 'r') as f:
    content = f.read()

# Add imports
content = content.replace("import { fetchTimeline, searchPhotos, bulkDeleteMedia, fetchAlbumMedia, fetchTagMedia } from '../api/client';", "import { fetchTimeline, searchPhotos, bulkDeleteMedia, fetchAlbumMedia, fetchTagMedia, fetchTimelineMetadata, fetchBin, emptyBin } from '../api/client';\nimport type { TimelineMetadataResponse } from '../api/types';")

# Add isBin prop
content = content.replace("  tagId?: string;\n  dirId?: string;", "  tagId?: string;\n  dirId?: string;\n  isBin?: boolean;")

# Add metadata state
content = content.replace("  const virtuosoRef = useRef<any>(null);", "  const virtuosoRef = useRef<any>(null);\n  const [timelineMetadata, setTimelineMetadata] = useState<TimelineMetadataResponse | null>(null);")

# Add fetch metadata effect
effect_code = """
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
"""
content = content.replace("  const [activeGroupIndex, setActiveGroupIndex] = useState(0);", "  const [activeGroupIndex, setActiveGroupIndex] = useState(0);\n" + effect_code)

# Add loadMore changes
old_loadmore = """  const loadMore = useCallback(async () => {
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
      } else if (tagId) {
        res = await fetchTagMedia(tagId);
        setHasMore(false);
      } else if (albumId) {
        res = await fetchAlbumMedia(albumId);
        setHasMore(false);
      } else if (searchQuery) {
        res = await searchPhotos(searchQuery);
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
        const appendedItems = (searchQuery || personId || petsOnly || albumId || tagId) ? newItems : [...prev, ...newItems];
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
  ]);"""

new_loadmore = """  const loadMore = useCallback(async (overrideCursor?: string, replace = false) => {
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
      } else if (tagId) {
        res = await fetchTagMedia(tagId);
        setHasMore(false);
      } else if (albumId) {
        res = await fetchAlbumMedia(albumId);
        setHasMore(false);
      } else if (searchQuery) {
        res = await searchPhotos(searchQuery);
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
    isBin,
    personId,
    petsOnly
  ]);"""

content = content.replace(old_loadmore, new_loadmore)

# Update scrubberMarkers
old_scrubber_markers = """  const scrubberMarkers = useMemo(() => {
    const markers: { label: string; index: number; percent: number; isYear: boolean }[] = [];
    let lastYear = '';
    let lastMonth = '';
    
    dayGroups.forEach((group, index) => {
      const yearMatch = group.dateStr.match(/\\b(20\\d{2}|19\\d{2})\\b/);
      const year = yearMatch ? yearMatch[1] : '';
      const percent = dayGroups.length > 1 ? index / (dayGroups.length - 1) : 0;
      
      if (year && year !== lastYear) {
        markers.push({ label: year, index, percent, isYear: true });
        lastYear = year;
        lastMonth = '';
      } else {
        const monthMatch = group.dateStr.match(/^[a-zA-Z]{3,}/);
        const month = monthMatch ? monthMatch[0] : '';
        if (month && month !== lastMonth) {
          markers.push({ label: '•', index, percent, isYear: false });
          lastMonth = month;
        }
      }
    });
    return markers;
  }, [dayGroups]);"""

new_scrubber_markers = """  const scrubberMarkers = useMemo(() => {
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
      const yearMatch = group.dateStr.match(/\\b(20\\d{2}|19\\d{2})\\b/);
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
  }, [dayGroups, grouping, timelineMetadata]);"""

content = content.replace(old_scrubber_markers, new_scrubber_markers)


# Update scrubToY
old_scrubToY = """  const scrubToY = useCallback((y: number) => {
    if (!scrubberContainerRef.current) return;
    const { top, height } = scrubberContainerRef.current.getBoundingClientRect();
    let relativeY = y - top;
    // ...
    // ... wait, I'll just regex replace the whole function because it's easier
"""

content = content.replace("  const scrubToY = useCallback((y: number) => {", "  const scrubToY = useCallback((y: number) => {\n    if (timelineMetadata && timelineMetadata.total_count > 0 && scrubberContainerRef.current) {\n      const { top, height } = scrubberContainerRef.current.getBoundingClientRect();\n      const percent = Math.min(1, Math.max(0, (y - top) / height));\n      const targetGlobalIndex = percent * timelineMetadata.total_count;\n      let cumulative = 0;\n      let targetItem = timelineMetadata.items[0];\n      for (const item of timelineMetadata.items) {\n        cumulative += item.count;\n        if (cumulative >= targetGlobalIndex) {\n          targetItem = item;\n          break;\n        }\n      }\n      const nextMonth = targetItem.month === 12 ? 1 : targetItem.month + 1;\n      const nextYear = targetItem.month === 12 ? targetItem.year + 1 : targetItem.year;\n      const targetCursor = `${nextYear}-${String(nextMonth).padStart(2, '0')}-01T00:00:00Z`;\n      loadMore(targetCursor, true);\n      return;\n    }")

# Update scrubber rendering
content = content.replace("{scrubberMarkers.length > 0 && items.length > 0 && (", "{scrubberMarkers.length > 0 && (")

# Update Empty Bin button
content = content.replace("Add all to Album\\n                </button>\\n              )}", "Add all to Album\n                </button>\n              )}\n              {isBin && resultCount > 0 && (\n                <button \n                  onClick={async () => {\n                    if (!confirm('Empty bin permanently?')) return;\n                    try { await emptyBin(); setItems([]); onTotalCountChange(0, 0); } catch (e) { console.error(e); }\n                  }}\n                  className=\"bg-[var(--color-danger)]/10 text-[var(--color-danger)] hover:bg-[var(--color-danger)] hover:text-white px-3 py-1 rounded-md text-sm font-medium transition-colors border border-[var(--color-danger)]/20\"\n                >\n                  Empty Bin\n                </button>\n              )}")

with open('/Users/akshay/Desktop/code/myphotos/frontend/src/components/Timeline.tsx', 'w') as f:
    f.write(content)
