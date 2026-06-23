import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';
import type { MediaItemSummary, ScanStatusResponse } from './api/types';
import { fetchTimeline, fetchScans, pauseScan } from './api/client';
import Header from './components/Header';
import Sidebar from './components/Sidebar';
import Timeline from './components/Timeline';
import Lightbox from './components/Lightbox';
import ScanPanel from './components/ScanPanel';
import EmptyState from './components/EmptyState';
import Settings from './components/Settings';
import Albums from './components/Albums';
import AlbumDetail from './components/AlbumDetail';
import Folders from './components/Folders';
import FolderDetail from './components/FolderDetail';
import LockedFolder from './components/LockedFolder';
import PeoplePetsPage from './pages/PeoplePetsPage';
import PersonViewPage from './pages/PersonViewPage';
import type { PersonResponse } from './api/people';
import TagsPage from './pages/TagsPage';
import TagViewPage from './pages/TagViewPage';

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [totalCount, setTotalCount] = useState(0);
  const [totalSize, setTotalSize] = useState(0);
  const [isLibraryLoading, setIsLibraryLoading] = useState(true);
  const [selectedMediaIndex, setSelectedMediaIndex] = useState<number | null>(null);
  const [activeMediaList, setActiveMediaList] = useState<MediaItemSummary[]>([]);
  const [navDirection, setNavDirection] = useState<-1 | 0 | 1>(0);
  const [showScan, setShowScan] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  const activeSearchQuery = useMemo(() => {
    switch (location.pathname) {
      case '/documents':
        return 'document, receipt, id card, paperwork, text';
      case '/screenshots':
        return 'screenshot, user interface, screen capture';
      case '/memes':
        return 'meme, funny internet meme, comic';
      case '/quotes':
        return 'quote, motivational, typography, text';
      case '/':
        return searchQuery;
      default:
        return '';
    }
  }, [location.pathname, searchQuery]);
  const [timelineKey, setTimelineKey] = useState(0);
  const [galleryRefreshToken, setGalleryRefreshToken] = useState(0);
  const [activePerson, setActivePerson] = useState<PersonResponse | null>(null);

  // Scan progress tracking
  const [activeScans, setActiveScans] = useState<{ taskId: string; path: string; mode?: 'scan' | 'takeout' }[]>([]);
  const [scanProgress, setScanProgress] = useState<Record<string, ScanStatusResponse>>({});
  const [progressUpdatedAt, setProgressUpdatedAt] = useState(() => Date.now() / 1000);
  const lastInsertedByTask = useRef<Record<string, number>>({});
  const galleryRefreshTimer = useRef<number | null>(null);

  const handlePhotoClick = useCallback((item: MediaItemSummary, list: MediaItemSummary[]) => {
    const idx = list.findIndex(x => x.id === item.id);
    setNavDirection(0);
    setSelectedMediaIndex(idx !== -1 ? idx : null);
    setActiveMediaList(list);
  }, []);

  const handleTotalCountChange = useCallback((count: number, size: number) => {
    setTotalCount(count);
    setTotalSize(size);
  }, []);

  const refreshTotalCount = useCallback(async () => {
    try {
      const res = await fetchTimeline({ limit: 1 });
      setTotalCount(res.total_count);
      setTotalSize(res.total_size_bytes);
    } catch (err) {
      console.error('Failed to fetch total count:', err);
    } finally {
      setIsLibraryLoading(false);
    }
  }, []);

  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query);
    navigate('/');
  }, [navigate]);

  // Fetch initial total count on mount
  useEffect(() => {
    let isActive = true;
    fetchTimeline({ limit: 1 })
      .then((response) => {
        if (isActive) {
          setTotalCount(response.total_count);
          setTotalSize(response.total_size_bytes);
        }
      })
      .catch((error) => console.error('Failed to fetch total count:', error))
      .finally(() => {
        if (isActive) setIsLibraryLoading(false);
      });

    return () => {
      isActive = false;
    };
  }, []);

  const handleScanStarted = useCallback((taskId: string, path: string, mode: 'scan' | 'takeout') => {
    setActiveScans((prev) => [...prev, { taskId, path, mode }]);
    setScanProgress((prev) => ({
      ...prev,
      [taskId]: {
        task_id: taskId,
        status: 'pending',
        path,
        mode,
        result: null,
      },
    }));
  }, []);

  const scheduleGalleryRefresh = useCallback(() => {
    if (galleryRefreshTimer.current !== null) return;
    galleryRefreshTimer.current = window.setTimeout(() => {
      galleryRefreshTimer.current = null;
      setGalleryRefreshToken((token) => token + 1);
      void refreshTotalCount();
    }, 2000);
  }, [refreshTotalCount]);

  const applyScanUpdate = useCallback((data: ScanStatusResponse) => {
    if (!data.task_id) return;

    setProgressUpdatedAt(Date.now() / 1000);
    setScanProgress((prev) => ({
      ...prev,
      [data.task_id]: data,
    }));

    const inserted = data.progress?.new_inserted ?? 0;
    const previousInserted = lastInsertedByTask.current[data.task_id] ?? 0;
    if (inserted > previousInserted) {
      lastInsertedByTask.current[data.task_id] = inserted;
      scheduleGalleryRefresh();
    }

    if (data.status === 'complete') {
      setTimelineKey((prevKey) => prevKey + 1);
      void refreshTotalCount();
    }

    if (data.status === 'complete' || data.status === 'error') {
      setActiveScans((prevActive) => prevActive.filter((s) => s.taskId !== data.task_id));
      return;
    }

    if (data.status === 'paused') {
      setActiveScans((prevActive) => prevActive.filter((s) => s.taskId !== data.task_id));
      return;
    }

    if (data.path) {
      setActiveScans((prevActive) => {
        if (prevActive.some((s) => s.taskId === data.task_id)) return prevActive;
        return [
          ...prevActive,
          {
            taskId: data.task_id,
            path: data.path ?? 'directory',
            mode: data.mode ?? 'scan',
          },
        ];
      });
    }
  }, [refreshTotalCount, scheduleGalleryRefresh]);

  const handleScanDeleted = useCallback((taskId: string) => {
    setScanProgress((prev) => {
      const next = { ...prev };
      delete next[taskId];
      return next;
    });
    setActiveScans((prev) => prev.filter((s) => s.taskId !== taskId));
  }, []);

  // Restore persisted scan tasks after reload
  useEffect(() => {
    let isActive = true;

    fetchScans()
      .then((scans) => {
        if (!isActive) return;
        scans.forEach((scan) => {
          applyScanUpdate(scan);
          if (scan.progress?.new_inserted !== undefined) {
            lastInsertedByTask.current[scan.task_id] = scan.progress.new_inserted;
          }
        });
      })
      .catch((error) => console.error('Failed to restore scan tasks:', error));

    return () => {
      isActive = false;
    };
  }, [applyScanUpdate]);

  // Listen to WebSocket progress updates
  useEffect(() => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/api/ws/scan-progress`;
    
    let ws: WebSocket;
    let reconnectTimeout: ReturnType<typeof setTimeout>;
    let isCleanedUp = false;

    const connect = () => {
      ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as ScanStatusResponse;
          applyScanUpdate(data);
        } catch (err) {
          console.error('Failed to parse WebSocket progress message:', err);
        }
      };

      ws.onclose = () => {
        if (!isCleanedUp) {
          reconnectTimeout = setTimeout(connect, 3000);
        }
      };
    };

    connect();

    return () => {
      isCleanedUp = true;
      clearTimeout(reconnectTimeout);
      if (ws) {
        ws.onclose = null; // Prevent reconnect logic from firing
        ws.close();
      }
    };
  }, [applyScanUpdate]);

  const handlePauseScan = useCallback(async (taskId: string) => {
    try {
      const updated = await pauseScan(taskId);
      applyScanUpdate(updated);
    } catch (err) {
      console.error('Failed to pause scan:', err);
      alert(err instanceof Error ? err.message : 'Failed to pause scan');
    }
  }, [applyScanUpdate]);

  const hasActiveScanWork = Object.values(scanProgress).some(
    (scan) => scan.status === 'pending' || scan.status === 'running' || scan.status === 'pausing',
  );


  return (
    <div className="app-shell">
      <Sidebar 
        isOpen={isSidebarOpen} 
        onClose={() => setIsSidebarOpen(false)} 
        currentCount={totalCount}
        currentSize={totalSize}
        onPhotosClick={() => handleSearch('')}
      />

      <div className="app-content">
        <Header
          onMenuClick={() => setIsSidebarOpen(true)}
          onScanClick={() => setShowScan(true)}
          onSearch={handleSearch}
          onScanStarted={handleScanStarted}
          searchQuery={activeSearchQuery}
        />

        <main className="app-main">
          <Routes>
            <Route path="/" element={
              isLibraryLoading ? (
                <div className="library-loading" aria-label="Loading photo library">
                  <div className="loading-spinner" />
                </div>
              ) : totalCount === 0 && !searchQuery && !hasActiveScanWork ? (
                <EmptyState onScanClick={() => setShowScan(true)} />
              ) : (
                <Timeline
                  key={`${timelineKey}:${searchQuery}`}
                  searchQuery={searchQuery}
                  refreshToken={galleryRefreshToken}
                  onPhotoClick={handlePhotoClick}
                  onTotalCountChange={handleTotalCountChange}
                />
              )
            } />
            <Route 
              path="/settings" 
              element={
                <Settings 
                  onScanStarted={handleScanStarted} 
                  activeScans={activeScans} 
                  scanProgress={scanProgress}
                  onScanUpdated={applyScanUpdate}
                  onScanDeleted={handleScanDeleted}
                />
              } 
            />
            <Route path="/albums" element={<Albums />} />
            <Route path="/albums/:id" element={<AlbumDetail onPhotoClick={handlePhotoClick} onTotalCountChange={handleTotalCountChange} />} />
            <Route path="/folders" element={<Folders />} />
            <Route path="/folders/:id" element={<FolderDetail onPhotoClick={handlePhotoClick} onTotalCountChange={handleTotalCountChange} />} />
            <Route path="/locked" element={<LockedFolder onPhotoClick={handlePhotoClick} onTotalCountChange={handleTotalCountChange} />} />
            
            {/* Tags */}
            <Route path="/tags" element={<TagsPage scanProgress={scanProgress} onScanStarted={handleScanStarted} />} />
            <Route path="/tags/:id" element={<TagViewPage onPhotoClick={handlePhotoClick} onTotalCountChange={handleTotalCountChange} scanProgress={scanProgress} onScanStarted={handleScanStarted} />} />
            
            {/* People & Pets */}
            <Route path="/people" element={
              activePerson ? (
                <PersonViewPage 
                  person={activePerson} 
                  onBack={() => setActivePerson(null)}
                  onPersonUpdate={setActivePerson}
                  onPhotoClick={handlePhotoClick}
                  onTotalCountChange={handleTotalCountChange}
                />
              ) : (
                <PeoplePetsPage 
                  onPersonClick={setActivePerson} 
                  onPetsClick={() => navigate('/pets')}
                  isAnalyzing={hasActiveScanWork}
                />
              )
            } />
            <Route path="/pets" element={<Timeline key="pets" title="Pets" searchQuery="" petsOnly={true} onPhotoClick={handlePhotoClick} onTotalCountChange={handleTotalCountChange} />} />

            {/* Smart Collections */}
            <Route path="/favourites" element={<Timeline key="favourites" title="Favourites" searchQuery="" favoritesOnly={true} onPhotoClick={handlePhotoClick} onTotalCountChange={handleTotalCountChange} />} />
            <Route path="/recent" element={<Timeline key="recent" title="Recently added" searchQuery="" sort="ingested_at" onPhotoClick={handlePhotoClick} onTotalCountChange={handleTotalCountChange} />} />
            <Route path="/videos" element={<Timeline key="videos" title="Videos" searchQuery="" videosOnly={true} onPhotoClick={handlePhotoClick} onTotalCountChange={handleTotalCountChange} />} />
            <Route path="/documents" element={<Timeline key="documents" title="Documents" searchQuery="document, receipt, id card, paperwork, text" onPhotoClick={handlePhotoClick} onTotalCountChange={handleTotalCountChange} />} />
            <Route path="/screenshots" element={<Timeline key="screenshots" title="Screenshots" searchQuery="screenshot, user interface, screen capture" onPhotoClick={handlePhotoClick} onTotalCountChange={handleTotalCountChange} />} />
            <Route path="/memes" element={<Timeline key="memes" title="Memes" searchQuery="meme, funny internet meme, comic" onPhotoClick={handlePhotoClick} onTotalCountChange={handleTotalCountChange} />} />
            <Route path="/quotes" element={<Timeline key="quotes" title="Quotes" searchQuery="quote, motivational, typography, text" onPhotoClick={handlePhotoClick} onTotalCountChange={handleTotalCountChange} />} />

            <Route path="*" element={
              <div className="flex flex-col items-center justify-center w-full h-full text-[var(--color-text-secondary)]">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" className="mb-4 text-white/20">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <line x1="9" y1="3" x2="9" y2="21" />
                </svg>
                <h2 className="text-xl font-medium text-[var(--color-text-primary)] mb-2">Coming Soon</h2>
                <p className="text-sm max-w-sm text-center">
                  This feature is currently under development. Check back later for updates!
                </p>
              </div>
            } />
          </Routes>
        </main>
      </div>

      {selectedMediaIndex !== null && activeMediaList.length > 0 && (
        <Lightbox
          mediaId={activeMediaList[selectedMediaIndex].id}
          item={activeMediaList[selectedMediaIndex]}
          previousItem={selectedMediaIndex > 0 ? activeMediaList[selectedMediaIndex - 1] : undefined}
          nextItem={
            selectedMediaIndex < activeMediaList.length - 1
              ? activeMediaList[selectedMediaIndex + 1]
              : undefined
          }
          direction={navDirection}
          onClose={() => setSelectedMediaIndex(null)}
          onPrev={
            selectedMediaIndex > 0
              ? () => {
                  setNavDirection(-1);
                  setSelectedMediaIndex(selectedMediaIndex - 1);
                }
              : undefined
          }
          onNext={
            selectedMediaIndex < activeMediaList.length - 1
              ? () => {
                  setNavDirection(1);
                  setSelectedMediaIndex(selectedMediaIndex + 1);
                }
              : undefined
          }
        />
      )}

      {showScan && (
        <ScanPanel
          onClose={() => setShowScan(false)}
          onScanStarted={handleScanStarted}
        />
      )}

      <div className="scan-notifications">
        {Object.entries(scanProgress)
          .filter(([taskId, data]) => {
            if (data.status === 'paused') return false;
            return (
              activeScans.some((s) => s.taskId === taskId) ||
              data.status === 'complete' ||
              data.status === 'error' ||
              data.status === 'pausing'
            );
          })
          .map(([taskId, data]) => {
          const scanInfo = activeScans.find((s) => s.taskId === taskId) || {
            taskId,
            path: data.path ?? 'directory',
            mode: data.mode ?? 'scan',
          };
          const isTakeout = scanInfo.mode === 'takeout';
          const isRunning = data.status === 'running' || data.status === 'pending' || data.status === 'pausing';
          const isComplete = data.status === 'complete';
          const isError = data.status === 'error';

          const progress = data.progress;
          const total = progress?.total_found || 0;
          const processed = progress?.processed || 0;
          const percent = total > 0 ? Math.round((processed / total) * 100) : 0;
          const currentFile = progress?.current_file;
          const startTime = progress?.start_time;
          const isML = scanInfo.path === 'AI Media Analysis';
          
          const heading = isComplete
            ? (isML ? 'AI Analysis Complete' : isTakeout ? 'Takeout Import Complete' : 'Scan Complete')
            : isError
              ? (isML ? 'AI Analysis Failed' : isTakeout ? 'Takeout Import Failed' : 'Scan Failed')
              : data.status === 'pausing'
                ? (isML ? 'Pausing AI Analysis…' : isTakeout ? 'Pausing Takeout…' : 'Pausing Scan…')
                : (isML ? 'Analyzing Media…' : isTakeout ? 'Importing Takeout…' : 'Scanning Directory…');

          // Calculate ETA
          let etaText = '';
          if (isRunning && startTime && processed > 0 && total > 0) {
            const elapsed = progressUpdatedAt - startTime;
            if (elapsed > 0) {
              const filesPerSec = processed / elapsed;
              if (filesPerSec > 0) {
                const remaining = total - processed;
                const remainingSecs = Math.round(remaining / filesPerSec);
                if (remainingSecs > 60) {
                  const mins = Math.floor(remainingSecs / 60);
                  const secs = remainingSecs % 60;
                  etaText = `~${mins}m ${secs}s remaining`;
                } else {
                  etaText = `~${remainingSecs}s remaining`;
                }
              }
            }
          }

          return (
            <div
              key={taskId}
              className="w-80 p-4 rounded-xl shadow-lg border glass flex flex-col transition-all duration-300"
              style={{
                borderColor: isError
                  ? 'rgba(248,113,113,0.3)'
                  : isComplete
                  ? 'rgba(52,211,153,0.3)'
                  : 'var(--color-border)',
                background: 'rgba(15, 12, 28, 0.85)',
                color: '#fff',
              }}
            >
              <div className="flex justify-between items-start mb-2">
                <div className="min-w-0 flex-1 pr-2">
                  <h4 className="text-sm font-semibold truncate">
                    {heading}
                  </h4>
                  <p className="text-[10px] text-white/50 truncate" title={scanInfo.path}>
                    {scanInfo.path}
                  </p>
                </div>
                {isRunning && (
                  <div
                    className="w-4 h-4 rounded-full border-2 border-white/20 shrink-0"
                    style={{
                      borderTopColor: 'var(--color-primary, #6366f1)',
                      animation: 'spin 0.8s linear infinite',
                    }}
                  />
                )}
              </div>

              {progress && (
                <div className="space-y-2 mt-2">
                  {total > 0 && (
                    <div>
                      <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
                        <div
                          className="h-full transition-all duration-300"
                          style={{
                            width: `${percent}%`,
                            background: isError
                              ? 'var(--color-danger)'
                              : isComplete
                              ? 'var(--color-success)'
                              : 'var(--color-primary, #6366f1)',
                          }}
                        />
                      </div>
                      <div className="flex justify-between text-[10px] text-white/40 mt-1">
                        <span>
                          {percent}% {etaText ? `• ${etaText}` : ''}
                        </span>
                        <span>
                          {processed} / {total} files
                        </span>
                      </div>
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-1 text-[11px] text-white/60 pt-2 border-t border-white/5">
                    {!isML ? (
                      <>
                        <div>
                          New: <span className="font-semibold text-emerald-400">{progress.new_inserted}</span>
                        </div>
                        <div>
                          Dupes: <span className="font-semibold text-amber-400">{progress.duplicates_skipped}</span>
                        </div>
                      </>
                    ) : (
                      <>
                        <div>
                          Faces: <span className="font-semibold text-indigo-400">{progress.faces_found || 0}</span>
                        </div>
                        <div>
                          Labels: <span className="font-semibold text-purple-400">{progress.labels_found || 0}</span>
                        </div>
                      </>
                    )}
                    {progress.errors > 0 && (
                      <div className="col-span-2 text-rose-400">
                        Errors: {progress.errors}
                      </div>
                    )}
                  </div>

                  {currentFile && isRunning && (
                    <div
                      className="text-[9px] text-white/40 truncate mt-1 pt-1.5 border-t border-white/5"
                      title={currentFile}
                    >
                      File: <span className="font-mono text-white/60">{currentFile.split('/').pop()}</span>
                    </div>
                  )}
                </div>
              )}

              {!isRunning && (
                <button
                  type="button"
                  className="mt-3 w-full py-1 text-center text-xs font-semibold rounded bg-white/10 hover:bg-white/20 text-white transition-colors"
                  onClick={() => {
                    setScanProgress((prev) => {
                      const next = { ...prev };
                      delete next[taskId];
                      return next;
                    });
                  }}
                >
                  Dismiss
                </button>
              )}

              {isRunning && (
                <button
                  type="button"
                  className="mt-3 w-full py-1 text-center text-xs font-semibold rounded bg-white/10 hover:bg-white/20 text-white transition-colors"
                  onClick={() => void handlePauseScan(taskId)}
                  disabled={data.status === 'pausing'}
                >
                  {data.status === 'pausing' ? 'Pausing…' : 'Pause'}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
