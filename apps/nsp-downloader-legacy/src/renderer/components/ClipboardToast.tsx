import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface ToastState {
  url: string;
  visible: boolean;
}

export function ClipboardToast(): React.ReactElement {
  const { t } = useTranslation();
  const [toast, setToast] = useState<ToastState>({ url: '', visible: false });
  const [added, setAdded] = useState(false);

  useEffect(() => {
    const api = (window as any).electronAPI;
    if (!api?.clipboard?.onCapture) return;

    const unsubscribe = api.clipboard.onCapture((event: { url: string }) => {
      setToast({ url: event.url, visible: true });
      setAdded(false);
    });

    return unsubscribe;
  }, []);

  const handleAdd = async () => {
    try {
      await (window as any).electronAPI.download.add(toast.url);
      setAdded(true);
      setTimeout(() => setToast({ url: '', visible: false }), 1500);
    } catch (err) {
      console.error('Failed to add:', err);
    }
  };

  const handleDismiss = () => {
    setToast({ url: '', visible: false });
  };

  if (!toast.visible) return <></>;

  return (
    <div style={styles.overlay}>
      <div style={styles.toast}>
        <div style={styles.icon}>&#9889;</div>
        <div style={styles.text}>
          <div style={styles.title}>{t('clipboard.detected')}</div>
          <div style={styles.url}>{toast.url.length > 50 ? toast.url.substring(0, 50) + '...' : toast.url}</div>
        </div>
        <div style={styles.actions}>
          {!added ? (
            <>
              <button style={styles.addBtn} onClick={handleAdd}>
                {t('download.add')}
              </button>
              <button style={styles.dismissBtn} onClick={handleDismiss}>
                x
              </button>
            </>
          ) : (
            <span style={styles.doneText}>{t('clipboard.added')}</span>
          )}
        </div>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'absolute',
    bottom: 16,
    left: 16,
    right: 16,
    zIndex: 100,
    pointerEvents: 'auto',
    animation: 'none',
  },
  toast: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    background: '#1c2128',
    border: '1px solid #3fb950',
    borderRadius: 10,
    padding: '12px 14px',
    boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
  },
  icon: {
    fontSize: 20,
    flexShrink: 0,
  },
  text: {
    flex: 1,
    minWidth: 0,
  },
  title: {
    fontSize: 13,
    fontWeight: 600,
    color: '#c9d1d9',
    marginBottom: 2,
  },
  url: {
    fontSize: 11,
    color: '#8b949e',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  actions: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    flexShrink: 0,
  },
  addBtn: {
    background: '#238636',
    color: '#ffffff',
    border: 'none',
    borderRadius: 6,
    padding: '5px 14px',
    fontSize: 12,
    fontWeight: 600,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  dismissBtn: {
    background: 'none',
    border: 'none',
    color: '#484f58',
    fontSize: 14,
    cursor: 'pointer',
    padding: '2px 6px',
  },
  doneText: {
    fontSize: 12,
    color: '#3fb950',
    fontWeight: 600,
  },
};
