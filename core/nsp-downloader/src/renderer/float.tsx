import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';

interface Task {
  gid: string;
  status: string;
  totalLength: string;
  completedLength: string;
  downloadSpeed: string;
  files?: Array<{ path: string }>;
  errorMessage?: string;
}

function formatSpeed(speed: string): string {
  const bps = parseInt(speed, 10);
  if (!bps || bps <= 0) return '0 B/s';
  if (bps < 1024) return `${bps} B/s`;
  if (bps < 1024 * 1024) return `${(bps / 1024).toFixed(1)} KB/s`;
  if (bps < 1024 * 1024 * 1024) return `${(bps / 1024 / 1024).toFixed(1)} MB/s`;
  return `${(bps / 1024 / 1024 / 1024).toFixed(2)} GB/s`;
}

function calcProgress(completed: string, total: string): number {
  const c = parseInt(completed, 10) || 0;
  const t = parseInt(total, 10) || 0;
  if (t <= 0) return 0;
  return Math.round((c / t) * 100);
}

function getShortName(task: Task): string {
  if (task.files && task.files.length > 0) {
    const parts = task.files[0].path.replace(/\\/g, '/').split('/');
    const name = parts[parts.length - 1] || '...';
    return name.length > 20 ? name.substring(0, 18) + '..' : name;
  }
  return '...';
}

function FloatPanel(): React.ReactElement {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [hidden, setHidden] = useState(true);

  useEffect(() => {
    const poll = () => {
      const api = (window as any).electronAPI;
      if (!api) return;

      Promise.all([
        api.download.getActive(),
        api.download.getWaiting(0, 10),
      ]).then(([active, waiting]) => {
        const all = [...(active || []), ...(waiting || [])];
        setTasks(all);
        setHidden(all.length === 0);
      }).catch(() => {});
    };

    poll();
    const interval = setInterval(poll, 1000);
    return () => clearInterval(interval);
  }, []);

  if (hidden) return <div />;

  const activeTask = tasks.find((t: Task) => t.status === 'active') || tasks[0];
  if (!activeTask) return <div />;

  const progress = calcProgress(activeTask.completedLength, activeTask.totalLength);
  const totalSpeed = tasks
    .filter((t: Task) => t.status === 'active')
    .reduce((sum, t) => sum + (parseInt(t.downloadSpeed, 10) || 0), 0);

  const handleShowMain = () => {
    const api = (window as any).electronAPI;
    api?.float?.showMain();
  };

  const handleClose = () => {
    const api = (window as any).electronAPI;
    api?.float?.hide();
  };

  return (
    <div style={styles.panel}>
      <div style={styles.header}>
        <span style={styles.title}>{getShortName(activeTask)}</span>
        <button style={styles.closeBtn} onClick={handleClose}>x</button>
      </div>
      <div style={styles.progressWrapper}>
        <div style={styles.progressTrack}>
          <div style={{ ...styles.progressFill, width: `${progress}%` }} />
        </div>
        <span style={styles.progressText}>{progress}%</span>
      </div>
      <div style={styles.stats} onClick={handleShowMain}>
        <span style={styles.speed}>{formatSpeed(String(totalSpeed))}</span>
        <span style={styles.count}>
          {tasks.filter((t: Task) => t.status === 'active').length} active
          {tasks.length > 1 ? ` / ${tasks.length} total` : ''}
        </span>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    width: 240,
    background: 'rgba(13, 17, 23, 0.92)',
    border: '1px solid #30363d',
    borderRadius: 8,
    padding: '8px 10px',
    boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  title: {
    fontSize: 11,
    color: '#c9d1d9',
    fontWeight: 500,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    maxWidth: 190,
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: '#484f58',
    fontSize: 12,
    cursor: 'pointer',
    padding: '0 2px',
  },
  progressWrapper: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
  },
  progressTrack: {
    flex: 1,
    height: 3,
    background: '#21262d',
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    background: '#238636',
    borderRadius: 2,
    transition: 'width 0.3s ease',
  },
  progressText: {
    fontSize: 10,
    color: '#8b949e',
    minWidth: 28,
    textAlign: 'right',
  },
  stats: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    cursor: 'pointer',
  },
  speed: {
    fontSize: 14,
    fontWeight: 700,
    color: '#3fb950',
  },
  count: {
    fontSize: 10,
    color: '#484f58',
  },
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <FloatPanel />
  </React.StrictMode>
);
