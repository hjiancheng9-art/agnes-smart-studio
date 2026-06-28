import React, { useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { TaskItem } from './TaskItem';
import { useDownloadStore } from '../hooks/useDownloads';

export function TaskList(): React.ReactElement {
  const { t } = useTranslation();
  const { tasks, refresh } = useDownloadStore();

  const poll = useCallback(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    poll();
    const interval = setInterval(poll, 1000);
    return () => clearInterval(interval);
  }, [poll]);

  const handleClearFinished = async () => {
    await (window as any).electronAPI.download.clearFinished();
    refresh();
  };

  const handleOpenFolder = async () => {
    await (window as any).electronAPI.download.openFolder();
  };

  return (
    <>
      <div style={styles.toolbar}>
        <button style={styles.toolbarBtn} onClick={handleOpenFolder}>
          {t('download.openFolder')}
        </button>
        <button style={styles.toolbarBtn} onClick={handleClearFinished}>
          {t('download.clearFinished')}
        </button>
      </div>
      {tasks.length === 0 ? (
        <div style={styles.empty}>
          <p>{t('download.noTasks')}</p>
        </div>
      ) : (
        <div style={styles.list}>
          {tasks.map((task: any) => (
            <TaskItem key={task.gid} task={task} />
          ))}
        </div>
      )}
    </>
  );
}

const styles: Record<string, React.CSSProperties> = {
  toolbar: {
    display: 'flex',
    gap: 8,
    padding: '8px 14px 0',
  },
  toolbarBtn: {
    background: '#21262d',
    border: '1px solid #30363d',
    color: '#c9d1d9',
    fontSize: 12,
    padding: '6px 10px',
    borderRadius: 6,
    cursor: 'pointer',
  },
  list: {
    flex: 1,
    overflowY: 'auto',
    padding: '8px 14px',
  },
  empty: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#484f58',
    fontSize: 13,
  },
};
