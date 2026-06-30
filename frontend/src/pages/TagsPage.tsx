import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchTags, createTag, deleteTag, triggerTagScan } from '../api/client';
import { dialog } from '../components/DialogContainer';
import type { TagWithCount, ScanStatusResponse } from '../api/types';

interface TagsPageProps {
  scanProgress: Record<string, ScanStatusResponse>;
  onScanStarted: (taskId: string, path: string, mode: 'scan' | 'takeout') => void;
}

export default function TagsPage({ scanProgress, onScanStarted }: TagsPageProps) {
  const navigate = useNavigate();
  const [tags, setTags] = useState<TagWithCount[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newTagName, setNewTagName] = useState('');
  const [activeTab, setActiveTab] = useState<'user' | 'auto'>('user');

  const loadTags = async () => {
    try {
      const data = await fetchTags();
      setTags(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTags();
  }, []);

  // Reload tags when any tag-scan completes
  useEffect(() => {
    const hasCompletedScan = Object.values(scanProgress).some(
      (scan) => scan.task_id.startsWith('tag-scan-') && scan.status === 'complete'
    );
    if (hasCompletedScan) {
      loadTags();
    }
  }, [scanProgress]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTagName.trim()) return;
    try {
      const newTag = await createTag(newTagName.trim());
      setNewTagName('');
      setShowCreate(false);
      
      // Auto-scan is triggered by backend POST /api/tags
      // Let's notify App of the started scan task
      const taskId = `tag-scan-${newTag.id}`;
      onScanStarted(taskId, `Tag: ${newTag.name}`, 'scan');
      
      await loadTags();
    } catch (e) {
      console.error(e);
      dialog.alert('Failed to create tag');
    }
  };

  const handleDelete = async (tagId: string, name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!(await dialog.confirm(`Are you sure you want to delete the tag "${name}"?`))) return;
    try {
      await deleteTag(tagId);
      await loadTags();
    } catch (e) {
      console.error(e);
      dialog.alert('Failed to delete tag');
    }
  };

  const handleReanalyze = async (tagId: string, name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const res = await triggerTagScan(tagId);
      onScanStarted(res.task_id, `Tag: ${name}`, 'scan');
      dialog.alert(`Re-analysis started for "${name}"`);
    } catch (e) {
      console.error(e);
      dialog.alert('Failed to start re-analysis');
    }
  };

  const filteredTags = tags.filter(tag => 
    activeTab === 'user' ? tag.source === 'user' : tag.source !== 'user'
  );

  return (
    <div className="timeline-view text-white">
      <div className="timeline-toolbar">
        <div className="timeline-heading">
          <h1>Tags</h1>
          <span>Auto-scan photos using CLIP semantic AI.</span>
        </div>
        <div className="grouping-control">
          <button
            type="button"
            className={activeTab === 'user' ? 'active' : ''}
            onClick={() => setActiveTab('user')}
          >
            My Tags
          </button>
          <button
            type="button"
            className={activeTab === 'auto' ? 'active' : ''}
            onClick={() => setActiveTab('auto')}
          >
            Auto Tags
          </button>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="outlined-action-button"
        >
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Create Tag
        </button>
      </div>

      <div className="timeline-scroller overflow-y-auto px-7 py-6">
        {showCreate && (
          <form onSubmit={handleCreate} className="album-create-panel mb-6">
            <h2>New Tag</h2>
            <div className="album-create-fields">
              <input
                type="text"
                value={newTagName}
                onChange={(e) => setNewTagName(e.target.value)}
                placeholder="Tag name (e.g. food, beach, cat)"
                className="input-field"
                autoFocus
              />
              <button type="submit" className="btn-primary">
                Create & Scan
              </button>
              <button type="button" onClick={() => setShowCreate(false)} className="text-button">
                Cancel
              </button>
            </div>
          </form>
        )}

        {loading ? (
          <div className="tags-grid" aria-label="Loading tags">
            <div className="tag-skeleton skeleton" />
            <div className="tag-skeleton skeleton" />
            <div className="tag-skeleton skeleton" />
          </div>
        ) : filteredTags.length === 0 ? (
          activeTab === 'user' ? (
            <div className="albums-empty-state">
              <div className="albums-empty-icon">
                <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
                  <line x1="7" y1="7" x2="7.01" y2="7" strokeWidth="2.5" />
                </svg>
              </div>
              <h2>Create your first semantic tag</h2>
              <p>Type any keyword, and our CLIP AI will scan your library to tag matching photos.</p>
            </div>
          ) : (
            <div className="albums-empty-state">
              <div className="albums-empty-icon">
                <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
                  <line x1="7" y1="7" x2="7.01" y2="7" strokeWidth="2.5" />
                </svg>
              </div>
              <h2>No automatic tags found</h2>
              <p>Photos must be analyzed to extract auto tags and OCR text.</p>
            </div>
          )
        ) : (
          <div className="tags-grid">
            {filteredTags.map((tag) => {
              const taskId = `tag-scan-${tag.id}`;
              const activeScan = scanProgress[taskId];
              const isScanning = activeScan?.status === 'running' || activeScan?.status === 'pending';
              const progressPct = isScanning && activeScan.progress && activeScan.progress.total_found > 0
                ? Math.round((activeScan.progress.processed / activeScan.progress.total_found) * 100)
                : 0;

              return (
                <button
                  type="button"
                  key={tag.id}
                  className="tag-card"
                  onClick={() => navigate(`/tags/${tag.id}`)}
                >
                  <div className="tag-card-content">
                    <div className="tag-card-header">
                      <span className="tag-name">#{tag.name}</span>
                      <span className="tag-count">{tag.media_count} items</span>
                    </div>

                    {isScanning && (
                      <div className="tag-scan-progress-container">
                        <div className="tag-scan-status-text">
                          Scanning... {progressPct}%
                        </div>
                        <div className="tag-progress-bar-bg">
                          <div 
                            className="tag-progress-bar-fill"
                            style={{ width: `${progressPct}%` }}
                          />
                        </div>
                      </div>
                    )}

                    <div className="tag-card-actions">
                      <button
                        type="button"
                        className="tag-action-btn reanalyze"
                        onClick={(e) => handleReanalyze(tag.id, tag.name, e)}
                        disabled={isScanning}
                        title="Re-run CLIP AI analysis"
                      >
                        Re-analyze
                      </button>
                      <button
                        type="button"
                        className="tag-action-btn delete"
                        onClick={(e) => handleDelete(tag.id, tag.name, e)}
                        title="Delete tag"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
