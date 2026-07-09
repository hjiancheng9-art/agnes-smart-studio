/**
 * 新烬龙V2 · Dashboard 控制面板
 * 轻量服务器，端口 4377（不冲突主应用 4366）
 * 运行: node dashboard.js
 * 打开: http://localhost:4377
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const { execSync, exec, spawn } = require('child_process');

// ============ CONFIG ============
const PORT = 4377;
const ROOT = path.resolve(__dirname);
const WORKSPACE = path.join(ROOT, 'artifacts', 'product-core-baseline', 'baseline-files');
const CONFIG_PATH = path.join(ROOT, 'config', 'cli-config.json');
const DATA_DIR = path.join(ROOT, 'data', 'project-files');
const COCKPIT_DIR = path.join(WORKSPACE, 'public', 'assets', 'cockpit');

let mainServerProcess = null;
let serverLogs = [];

function log(msg) {
  const t = new Date().toLocaleTimeString();
  const line = `[${t}] ${msg}`;
  serverLogs.unshift(line);
  if (serverLogs.length > 200) serverLogs.length = 200;
  console.log(line);
}

// ============ HELPERS ============
function readJSON(p) {
  try { return JSON.parse(fs.readFileSync(p, 'utf-8')); } catch { return null; }
}

function getConfig() {
  return readJSON(CONFIG_PATH) || { server: { port: 4366, host: '127.0.0.1' } };
}

function getProjectList() {
  if (!fs.existsSync(DATA_DIR)) return [];
  try {
    return fs.readdirSync(DATA_DIR).filter(f => {
      const p = path.join(DATA_DIR, f);
      return fs.statSync(p).isDirectory() && f.startsWith('project-') || f.startsWith('New-Project-');
    }).map(f => {
      const p = path.join(DATA_DIR, f);
      const projFile = path.join(p, 'artifact_archive', '05_project_files', 'project.json');
      const projMd = path.join(p, 'artifact_archive', '05_project_files', 'project.md');
      const projMp4 = path.join(p, 'artifact_archive', '05_project_files', 'project.mp4');
      let info = { id: f, name: f, type: 'unknown', updated: 'unknown' };
      if (fs.existsSync(projFile)) {
        try {
          const j = JSON.parse(fs.readFileSync(projFile, 'utf-8'));
          info.name = j.name || j.title || f;
          info.type = 'project';
        } catch {}
      } else if (fs.existsSync(projMd)) {
        info.name = f;
        info.type = 'document';
      } else if (fs.existsSync(projMp4)) {
        info.name = f;
        info.type = 'video';
      }
      const stat = fs.statSync(p);
      info.updated = stat.mtime.toISOString().split('T')[0];
      info.size = (stat.size / 1024).toFixed(0) + 'KB';
      return info;
    });
  } catch { return []; }
}

function getCockpitAssets() {
  if (!fs.existsSync(COCKPIT_DIR)) return [];
  try {
    return fs.readdirSync(COCKPIT_DIR).map(f => ({
      name: f,
      path: f,
      isDir: fs.statSync(path.join(COCKPIT_DIR, f)).isDirectory()
    }));
  } catch { return []; }
}

function getPackageInfo() {
  const p = path.join(WORKSPACE, 'package.json');
  return readJSON(p) || {};
}

function getNodeVersion() {
  try {
    return execSync('node --version', { encoding: 'utf-8', timeout: 3000 }).trim();
  } catch { return 'unknown'; }
}

function runCmd(cmd, cwd) {
  try {
    const r = execSync(cmd, { cwd: cwd || ROOT, encoding: 'utf-8', timeout: 15000, maxBuffer: 1024 * 1024 });
    return { success: true, output: r.trim().substring(0, 5000) };
  } catch (e) {
    return { success: false, output: (e.stdout || '') + '\n' + (e.stderr || e.message || '').substring(0, 5000) };
  }
}

// ============ MIME ============
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.md': 'text/markdown; charset=utf-8',
  '.mp4': 'video/mp4',
  '.zip': 'application/zip',
};

// ============ SERVER ============
const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const pathname = url.pathname;

  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  // === API Routes ===
  if (pathname.startsWith('/api/')) {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    try { handleAPI(req, res, url); }
    catch (e) {
      res.writeHead(500);
      res.end(JSON.stringify({ error: e.message }));
    }
    return;
  }

  // === Static Files ===
  let filePath = pathname === '/'
    ? path.join(__dirname, 'dashboard.html')
    : path.join(__dirname, pathname);

  // Try workspace public folder as fallback for assets
  if (!fs.existsSync(filePath)) {
    const alt = path.join(WORKSPACE, 'public', pathname);
    if (fs.existsSync(alt)) filePath = alt;
  }

  const ext = path.extname(filePath).toLowerCase();

  // Security: prevent directory traversal
  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(path.resolve(ROOT)) &&
      !resolved.startsWith(path.resolve(WORKSPACE))) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }

  if (!fs.existsSync(filePath)) {
    // SPA fallback: serve dashboard
    filePath = path.join(__dirname, 'dashboard.html');
  }

  const mime = MIME[ext] || 'application/octet-stream';
  res.writeHead(200, { 'Content-Type': mime });
  fs.createReadStream(filePath).pipe(res);
});

// ============ API HANDLER ============
function handleAPI(req, res, url) {
  const pathname = url.pathname;
  const params = Object.fromEntries(url.searchParams);

  switch (pathname) {
    // === System ===
    case '/api/status': {
      const config = getConfig();
      res.end(JSON.stringify({
        name: '新烬龙V2',
        version: getPackageInfo().version || '0.1.0',
        node: getNodeVersion(),
        port: PORT,
        mainPort: config.server.port,
        mainHost: config.server.host,
        mainRunning: mainServerProcess !== null && mainServerProcess.exitCode === null,
        workspace: WORKSPACE,
        root: ROOT,
        uptime: process.uptime(),
        memory: process.memoryUsage(),
        platform: process.platform,
      }));
      break;
    }

    case '/api/config': {
      res.end(JSON.stringify(getConfig(), null, 2));
      break;
    }

    case '/api/package': {
      res.end(JSON.stringify(getPackageInfo(), null, 2));
      break;
    }

    // === Projects ===
    case '/api/projects': {
      const projects = getProjectList();
      res.end(JSON.stringify({ total: projects.length, projects }));
      break;
    }

    // === Cockpit Assets ===
    case '/api/cockpit': {
      res.end(JSON.stringify(getCockpitAssets()));
      break;
    }

    // === Skills ===
    case '/api/skills': {
      const skillsDir = path.join(WORKSPACE, 'knowledge', 'skills');
      if (fs.existsSync(skillsDir)) {
        const files = fs.readdirSync(skillsDir).filter(f => f.endsWith('.md')).map(f => {
          const fullPath = path.join(skillsDir, f);
          const content = fs.readFileSync(fullPath, 'utf-8').substring(0, 500);
          const title = content.split('\n')[0]?.replace(/^#\s*/, '') || f;
          return { file: f, title, preview: content.substring(0, 100) };
        });
        res.end(JSON.stringify({ total: files.length, skills: files }));
      } else {
        res.end(JSON.stringify({ total: 0, skills: [] }));
      }
      break;
    }

    // === Logs ===
    case '/api/logs': {
      res.end(JSON.stringify({ logs: serverLogs.slice(0, 100) }));
      break;
    }

    // === NPM INSTALL ===
    case '/api/npm/install': {
      log('正在安装依赖...');
      const result = runCmd('npm install', WORKSPACE);
      log(result.success ? '依赖安装完成' : '依赖安装失败');
      res.end(JSON.stringify(result));
      break;
    }

    // === START MAIN SERVER ===
    case '/api/server/start': {
      if (mainServerProcess && mainServerProcess.exitCode === null) {
        res.end(JSON.stringify({ success: false, output: '主服务器已在运行中' }));
        break;
      }
      const config = getConfig();
      const serverPath = path.join(WORKSPACE, 'server.js');
      const mainPort = config.server.port;

      if (fs.existsSync(serverPath)) {
        log(`启动主服务器 (端口 ${mainPort})...`);
        mainServerProcess = spawn('node', ['server.js'], {
          cwd: WORKSPACE,
          stdio: ['ignore', 'pipe', 'pipe'],
          detached: false
        });
        mainServerProcess.stdout.on('data', d => log(`[主服务器] ${d.toString().trim()}`));
        mainServerProcess.stderr.on('data', d => log(`[主服务器] ${d.toString().trim()}`));
        mainServerProcess.on('exit', (code) => {
          log(`主服务器退出 (代码: ${code})`);
          mainServerProcess = null;
        });
        // Wait a moment
        setTimeout(() => {
          const alive = mainServerProcess && mainServerProcess.exitCode === null;
          res.end(JSON.stringify({
            success: alive,
            output: alive
              ? `主服务器已启动 → http://localhost:${mainPort}`
              : '启动失败，请检查 server.js'
          }));
        }, 1500);
      } else {
        // Fallback: use http-server
        log('server.js 不存在，使用 http-server 静态服务...');
        mainServerProcess = spawn('npx', ['http-server', 'public', '-p', String(mainPort), '-o'], {
          cwd: WORKSPACE,
          stdio: ['ignore', 'pipe', 'pipe'],
          shell: true
        });
        setTimeout(() => {
          const alive = mainServerProcess && mainServerProcess.exitCode === null;
          res.end(JSON.stringify({
            success: alive,
            output: alive
              ? `静态服务器已启动 → http://localhost:${mainPort}`
              : '启动失败'
          }));
        }, 2000);
      }
      break;
    }

    case '/api/server/stop': {
      if (mainServerProcess && mainServerProcess.exitCode === null) {
        mainServerProcess.kill('SIGTERM');
        setTimeout(() => {
          try { mainServerProcess.kill('SIGKILL'); } catch {}
        }, 3000);
        log('主服务器已停止');
        res.end(JSON.stringify({ success: true, output: '服务器已停止' }));
      } else {
        res.end(JSON.stringify({ success: false, output: '没有运行中的服务器' }));
      }
      break;
    }

    // === RUN QA ===
    case '/api/qa/run': {
      const testName = params.test || 'all';
      log(`运行 QA 测试: ${testName}`);
      let cmd;
      if (testName === 'all') cmd = 'npm test';
      else cmd = `npm run ${testName}`;
      const result = runCmd(cmd, WORKSPACE);
      log(`QA 测试完成: ${result.success ? '通过' : '失败'}`);
      res.end(JSON.stringify(result));
      break;
    }

    // === Skill Content ===
    case '/api/skill': {
      const name = params.name;
      if (!name) { res.end(JSON.stringify({ error: 'no name' })); break; }
      const p = path.join(WORKSPACE, 'knowledge', 'skills', name);
      if (fs.existsSync(p)) {
        const content = fs.readFileSync(p, 'utf-8');
        res.end(JSON.stringify({ name, content }));
      } else {
        res.end(JSON.stringify({ error: 'not found' }));
      }
      break;
    }

    // === Documentation ===
    case '/api/docs': {
      const p = path.join(WORKSPACE, 'Documentation.md');
      if (fs.existsSync(p)) {
        res.end(JSON.stringify({ content: fs.readFileSync(p, 'utf-8').substring(0, 10000) }));
      } else {
        res.end(JSON.stringify({ content: '暂无文档' }));
      }
      break;
    }

    default:
      res.writeHead(404);
      res.end(JSON.stringify({ error: 'unknown api' }));
  }
}

server.listen(PORT, '127.0.0.1', () => {
  console.log('');
  console.log('╔══════════════════════════════════════════╗');
  console.log('║   🔥 新烬龙V2 · Dashboard                ║');
  console.log('║   控制面板已启动                          ║');
  console.log('╠══════════════════════════════════════════╣');
  console.log(`║  本地: http://localhost:${PORT}               ║`);
  console.log('║  主应用端口: 4366                        ║');
  console.log('╚══════════════════════════════════════════╝');
  console.log('');
});
