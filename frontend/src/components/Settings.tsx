import { useState, useEffect, useCallback, useMemo } from 'react';
import type { SyncedDirectory, ScanStatusResponse, AuditLog } from '../api/types';
import {
  fetchSyncedDirectories,
  addSyncedDirectory,
  removeSyncedDirectory,
  selectFolder,
  factoryReset,
  fetchAuditLogs,
  pauseScan,
  resumeScan,
  retryScan,
  resyncAll,
  retrainML,
} from '../api/client';

interface SettingsProps {
  onScanStarted?: (taskId: string, path: string, mode: 'scan' | 'takeout') => void;
  activeScans?: { taskId: string; path: string; mode?: 'scan' | 'takeout' }[];
  scanProgress?: Record<string, ScanStatusResponse>;
  onScanUpdated?: (scan: ScanStatusResponse) => void;
}

export default function Settings({ onScanStarted, scanProgress = {}, onScanUpdated }: SettingsProps) {
  const [directories, setDirectories] = useState<SyncedDirectory[]>([]);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState(false);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(true);

  const loadAuditLogs = useCallback(async () => {
    setLogsLoading(true);
    try {
      const logs = await fetchAuditLogs();
      setAuditLogs(logs);
    } catch (e) {
      console.error('Failed to load audit logs', e);
    } finally {
      setLogsLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadAuditLogs();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadAuditLogs]);

  const handleFactoryReset = async () => {
    const confirm1 = confirm("Are you absolutely sure you want to factory reset the platform? This will clear all database entries and local cache. This action cannot be undone.");
    if (!confirm1) return;
    
    const confirm2 = confirm("Please confirm once more. All synced folders, media items, tags, and albums will be deleted permanently.");
    if (!confirm2) return;
    
    try {
      setResetting(true);
      await factoryReset();
      alert("Factory reset complete. The application will now reload.");
      window.location.reload();
    } catch (e) {
      console.error(e);
      alert("Failed to factory reset: " + (e instanceof Error ? e.message : String(e)));
    } finally {
      setResetting(false);
    }
  };

  const loadDirectories = useCallback(async () => {
    try {
      const dirs = await fetchSyncedDirectories();
      setDirectories(dirs);
    } catch (e) {
      console.error('Failed to load synced directories', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadDirectories();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [loadDirectories]);

  // Reload directories when any scan completes to update counts
  useEffect(() => {
    const hasCompletedScan = Object.values(scanProgress).some(
      (scan) => scan.status === 'complete'
    );
    if (hasCompletedScan) {
      const timeoutId = window.setTimeout(() => {
        void loadDirectories();
      }, 0);
      return () => window.clearTimeout(timeoutId);
    }
  }, [loadDirectories, scanProgress]);

  const backgroundScans = useMemo(
    () =>
      Object.values(scanProgress).filter(
        (scan) =>
          scan.path &&
          (scan.status === 'pending' ||
            scan.status === 'running' ||
            scan.status === 'pausing' ||
            scan.status === 'paused' ||
            scan.status === 'error'),
      ),
    [scanProgress],
  );

  const findScanForPath = useCallback(
    (path: string) =>
      Object.values(scanProgress).find(
        (scan) => scan.path === path && scan.status !== 'complete',
      ),
    [scanProgress],
  );

  const handleScanAction = async (
    taskId: string,
    action: 'pause' | 'resume' | 'retry',
  ) => {
    try {
      const updated =
        action === 'pause'
          ? await pauseScan(taskId)
          : action === 'resume'
            ? await resumeScan(taskId)
            : await retryScan(taskId);
      onScanUpdated?.(updated);
      if (action === 'resume' || action === 'retry') {
        onScanStarted?.(taskId, updated.path ?? 'directory', updated.mode ?? 'scan');
      }
    } catch (e) {
      console.error(`Failed to ${action} scan`, e);
      alert(e instanceof Error ? e.message : `Failed to ${action} scan`);
    }
  };

  const getScanStatusLabel = (status: ScanStatusResponse['status']) => {
    switch (status) {
      case 'pending':
        return 'Queued';
      case 'running':
        return 'Running';
      case 'pausing':
        return 'Pausing…';
      case 'paused':
        return 'Paused';
      case 'error':
        return 'Failed';
      default:
        return status;
    }
  };

  const handleAdd = async () => {
    try {
      const { path } = await selectFolder();
      if (!path) return; // user cancelled

      const result = await addSyncedDirectory(path);
      if (result.task_id && onScanStarted) {
        onScanStarted(result.task_id, path, 'scan');
      }
      await loadDirectories();
      void loadAuditLogs();
    } catch (e) {
      console.error('Failed to add directory', e);
      alert('Failed to add directory');
    }
  };

  const handleRemove = async (id: string) => {
    if (!confirm('Stop syncing this directory and remove all synced media from your library? This cannot be undone.')) return;
    try {
      await removeSyncedDirectory(id);
      await loadDirectories();
      void loadAuditLogs();
    } catch (e) {
      console.error('Failed to remove directory', e);
    }
  };

  const handleResyncAll = async () => {
    if (!confirm('Start a background scan for all monitored directories?')) return;
    try {
      const results = await resyncAll();
      for (const res of results) {
        if (res.task_id && onScanStarted) {
          onScanStarted(res.task_id, res.path || 'directory', 'scan');
        }
      }
      void loadAuditLogs();
    } catch (e) {
      alert('Failed to trigger resync: ' + (e instanceof Error ? e.message : String(e)));
    }
  };

  const handleRetrainML = async () => {
    if (!confirm('This will reset AI embeddings and faces, then re-process all media. This might take a while. Continue?')) return;
    try {
      const res = await retrainML();
      if (res.task_id && onScanStarted) {
        onScanStarted(res.task_id, 'AI Media Analysis', 'scan');
      }
      void loadAuditLogs();
    } catch (e) {
      alert('Failed to trigger retraining: ' + (e instanceof Error ? e.message : String(e)));
    }
  };



  const getLevelBadgeStyles = (level: string) => {
    switch (level) {
      case 'success':
        return 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
      case 'warning':
        return 'bg-amber-500/10 text-amber-400 border border-amber-500/20';
      case 'error':
        return 'bg-rose-500/10 text-rose-400 border border-rose-500/20';
      default:
        return 'bg-blue-500/10 text-blue-400 border border-blue-500/20';
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden p-4 md:p-8 max-w-[1280px] mx-auto w-full gap-6 text-white">
      <h1 className="settings-page-title shrink-0 mb-0">Settings</h1>
      
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-0 overflow-hidden pb-4">
        {/* Left Column (Directories & Background Scans & Danger Zone) */}
        <div className="lg:col-span-6 flex flex-col gap-6 min-h-0 overflow-y-auto pr-2 custom-scrollbar">
          {backgroundScans.length > 0 && (
            <section className="settings-card mb-0">
              <div className="settings-section-header">
                <div>
                  <h3 className="text-lg font-medium text-[var(--color-text-primary)]">Background Scans</h3>
                  <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                    Pause, resume, or retry directory and Takeout import tasks. Progress is saved across reloads.
                  </p>
                </div>
              </div>

              <div className="space-y-3">
                {backgroundScans.map((scan) => {
                  const progress = scan.progress;
                  const total = progress?.total_found || 0;
                  const processed = progress?.processed || 0;
                  const percent = total > 0 ? Math.round((processed / total) * 100) : 0;
                  const isML = scan.task_id === 'ml-pipeline' || scan.path === 'AI Media Analysis';
                  const isTakeout = scan.mode === 'takeout';
                  const canPause = scan.status === 'pending' || scan.status === 'running';
                  const canResume = scan.status === 'paused';
                  const canRetry = scan.status === 'error';

                  return (
                    <div
                      key={scan.task_id}
                      className="flex flex-col p-4 bg-white/5 rounded-xl border border-white/5"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0 flex-1">
                          <div className="font-semibold text-sm text-[var(--color-text-primary)] truncate" title={scan.path ?? undefined}>
                            {isML ? 'AI Media Analysis' : isTakeout ? 'Takeout Import' : 'Directory Scan'}
                          </div>
                          <div className="text-xs font-mono text-white/50 truncate mt-0.5" title={scan.path ?? undefined}>
                            {scan.path}
                          </div>
                          <div className="text-xs mt-2 text-[var(--color-text-secondary)]">
                            <span className="font-medium">{getScanStatusLabel(scan.status)}</span>
                            {total > 0 && (
                              <span>
                                {' '}• {processed} / {total} files ({percent}%)
                              </span>
                            )}
                            {progress && (
                              <span>
                                {isML ? (
                                  <span>
                                    {' '}• Faces: {progress.faces_found || 0} • Labels: {progress.labels_found || 0}
                                  </span>
                                ) : (
                                  <span>
                                    {' '}• New: {progress.new_inserted} • Dupes: {progress.duplicates_skipped}
                                  </span>
                                )}
                              </span>
                            )}
                          </div>
                          {scan.error_message && (
                            <p className="text-xs text-rose-400 mt-2 truncate" title={scan.error_message}>
                              {scan.error_message}
                            </p>
                          )}
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          {canPause && (
                            <button
                              type="button"
                              onClick={() => void handleScanAction(scan.task_id, 'pause')}
                              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors"
                            >
                              Pause
                            </button>
                          )}
                          {canResume && (
                            <button
                              type="button"
                              onClick={() => void handleScanAction(scan.task_id, 'resume')}
                              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-200 transition-colors"
                            >
                              Resume
                            </button>
                          )}
                          {canRetry && (
                            <button
                              type="button"
                              onClick={() => void handleScanAction(scan.task_id, 'retry')}
                              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 transition-colors"
                            >
                              Retry
                            </button>
                          )}
                        </div>
                      </div>

                      {total > 0 && (
                        <div className="mt-3 w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all duration-300 ${
                              scan.status === 'error'
                                ? 'bg-rose-500'
                                : scan.status === 'paused'
                                  ? 'bg-amber-500'
                                  : 'bg-indigo-500'
                            }`}
                            style={{ width: `${percent}%` }}
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          <section className="settings-card mb-0">
            <div className="settings-section-header">
              <div>
                <h3 className="text-lg font-medium text-[var(--color-text-primary)]">Synced Directories</h3>
                <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                  Folders listed here are monitored for changes. Any photos dropped into these folders will automatically appear in your library.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleRetrainML}
                  className="p-2 rounded-lg bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 transition-colors border border-indigo-500/20"
                  title="Retrain AI"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                     <path d="M2 12h4l2-9 5 18 2-9h5"/>
                  </svg>
                </button>
                <button
                  onClick={handleResyncAll}
                  className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors border border-white/5"
                  title="Resync All"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                    <path d="M3 3v5h5"/>
                  </svg>
                </button>
                <button
                  onClick={handleAdd}
                  className="outlined-action-button settings-add-button"
                >
                  <svg 
                    width="18" 
                    height="18" 
                    viewBox="0 0 24 24" 
                    fill="none" 
                    stroke="currentColor" 
                    strokeWidth="2"
                  >
                    <line x1="12" y1="5" x2="12" y2="19" />
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                  <span>Add folder</span>
                </button>
              </div>
            </div>

            {loading ? (
              <div className="animate-pulse space-y-4">
                <div className="h-16 bg-white/5 rounded-lg w-full"></div>
                <div className="h-16 bg-white/5 rounded-lg w-full"></div>
              </div>
            ) : directories.length === 0 ? (
              <div className="text-center py-12 border-2 border-dashed border-white/10 rounded-xl">
                <svg className="mx-auto h-12 w-12 text-white/20 mb-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                </svg>
                <p className="text-[var(--color-text-secondary)]">No directories are currently being synced.</p>
              </div>
            ) : (
              <div className="max-h-[300px] overflow-y-auto pr-2 space-y-3">
                {directories.map(dir => {
                  const progressData = findScanForPath(dir.path);
                  const isRunning = progressData?.status === 'running' || progressData?.status === 'pending' || progressData?.status === 'pausing';

                  const progress = progressData?.progress;
                  const total = progress?.total_found || dir.total_files || 0;
                  const processed = progress?.processed || dir.synced_files || 0;
                  const percent = total > 0 ? Math.round((processed / total) * 100) : 0;

                  return (
                    <div key={dir.id} className="flex flex-col p-4 bg-white/5 rounded-xl border border-white/5 hover:bg-white/10 transition-all duration-300">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4 min-w-0 flex-1">
                          <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                            isRunning 
                              ? 'bg-indigo-400 shadow-[0_0_8px_rgba(99,102,241,0.6)] animate-pulse' 
                              : dir.is_active 
                              ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]' 
                              : 'bg-white/20'
                          }`} />
                          <div className="min-w-0">
                            <div className="font-semibold text-[var(--color-text-primary)] font-mono text-sm truncate" title={dir.path}>
                              {dir.path}
                            </div>
                            <div className="text-xs mt-1 flex items-center gap-2">
                              <span className={dir.is_active ? 'text-emerald-400/80' : 'text-white/30'}>
                                {dir.is_active ? 'Actively Monitored' : 'Paused'}
                              </span>
                              <span className="text-white/20">•</span>
                              <span className="text-[var(--color-text-secondary)] font-medium">
                                {isRunning ? (
                                  <span className="text-indigo-400">
                                    Syncing: {processed} / {total} files ({percent}%)
                                  </span>
                                ) : (
                                  <span>
                                    Synced: {dir.synced_files} / {dir.total_files} files ({dir.total_files > 0 ? Math.round((dir.synced_files / dir.total_files) * 100) : 0}%)
                                  </span>
                                )}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 shrink-0 ml-4">
                          {isRunning && progressData && (
                            <button
                              type="button"
                              onClick={() => void handleScanAction(progressData.task_id, 'pause')}
                              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors"
                              title="Pause scan"
                            >
                              Pause
                            </button>
                          )}
                          <button
                            onClick={() => handleRemove(dir.id)}
                            className="text-[var(--color-danger)] hover:bg-[var(--color-danger)] hover:bg-opacity-10 p-2 rounded-lg transition-colors"
                            title="Stop Syncing"
                          >
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <line x1="18" y1="6" x2="6" y2="18" />
                              <line x1="6" y1="6" x2="18" y2="18" />
                            </svg>
                          </button>
                        </div>
                      </div>

                      {/* Progress Bar (Always show when running or not fully synced) */}
                      {(isRunning || percent < 100) && total > 0 && (
                        <div className="mt-3.5 w-full">
                          <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
                            <div
                              className={`h-full transition-all duration-300 ${
                                isRunning ? 'bg-indigo-500' : 'bg-emerald-500'
                              }`}
                              style={{ width: `${percent}%` }}
                            />
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <section className="settings-card settings-danger-card mb-0">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-red-400">Danger Zone</h3>
                <p className="text-sm text-[var(--color-text-secondary)] mt-1.5 leading-relaxed">
                  Resets the platform to a clean state. This will delete all indexed database records, custom albums, tags, and cached thumbnails/previews. Original files on disk will not be deleted.
                </p>
              </div>
              <button
                onClick={handleFactoryReset}
                disabled={resetting}
                className={`px-5 py-2.5 rounded-xl font-semibold text-white transition-all duration-300 transform active:scale-95 cursor-pointer shadow-lg shadow-red-900/20 shrink-0 select-none relative overflow-hidden group ${
                  resetting ? 'opacity-50 cursor-not-allowed' : ''
                }`}
                style={{
                  background: 'linear-gradient(135deg, #ef4444 0%, #b91c1c 100%)',
                  border: '1px solid rgba(239, 68, 68, 0.2)',
                }}
              >
                {/* Hover sheen effect */}
                <div className="absolute inset-0 w-full h-full bg-gradient-to-r from-transparent via-white/10 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-1000 ease-out" />
                <span>{resetting ? 'Resetting...' : 'Factory Reset'}</span>
              </button>
            </div>
          </section>
        </div>

        {/* Right Column (Activity Logs) */}
        <div className="lg:col-span-6 flex flex-col min-h-0 overflow-hidden">
          <section className="settings-card flex-1 flex flex-col min-h-0 overflow-hidden mb-0">
            <div className="settings-section-header shrink-0">
              <div>
                <h3 className="text-lg font-medium text-[var(--color-text-primary)]">Activity Logs</h3>
                <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                  Tracks actions taken on photos, albums, and directory sync status.
                </p>
              </div>
              <button 
                onClick={loadAuditLogs} 
                className="text-xs text-[var(--color-accent)] font-medium hover:underline p-1 flex items-center gap-1.5"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
                </svg>
                Refresh
              </button>
            </div>

            {logsLoading ? (
              <div className="flex justify-center py-8 flex-1 items-center">
                <div className="w-6 h-6 rounded-full border-2 border-white/30 border-t-white animate-spin" />
              </div>
            ) : auditLogs.length === 0 ? (
              <div className="text-center py-8 text-[var(--color-text-secondary)] text-sm flex-1 flex items-center justify-center">
                No activity logged yet.
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
                <div className="border-l-2 border-white/10 ml-8 pl-6 space-y-5 py-2">
                  {auditLogs.map((log) => (
                    <div key={log.id} className="relative">
                      {/* Visual node indicator */}
                      <div 
                        className={`absolute -left-[31px] top-1.5 w-3.5 h-3.5 rounded-full border-2 border-[#1a1a1a] ${
                          log.level === 'success' ? 'bg-emerald-500' :
                          log.level === 'warning' ? 'bg-amber-500' :
                          log.level === 'error' ? 'bg-rose-500' : 'bg-blue-500'
                        }`} 
                      />
                      <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-white/90 font-mono capitalize">
                            {log.action.replace(/_/g, ' ')}
                          </span>
                          <span className={`text-[10px] px-2 py-0.5 rounded font-mono font-medium ${getLevelBadgeStyles(log.level)}`}>
                            {log.level}
                          </span>
                        </div>
                        <span className="text-[10px] text-white/30 font-medium shrink-0">
                          {new Date(log.timestamp).toLocaleString()}
                        </span>
                      </div>
                      {log.details && (
                        <p className="text-xs text-white/50 mt-1 leading-relaxed max-w-2xl font-mono truncate" title={log.details}>
                          {log.details}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
