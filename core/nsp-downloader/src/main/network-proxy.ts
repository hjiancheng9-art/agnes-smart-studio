import { execSync } from 'child_process';
import { config } from 'dotenv';
import path from 'path';

// Load environment variables
config();

interface ProxyConfig {
  enabled: boolean;
  url: string | null;
  type: 'system' | 'env' | 'none';
  method: 'http' | 'https' | 'socks5' | 'none';
  port?: number;
  host?: string;
}

let cachedSystemProxy: string | undefined;
let cachedProxyConfig: ProxyConfig | null = null;

/**
 * Get system proxy configuration from Windows Registry
 */
export function getSystemProxy(): string | undefined {
  if (cachedSystemProxy) {
    return cachedSystemProxy;
  }

  try {
    // Check if we can access registry
    const enableOut = execSync(
      'reg query "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" /v ProxyEnable 2>nul',
      { encoding: 'utf8', timeout: 2000 }
    );

    const enableMatch = enableOut.match(/0x([0-9a-fA-F]+)/);
    if (!enableMatch || parseInt(enableMatch[1], 16) === 0) {
      return undefined; // Proxy is disabled
    }

    const serverOut = execSync(
      'reg query "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings" /v ProxyServer 2>nul',
      { encoding: 'utf8', timeout: 2000 }
    );

    const serverMatch = serverOut.match(/ProxyServer\s+REG_SZ\s+(.+)/);
    if (!serverMatch) return undefined;

    let addr = serverMatch[1].trim();
    // System proxy format is "host:port" — prefix with http://
    if (!/^https?:\/\//i.test(addr)) addr = 'http://' + addr;

    cachedSystemProxy = addr;
    return addr;
  } catch (error) {
    console.error('[nsp] Failed to read system proxy:', error);
    return undefined;
  }
}

/**
 * Get proxy configuration from environment variables
 */
export function getEnvProxy(): string | undefined {
  // Check common proxy environment variables
  const proxyVars = [
    'HTTP_PROXY',
    'HTTPS_PROXY',
    'http_proxy',
    'https_proxy',
    'ALL_PROXY',
    'all_proxy',
  ];

  for (const varName of proxyVars) {
    const value = process.env[varName];
    if (value && value.trim()) {
      return value.trim();
    }
  }

  return undefined;
}

/**
 * Parse proxy URL and extract configuration
 */
export function parseProxyUrl(url: string): ProxyConfig | null {
  try {
    const urlObj = new URL(url);

    return {
      enabled: true,
      url: url,
      type: 'env',
      method: urlObj.protocol.replace(':', '') as 'http' | 'https' | 'socks5',
      port: urlObj.port ? parseInt(urlObj.port, 10) : undefined,
      host: urlObj.hostname,
    };
  } catch (error) {
    console.error('[nsp] Failed to parse proxy URL:', error);
    return null;
  }
}

/**
 * Get effective proxy configuration (highest priority)
 */
export function getEffectiveProxy(): string | undefined {
  // 1. Check environment variables first (highest priority)
  const envProxy = getEnvProxy();
  if (envProxy) {
    return envProxy;
  }

  // 2. Check system proxy (second priority)
  const systemProxy = getSystemProxy();
  if (systemProxy) {
    return systemProxy;
  }

  return undefined;
}

/**
 * Get detailed proxy configuration
 */
export function getProxyConfig(): ProxyConfig {
  if (cachedProxyConfig) {
    return cachedProxyConfig;
  }

  // Check environment variables first
  const envProxy = getEnvProxy();
  if (envProxy) {
    cachedProxyConfig = {
      enabled: true,
      url: envProxy,
      type: 'env',
      method: parseProxyUrl(envProxy)?.method || 'http',
      port: parseProxyUrl(envProxy)?.port,
      host: parseProxyUrl(envProxy)?.host,
    };
    return cachedProxyConfig;
  }

  // Check system proxy
  const systemProxy = getSystemProxy();
  if (systemProxy) {
    cachedProxyConfig = {
      enabled: true,
      url: systemProxy,
      type: 'system',
      method: parseProxyUrl(systemProxy)?.method || 'http',
      port: parseProxyUrl(systemProxy)?.port,
      host: parseProxyUrl(systemProxy)?.host,
    };
    return cachedProxyConfig;
  }

  // No proxy configured
  cachedProxyConfig = {
    enabled: false,
    url: null,
    type: 'none',
    method: 'none',
  };

  return cachedProxyConfig;
}

/**
 * Test if proxy is working
 */
export async function testProxy(url: string = 'https://www.google.com'): Promise<{
  success: boolean;
  latency?: number;
  error?: string;
}> {
  return new Promise((resolve) => {
    const http = require('http');
    const https = require('https');

    const startTime = Date.now();

    const mod = url.startsWith('https') ? https : http;
    const req = mod.get(url, {
      timeout: 10000,
      rejectUnauthorized: false,
    }, (resp) => {
      const latency = Date.now() - startTime;

      if (resp.statusCode === 200) {
        resolve({
          success: true,
          latency,
        });
      } else {
        resolve({
          success: false,
          error: `HTTP ${resp.statusCode}`,
        });
      }
    });

    req.on('error', (error) => {
      resolve({
        success: false,
        error: error.message,
      });
    });

    req.on('timeout', () => {
      req.destroy();
      resolve({
        success: false,
        error: 'Connection timeout',
      });
    });

    req.setTimeout(10000);
  });
}

/**
 * Get proxy status for display
 */
export function getProxyStatus(): string {
  const config = getProxyConfig();

  if (!config.enabled) {
    return '未配置代理';
  }

  const typeText = {
    'system': '系统代理',
    'env': '环境变量代理',
    'none': '无代理',
  };

  return `${typeText[config.type]}: ${config.url || 'N/A'}`;
}

/**
 * Clear proxy cache
 */
export function clearProxyCache(): void {
  cachedSystemProxy = undefined;
  cachedProxyConfig = null;
}
