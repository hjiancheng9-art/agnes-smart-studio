import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

interface Settings {
  downloadDir: string;
  maxConnections: number;
  maxConcurrentTasks: number;
  maxDownloadSpeed: number;
  maxUploadSpeed: number;
  enableDht: boolean;
  seedRatio: number;
  seedTime: number;
  language: string;
  proxyAutoStart: boolean;
  proxyPort: number;
}

export function SettingsPanel(): React.ReactElement {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<Settings>({
    downloadDir: '',
    maxConnections: 16,
    maxConcurrentTasks: 5,
    maxDownloadSpeed: 0,
    maxUploadSpeed: 0,
    enableDht: true,
    seedRatio: 1.0,
    seedTime: 60,
    language: 'zh-CN',
    proxyAutoStart: false,
    proxyPort: 58309,
  });
  const [saved, setSaved] = useState(false);
  const [proxyOn, setProxyOn] = useState(false);
  const [proxyPort, setProxyPort] = useState(58309);

  useEffect(() => {
    (async () => {
      const s = await (window as any).electronAPI.settings.get();
      setSettings(s as Settings);
      const running = await (window as any).electronAPI.proxy.status();
      setProxyOn(running);
    })();

    const api = (window as any).electronAPI;
    if (api?.proxy?.onPortChange) {
      const unsub = api.proxy.onPortChange((port: number) => {
        setProxyPort(port);
      });
      return unsub;
    }
  }, []);

  const handleSelectDir = async () => {
    const dir = await (window as any).electronAPI.settings.selectDir();
    if (dir) {
      setSettings((prev) => ({ ...prev, downloadDir: dir }));
    }
  };

  const handleProxyToggle = async () => {
    if (proxyOn) {
      await (window as any).electronAPI.proxy.stop();
      setProxyOn(false);
    } else {
      const port = await (window as any).electronAPI.proxy.start();
      setProxyPort(port);
      setProxyOn(true);
    }
  };

  const handleSave = async () => {
    await (window as any).electronAPI.settings.update(settings);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>{t('settings.title')}</h2>

      <div style={styles.field}>
        <label style={styles.label}>{t('settings.downloadDir')}</label>
        <div style={styles.dirRow}>
          <input style={styles.input} value={settings.downloadDir} readOnly />
          <button style={styles.browseBtn} onClick={handleSelectDir}>
            {t('settings.browse')}
          </button>
        </div>
      </div>

      <div style={styles.field}>
        <label style={styles.label}>{t('settings.maxConnections')}</label>
        <input
          style={styles.input}
          type="number"
          min={1}
          max={64}
          value={settings.maxConnections}
          onChange={(e) =>
            setSettings((prev) => ({ ...prev, maxConnections: parseInt(e.target.value, 10) || 16 }))
          }
        />
      </div>

      <div style={styles.field}>
        <label style={styles.label}>{t('settings.maxConcurrentTasks')}</label>
        <input
          style={styles.input}
          type="number"
          min={1}
          max={20}
          value={settings.maxConcurrentTasks}
          onChange={(e) =>
            setSettings((prev) => ({ ...prev, maxConcurrentTasks: parseInt(e.target.value, 10) || 5 }))
          }
        />
      </div>

      <div style={styles.field}>
        <label style={styles.label}>{t('settings.maxDownloadSpeed')}</label>
        <input
          style={styles.input}
          type="number"
          min={0}
          step={100}
          value={settings.maxDownloadSpeed}
          onChange={(e) =>
            setSettings((prev) => ({ ...prev, maxDownloadSpeed: parseInt(e.target.value, 10) || 0 }))
          }
        />
      </div>

      <div style={styles.field}>
        <label style={styles.label}>{t('settings.maxUploadSpeed')}</label>
        <input
          style={styles.input}
          type="number"
          min={0}
          step={100}
          value={settings.maxUploadSpeed}
          onChange={(e) =>
            setSettings((prev) => ({ ...prev, maxUploadSpeed: parseInt(e.target.value, 10) || 0 }))
          }
        />
      </div>

      <div style={styles.separator} />

      <div style={styles.field}>
        <div
          style={styles.autoStartRow}
          onClick={() =>
            setSettings((prev) => ({ ...prev, enableDht: !prev.enableDht }))
          }
        >
          <span style={styles.autoStartLabel}>{t('settings.enableDht')}</span>
          <div
            style={{
              ...styles.autoSwitch,
              background: settings.enableDht ? '#238636' : '#30363d',
            }}
          >
            <div style={{ ...styles.autoSwitchDot, marginLeft: settings.enableDht ? 18 : 2 }} />
          </div>
        </div>
        <div style={styles.proxyDesc}>{t('settings.dhtDesc')}</div>
      </div>

      <div style={styles.field}>
        <label style={styles.label}>{t('settings.seedRatio')}</label>
        <input
          style={styles.input}
          type="number"
          min={0}
          max={10}
          step={0.5}
          value={settings.seedRatio}
          onChange={(e) =>
            setSettings((prev) => ({ ...prev, seedRatio: parseFloat(e.target.value) || 0 }))
          }
        />
      </div>

      <div style={styles.field}>
        <label style={styles.label}>{t('settings.seedTime')}</label>
        <input
          style={styles.input}
          type="number"
          min={0}
          max={1440}
          value={settings.seedTime}
          onChange={(e) =>
            setSettings((prev) => ({ ...prev, seedTime: parseInt(e.target.value, 10) || 0 }))
          }
        />
      </div>

      <div style={styles.separator} />

      <div style={styles.field}>
        <label style={styles.label}>{t('settings.proxy')}</label>
        <div style={styles.proxyRow}>
          <div style={{ ...styles.proxyBadge, background: proxyOn ? '#0d3320' : '#21262d', borderColor: proxyOn ? '#3fb950' : '#30363d' }}>
            <span style={{ ...styles.proxyDot, background: proxyOn ? '#3fb950' : '#484f58' }} />
            <span style={{ color: proxyOn ? '#3fb950' : '#8b949e' }}>
              {proxyOn ? t('settings.proxyRunning') : t('settings.proxyStopped')}
            </span>
          </div>
          <button
            style={{ ...styles.toggleBtn, background: proxyOn ? '#da3633' : '#238636' }}
            onClick={handleProxyToggle}
          >
            {proxyOn ? t('settings.proxyStop') : t('settings.proxyStart')}
          </button>
        </div>
        {proxyOn && (
          <div style={styles.proxyInfo}>
            {t('settings.proxyAddress')}: 127.0.0.1:{proxyPort}
          </div>
        )}
        <div style={styles.proxyDesc}>{t('settings.proxyDesc')}</div>

        <div
          style={styles.autoStartRow}
          onClick={() =>
            setSettings((prev) => ({ ...prev, proxyAutoStart: !prev.proxyAutoStart }))
          }
        >
          <span style={styles.autoStartLabel}>{t('settings.proxyAutoStart')}</span>
          <div
            style={{
              ...styles.autoSwitch,
              background: settings.proxyAutoStart ? '#238636' : '#30363d',
            }}
          >
            <div
              style={{
                ...styles.autoSwitchDot,
                marginLeft: settings.proxyAutoStart ? 18 : 2,
              }}
            />
          </div>
        </div>
      </div>

      <button style={styles.saveBtn} onClick={handleSave}>
        {saved ? t('settings.saved') : t('settings.save')}
      </button>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: { padding: 20, height: '100%' },
  title: { fontSize: 16, fontWeight: 600, color: '#c9d1d9', marginBottom: 20 },
  field: { marginBottom: 16 },
  label: { display: 'block', fontSize: 12, color: '#8b949e', marginBottom: 6 },
  input: {
    width: '100%', background: '#0d1117', border: '1px solid #30363d',
    borderRadius: 6, padding: '8px 12px', color: '#c9d1d9', fontSize: 13, outline: 'none',
  },
  dirRow: { display: 'flex', gap: 8 },
  browseBtn: {
    background: '#21262d', border: '1px solid #30363d', color: '#c9d1d9',
    fontSize: 13, padding: '8px 14px', borderRadius: 6, cursor: 'pointer', whiteSpace: 'nowrap',
  },
  separator: { height: 1, background: '#21262d', margin: '20px 0' },
  proxyRow: { display: 'flex', alignItems: 'center', gap: 10, justifyContent: 'space-between' },
  proxyBadge: {
    display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px',
    borderRadius: 6, border: '1px solid #30363d', fontSize: 12,
  },
  proxyDot: { width: 8, height: 8, borderRadius: '50%' },
  toggleBtn: {
    border: 'none', borderRadius: 6, padding: '6px 16px',
    color: '#ffffff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
  },
  proxyInfo: { fontSize: 11, color: '#58a6ff', marginTop: 8 },
  proxyDesc: { fontSize: 11, color: '#8b949e', marginTop: 6, lineHeight: 1.5 },
  autoStartRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12, cursor: 'pointer' },
  autoStartLabel: { fontSize: 12, color: '#c9d1d9' },
  autoSwitch: {
    width: 38, height: 22, borderRadius: 11, transition: 'background 0.2s',
    display: 'flex', alignItems: 'center',
  },
  autoSwitchDot: {
    width: 18, height: 18, borderRadius: '50%', background: '#ffffff', transition: 'margin-left 0.2s',
  },
  saveBtn: {
    width: '100%', background: '#238636', color: '#ffffff', border: 'none',
    borderRadius: 6, padding: '10px 0', fontSize: 14, fontWeight: 600, cursor: 'pointer', marginTop: 8,
  },
};
