import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DownloadBar } from './components/DownloadBar';
import { TaskList } from './components/TaskList';
import { ClipboardToast } from './components/ClipboardToast';
import { CookieManager } from './components/CookieManager';
import { SettingsPanel } from './components/SettingsPanel';

type Page = 'main' | 'cookies' | 'settings';

export function App(): React.ReactElement {
  const { t } = useTranslation();
  const [page, setPage] = useState<Page>('main');

  return (
    <div style={styles.container}>
      <Header page={page} onNavigate={setPage} t={t} />
      <div style={styles.body}>
        {page === 'main' && <MainPage />}
        {page === 'cookies' && <CookieManager />}
        {page === 'settings' && <SettingsPanel />}
      </div>
    </div>
  );
}

function Header({
  page,
  onNavigate,
  t,
}: {
  page: Page;
  onNavigate: (p: Page) => void;
  t: (key: string) => string;
}): React.ReactElement {
  return (
    <div style={styles.header}>
      <div style={styles.titleBar}>
        <span style={styles.title}>{t('app.title')}</span>
        <div style={styles.nav}>
          <button
            style={{ ...styles.navBtn, ...(page === 'main' ? styles.navBtnActive : {}) }}
            onClick={() => onNavigate('main')}
          >
            {t('app.tasks')}
          </button>
          <button
            style={{ ...styles.navBtn, ...(page === 'cookies' ? styles.navBtnActive : {}) }}
            onClick={() => onNavigate('cookies')}
          >
            {t('app.cookies')}
          </button>
          <button
            style={{ ...styles.navBtn, ...(page === 'settings' ? styles.navBtnActive : {}) }}
            onClick={() => onNavigate('settings')}
          >
            {t('app.settings')}
          </button>
        </div>
        <div style={styles.windowControls}>
          <span
            style={styles.controlBtn}
            onClick={() => (window as any).electronAPI?.window.minimize()}
          >
            &#x2014;
          </span>
          <span
            style={styles.controlBtn}
            onClick={() => (window as any).electronAPI?.window.close()}
          >
            &#x2715;
          </span>
        </div>
      </div>
    </div>
  );
}

function MainPage(): React.ReactElement {
  return (
    <div style={styles.page}>
      <DownloadBar />
      <TaskList />
      <ClipboardToast />
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    height: '100vh',
    display: 'flex',
    flexDirection: 'column',
    background: '#0d1117',
  },
  header: {
    height: 40,
    background: '#161b22',
    borderBottom: '1px solid #21262d',
    display: 'flex',
    alignItems: 'center',
  },
  titleBar: {
    display: 'flex',
    alignItems: 'center',
    width: '100%',
    padding: '0 8px',
    WebkitAppRegion: 'drag' as any,
  },
  title: {
    fontSize: 13,
    fontWeight: 600,
    color: '#58a6ff',
    marginRight: 16,
  },
  nav: {
    display: 'flex',
    gap: 4,
    WebkitAppRegion: 'no-drag' as any,
  },
  navBtn: {
    background: 'none',
    border: 'none',
    color: '#8b949e',
    fontSize: 12,
    padding: '4px 10px',
    borderRadius: 4,
    cursor: 'pointer',
  },
  navBtnActive: {
    background: '#1f6feb',
    color: '#ffffff',
  },
  windowControls: {
    marginLeft: 'auto',
    display: 'flex',
    gap: 0,
    WebkitAppRegion: 'no-drag' as any,
  },
  controlBtn: {
    color: '#8b949e',
    fontSize: 12,
    padding: '4px 10px',
    cursor: 'pointer',
  },
  body: {
    flex: 1,
    overflow: 'hidden',
  },
  page: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    position: 'relative',
  },
};
