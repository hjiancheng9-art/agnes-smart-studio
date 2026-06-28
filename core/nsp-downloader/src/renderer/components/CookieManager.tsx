import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';

export function CookieManager(): React.ReactElement {
  const { t } = useTranslation();
  const [result, setResult] = useState<{ browser: string; count: number } | null>(null);
  const [loading, setLoading] = useState(false);

  const handleImport = async (browser: 'chrome' | 'edge') => {
    setLoading(true);
    setResult(null);
    try {
      const res = await (window as any).electronAPI.cookie.import(browser);
      setResult({ browser, count: res.count });
    } catch {
      setResult({ browser, count: -1 });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>{t('cookie.title')}</h2>
      <p style={styles.desc}>{t('cookie.desc')}</p>

      <div style={styles.buttons}>
        <button
          style={styles.btn}
          onClick={() => handleImport('chrome')}
          disabled={loading}
        >
          {t('cookie.importChrome')}
        </button>
        <button
          style={styles.btn}
          onClick={() => handleImport('edge')}
          disabled={loading}
        >
          {t('cookie.importEdge')}
        </button>
      </div>

      {loading && <p style={styles.loading}>{t('cookie.extracting')}</p>}

      {result && result.count >= 0 && (
        <div style={styles.success}>
          {t('cookie.success', { count: result.count, browser: result.browser })}
        </div>
      )}

      {result && result.count < 0 && (
        <div style={styles.error}>
          {t('cookie.failed')}
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: 20,
    height: '100%',
  },
  title: {
    fontSize: 16,
    fontWeight: 600,
    color: '#c9d1d9',
    marginBottom: 8,
  },
  desc: {
    fontSize: 13,
    color: '#8b949e',
    marginBottom: 20,
    lineHeight: 1.5,
  },
  buttons: {
    display: 'flex',
    gap: 10,
    marginBottom: 16,
  },
  btn: {
    flex: 1,
    background: '#21262d',
    border: '1px solid #30363d',
    color: '#c9d1d9',
    fontSize: 13,
    padding: '10px 16px',
    borderRadius: 6,
    cursor: 'pointer',
  },
  loading: {
    color: '#d29922',
    fontSize: 13,
    marginBottom: 12,
  },
  success: {
    background: '#0d3320',
    border: '1px solid #3fb950',
    color: '#3fb950',
    padding: '10px 14px',
    borderRadius: 6,
    fontSize: 13,
  },
  error: {
    background: '#490202',
    border: '1px solid #f85149',
    color: '#f85149',
    padding: '10px 14px',
    borderRadius: 6,
    fontSize: 13,
  },
};
