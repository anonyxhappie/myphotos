import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Timeline from '../components/Timeline';
import type { MediaItemSummary, TagWithCount, ScanStatusResponse } from '../api/types';
import { fetchTags, triggerTagScan } from '../api/client';

interface TagViewPageProps {
  onPhotoClick: (item: MediaItemSummary, list: MediaItemSummary[]) => void;
  onTotalCountChange: (count: number, size: number) => void;
  scanProgress: Record<string, ScanStatusResponse>;
  onScanStarted: (taskId: string, path: string, mode: 'scan' | 'takeout') => void;
}

export default function TagViewPage({ 
  onPhotoClick, 
  onTotalCountChange,
  scanProgress,
  onScanStarted
}: TagViewPageProps) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [tag, setTag] = useState<TagWithCount | null>(null);
  const [timelineKey, setTimelineKey] = useState(0);

  const loadTagDetails = async () => {
    if (!id) return;
    try {
      const tags = await fetchTags();
      const found = tags.find(t => t.id === id);
      if (found) setTag(found);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadTagDetails();
  }, [id, timelineKey]);

  // Reload tag count if scan finishes
  useEffect(() => {
    if (!id) return;
    const taskId = `tag-scan-${id}`;
    const scan = scanProgress[taskId];
    if (scan?.status === 'complete') {
      loadTagDetails();
      setTimelineKey(prev => prev + 1);
    }
  }, [scanProgress, id]);

  if (!id) return null;

  const taskId = `tag-scan-${id}`;
  const activeScan = scanProgress[taskId];
  const isScanning = activeScan?.status === 'running' || activeScan?.status === 'pending';
  const progressPct = isScanning && activeScan.progress && activeScan.progress.total_found > 0
    ? Math.round((activeScan.progress.processed / activeScan.progress.total_found) * 100)
    : 0;

  const handleReanalyze = async () => {
    if (!tag) return;
    try {
      const res = await triggerTagScan(id);
      onScanStarted(res.task_id, `Tag: ${tag.name}`, 'scan');
      alert(`Re-analysis started for "${tag.name}"`);
    } catch (e) {
      console.error(e);
      alert('Failed to start re-analysis');
    }
  };

  return (
    <div className="w-full h-full flex flex-col relative text-white">
      <div className="timeline-toolbar">
        <div className="timeline-heading flex items-center gap-4">
          <button 
            onClick={() => navigate('/tags')}
            className="text-[var(--color-text-secondary)] hover:text-white flex items-center"
            aria-label="Back to tags"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <div>
            <h1 className="text-xl font-semibold">#{tag ? tag.name : 'Tag'}</h1>
            <span className="text-sm text-[var(--color-text-secondary)]">
              {tag ? `${tag.media_count} items found` : ''}
              {isScanning && ` • Scanning: ${progressPct}%`}
            </span>
          </div>
        </div>

        <button
          onClick={handleReanalyze}
          className="outlined-action-button"
          disabled={isScanning}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={isScanning ? 'animate-spin' : ''}>
            <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
          </svg>
          {isScanning ? 'Scanning...' : 'Re-analyze'}
        </button>
      </div>

      {isScanning && (
        <div className="px-7 py-2 bg-indigo-900/20 border-b border-indigo-500/10">
          <div className="flex items-center justify-between text-xs text-indigo-400 mb-1">
            <span>Scanning library for matching photos...</span>
            <span>{progressPct}%</span>
          </div>
          <div className="w-full bg-white/5 h-1 rounded-full overflow-hidden">
            <div className="bg-indigo-400 h-full transition-all duration-300" style={{ width: `${progressPct}%` }} />
          </div>
        </div>
      )}

      <div className="flex-1 overflow-hidden relative">
        <Timeline 
          key={`${id}:${timelineKey}`}
          searchQuery="" 
          tagId={id}
          hideHeader={true}
          onPhotoClick={onPhotoClick} 
          onTotalCountChange={onTotalCountChange} 
        />
      </div>
    </div>
  );
}
