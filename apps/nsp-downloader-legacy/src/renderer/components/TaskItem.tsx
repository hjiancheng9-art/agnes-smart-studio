import React from 'react';
import { useTranslation } from 'react-i18next';

interface TaskItemProps {
  task: {
    gid: string;
    status: string;
    totalLength: string;
    completedLength: string;
    downloadSpeed: string;
    files?: Array<{ path: string; length: string }>;
    errorMessage?: string;
    errorCode?: string;
    progress?: number;
    kind?: string;
  };
}

function formatSpeed(speed: string): string {
  const bps = parseInt(speed, 10);
  if (!bps || bps <= 0) return '0 B/s';
  if (bps < 1024) return `${bps} B/s`;
  if (bps < 1024 * 1024) return `${(bps / 1024).toFixed(1)} KB/s`;
  if (bps < 1024 * 1024 * 1024) return `${(bps / 1024 / 1024).toFixed(1)} MB/s`;
  return `${(bps / 1024 / 1024 / 1024).toFixed(2)} GB/s`;
}

function formatSize(bytes: string): string {
  const b = parseInt(bytes, 10);
  if (!b || b <= 0) return '--';
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`;
  return `${(b / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function calcProgress(completed: string, total: string): number {
  const c = parseInt(completed, 10) || 0;
  const t = parseInt(total, 10) || 0;
  if (t <= 0) return 0;
  return Math.round((c / t) * 100);
}

function formatTransfer(task: TaskItemProps['task']): string {
  const completed = formatSize(task.completedLength);
  const total = formatSize(task.totalLength);

  if (task.kind === 'video' && total === '--') {
    return completed;
  }

  return `${completed} / ${total}`;
}

function getFileName(task: TaskItemProps['task']): string {
  if (task.files && task.files.length > 0) {
    const p = task.files[0].path;
    const parts = p.replace(/\\/g, '/').split('/');
    return parts[parts.length - 1] || 'Unknown';
  }
  return 'Downloading...';
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'active': return '#3fb950';
    case 'paused': return '#d29922';
    case 'complete': return '#58a6ff';
    case 'error': return '#f85149';
    default: return '#8b949e';
  }
}

export function TaskItem({ task }: TaskItemProps): React.ReactElement {
  const { t } = useTranslation();
  const progress = typeof task.progress === 'number'
    ? Math.max(0, Math.min(100, Math.round(task.progress)))
    : calcProgress(task.completedLength, task.totalLength);
  const fileName = getFileName(task);
  const statusColor = getStatusColor(task.status);

  const statusLabel = t(`download.status.${task.status}`, t('download.status.unknown'));
  const isVideoTask = task.kind === 'video';

  const handlePause = () => {
    (window as any).electronAPI.download.pause(task.gid);
  };

  const handleResume = () => {
    (window as any).electronAPI.download.resume(task.gid);
  };

  const handleDelete = () => {
    (window as any).electronAPI.download.delete(task.gid);
  };

  // Video tasks with a mediaUrl can be retried after errors (app restart,
  // transient ffmpeg failure). aria2 tasks use resume instead.
  const canRetry = task.kind === 'video' && task.status === 'error';

  const handleRetry = () => {
    (window as any).electronAPI.download.retry(task.gid);
  };

  return (
    <div style={styles.card}>
      <div style={styles.row}>
        <span style={styles.name}>{fileName}</span>
        <span style={{ ...styles.status, color: statusColor }}>{statusLabel}</span>
      </div>

      <div style={styles.progressWrapper}>
        <div style={styles.progressTrack}>
          <div
            style={{
              ...styles.progressFill,
              width: `${progress}%`,
              background: statusColor,
            }}
          />
        </div>
        <span style={styles.progressText}>{progress}%</span>
      </div>

      <div style={styles.row}>
        <span style={styles.meta}>
          {formatTransfer(task)}
        </span>
        <span style={styles.meta}>{formatSpeed(task.downloadSpeed)}</span>
      </div>

      {task.errorMessage && (
        <div style={styles.error}>{task.errorMessage}</div>
      )}

      <div style={styles.actions}>
        {task.status === 'active' && (
          isVideoTask ? null : (
            <button style={styles.actionBtn} onClick={handlePause}>
              {t('download.pause')}
            </button>
          )
        )}
        {task.status === 'paused' && (
          <button style={styles.actionBtn} onClick={handleResume}>
            {t('download.resume')}
          </button>
        )}
        {canRetry && (
          <button style={{ ...styles.actionBtn, color: '#3fb950' }} onClick={handleRetry}>
            {t('download.retry')}
          </button>
        )}
        <button style={{ ...styles.actionBtn, color: '#f85149' }} onClick={handleDelete}>
          {t('download.delete')}
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    background: '#161b22',
    border: '1px solid #21262d',
    borderRadius: 8,
    padding: 12,
    marginBottom: 8,
  },
  row: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  name: {
    fontSize: 13,
    color: '#c9d1d9',
    fontWeight: 500,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    maxWidth: '70%',
  },
  status: {
    fontSize: 11,
    fontWeight: 600,
  },
  progressWrapper: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6,
  },
  progressTrack: {
    flex: 1,
    height: 4,
    background: '#21262d',
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: 2,
    transition: 'width 0.3s ease',
  },
  progressText: {
    fontSize: 11,
    color: '#8b949e',
    minWidth: 32,
    textAlign: 'right',
  },
  meta: {
    fontSize: 11,
    color: '#8b949e',
  },
  error: {
    fontSize: 11,
    color: '#f85149',
    marginTop: 4,
  },
  actions: {
    display: 'flex',
    gap: 8,
    marginTop: 8,
  },
  actionBtn: {
    background: '#21262d',
    border: '1px solid #30363d',
    color: '#c9d1d9',
    fontSize: 11,
    padding: '4px 12px',
    borderRadius: 4,
    cursor: 'pointer',
  },
};
