// ╔══════════════════════════════════════════════════╗
// ║  新烬龙V2 · 驾驶舱服务器 · Cockpit Server        ║
// ║  端口 4366 ·  AI 视频生产主引擎                   ║
// ╚══════════════════════════════════════════════════╝

const http = require('http');
const fs   = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const PORT   = 4366;
const ROOT   = __dirname;
const PUBLIC = path.join(ROOT, 'public');
const DATA   = path.join(ROOT, 'data', 'cockpit-projects');
const UPLOADS = path.join(PUBLIC, 'uploads');
if (!fs.existsSync(UPLOADS)) fs.mkdirSync(UPLOADS, { recursive: true });

if (!fs.existsSync(DATA)) fs.mkdirSync(DATA, { recursive: true });

// ═══════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════
const MIME = {
  '.html':'text/html; charset=utf-8', '.css':'text/css; charset=utf-8',
  '.js':'application/javascript; charset=utf-8', '.json':'application/json; charset=utf-8',
  '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg',
  '.webp':'image/webp', '.svg':'image/svg+xml', '.mp4':'video/mp4',
  '.md':'text/markdown; charset=utf-8', '.woff2':'font/woff2'
};

function json(res, data, code=200) {
  res.writeHead(code, {'Content-Type':'application/json; charset=utf-8'});
  res.end(JSON.stringify(data));
}
function err(res, msg, code=400) { json(res, {error:msg}, code); }

function readJSON(p) { try { return JSON.parse(fs.readFileSync(p,'utf-8')); } catch { return null; } }
function writeJSON(p, d) { fs.writeFileSync(p, JSON.stringify(d,null,2),'utf-8'); }

function listProjects() {
  if (!fs.existsSync(DATA)) return [];
  return fs.readdirSync(DATA)
    .filter(f => f.endsWith('.json'))
    .map(f => {
      const proj = readJSON(path.join(DATA, f));
      return { id: f.replace('.json',''), name: proj?.name || f, status: proj?.status || 'draft',
               updated: proj?.updated || '', description: proj?.description || '' };
    })
    .sort((a,b) => b.updated.localeCompare(a.updated));
}

function getProject(id) {
  const file = path.join(DATA, id + '.json');
  return fs.existsSync(file) ? readJSON(file) : null;
}
function saveProject(id, data) {
  data.updated = new Date().toISOString();
  writeJSON(path.join(DATA, id + '.json'), data);
}

function genId() { return 'proj_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2,7); }

// ═══════════════════════════════════════════
//  SERVER
// ═══════════════════════════════════════════
const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin','*');
  res.setHeader('Access-Control-Allow-Methods','GET,POST,PUT,DELETE,OPTIONS');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  const url = new URL(req.url, `http://localhost:${PORT}`);
  const p   = url.pathname;

  // === API ===
  if (p.startsWith('/api/')) { handleAPI(req, res, url); return; }

  // === Static ===
  let file = p === '/' ? path.join(PUBLIC, 'index.html') : path.join(ROOT, p);
  if (!fs.existsSync(file)) file = path.join(PUBLIC, 'index.html');
  const ext = path.extname(file).toLowerCase();
  res.writeHead(200, {'Content-Type': MIME[ext] || 'application/octet-stream'});
  fs.createReadStream(file).pipe(res);
});

function handleAPI(req, res, url) {
  const p  = url.pathname;
  const q  = Object.fromEntries(url.searchParams);

  // Collect body if POST/PUT
  let body = '';
  req.on('data', d => body += d);
  req.on('end', () => {
    let data = {};
    try { if (body) data = JSON.parse(body); } catch(e) {}

    switch (true) {

      // ── STATUS ──
      case p === '/api/status':
        json(res, { name:'新烬龙V2 驾驶舱', version:'3.0.0', port:PORT, projects: listProjects().length,
                     uptime: process.uptime(), node: process.version, memory: process.memoryUsage().rss });
        break;

      // ── PROJECTS CRUD ──
      case p === '/api/projects' && req.method === 'GET':
        json(res, { projects: listProjects() });
        break;

      case p === '/api/projects' && req.method === 'POST':
        const nid = genId();
        const proj = {
          id: nid, name: data.name || '未命名项目', description: data.description || '',
          status: 'draft', created: new Date().toISOString(), updated: new Date().toISOString(),
          pipeline: {
            stage: 'intent',           // intent → brief → storyboard → visual → generate → qc → deliver
            intent: null,              // 用户原始需求
            brief: null,               // 制作简报
            storyboard: [],            // 分镜列表
            shots: [],                 // 每镜详情 { index, description, imagePrompt, imageUrl, videoUrl, motion, status }
            deliverables: [],          // 最终产物
          }
        };
        saveProject(nid, proj);
        json(res, proj, 201);
        break;

      case p.startsWith('/api/projects/') && req.method === 'GET':
        const gid = p.split('/').pop();
        const gproj = getProject(gid);
        gproj ? json(res, gproj) : err(res, '项目不存在', 404);
        break;

      case p.startsWith('/api/projects/') && req.method === 'PUT':
        const pid = p.split('/').pop();
        const existing = getProject(pid);
        if (!existing) return err(res, '项目不存在', 404);
        Object.assign(existing, data);
        saveProject(pid, existing);
        json(res, existing);
        break;

      case p.startsWith('/api/projects/') && req.method === 'DELETE':
        const did = p.split('/').pop();
        const df = path.join(DATA, did + '.json');
        if (fs.existsSync(df)) { fs.unlinkSync(df); json(res, {deleted:did}); }
        else err(res, '项目不存在', 404);
        break;

      // ── PIPELINE STEPS ──
      case p.startsWith('/api/projects/') && p.endsWith('/pipeline') && req.method === 'POST':
        const qid = p.split('/')[3];
        const qproj = getProject(qid);
        if (!qproj) return err(res, '项目不存在', 404);

        const action = data.action; // set_intent | set_brief | set_storyboard | set_shot | next_stage
        switch (action) {
          case 'set_intent':
            qproj.pipeline.intent = data.intent;
            qproj.pipeline.stage = 'brief';
            qproj.status = 'planning';
            break;
          case 'set_brief':
            qproj.pipeline.brief = data.brief;
            qproj.pipeline.stage = 'storyboard';
            break;
          case 'set_storyboard':
            qproj.pipeline.storyboard = data.storyboard;
            // Create shots from storyboard (support both string and array)
            const rawShots = Array.isArray(data.storyboard)
              ? data.storyboard
              : String(data.storyboard).split(/\n+/).map(s => s.trim()).filter(Boolean);
            qproj.pipeline.shots = rawShots.map((s,i) => ({
              index: i, description: s.description || s, imagePrompt: s.imagePrompt || '',
              visualStyle: s.visualStyle || '', motion: s.motion || '',
              status: 'pending', imageUrl: null, videoUrl: null
            }));
            qproj.pipeline.stage = 'visual';
            qproj.status = 'producing';
            break;
          case 'set_shot_image':
            const si = data.shotIndex;
            if (si >= 0 && si < qproj.pipeline.shots.length) {
              qproj.pipeline.shots[si].imageUrl  = data.imageUrl;
              qproj.pipeline.shots[si].imagePrompt = data.prompt;
              qproj.pipeline.shots[si].status = 'image_done';
            }
            break;
          case 'set_shot_video':
            const vi = data.shotIndex;
            if (vi >= 0 && vi < qproj.pipeline.shots.length) {
              qproj.pipeline.shots[vi].videoUrl = data.videoUrl;
              qproj.pipeline.shots[vi].status    = 'video_done';
            }
            break;
          case 'next_stage':
            const stages = ['intent','brief','storyboard','visual','generate','qc','deliver'];
            const ci = stages.indexOf(qproj.pipeline.stage);
            if (ci < stages.length - 1) qproj.pipeline.stage = stages[ci + 1];
            if (qproj.pipeline.stage === 'deliver') qproj.status = 'completed';
            break;
          default:
            return err(res, '未知操作: ' + action);
        }
        saveProject(qid, qproj);
        json(res, qproj);
        break;

      // ── UPLOAD ──
      case p === '/api/upload' && req.method === 'POST':
        if (!data.filename || !data.data) return err(res, '缺少文件数据', 400);
        const ext = path.extname(data.filename) || '.bin';
        const fname = Date.now() + '-' + Math.random().toString(36).slice(2,8) + ext;
        const fpath = path.join(UPLOADS, fname);
        try {
          const buf = Buffer.from(data.data, 'base64');
          fs.writeFileSync(fpath, buf);
          json(res, { url: '/uploads/' + fname, size: buf.length, name: data.filename });
        } catch(e) { err(res, '写入失败: ' + e.message, 500); }
        break;

      // ── COCKPIT ASSETS ──
      case p === '/api/assets/cockpit':
        const cockpitDir = path.join(PUBLIC, 'assets', 'cockpit');
        if (fs.existsSync(cockpitDir)) {
          const files = fs.readdirSync(cockpitDir).filter(f => /\.(webp|png|jpg)$/i.test(f));
          json(res, { files: files.map(f => ({ name:f, url:'/assets/cockpit/'+f })) });
        } else { json(res, { files: [] }); }
        break;

      default:
        err(res, '未知 API: ' + p, 404);
    }
  });
}

server.listen(PORT, '127.0.0.1', () => {
  console.log('');
  console.log('╔══════════════════════════════════════════╗');
  console.log('║  🔥 新烬龙V2 · 驾驶舱                    ║');
  console.log('║  http://localhost:' + PORT + '                      ║');
  console.log('╚══════════════════════════════════════════╝');
  console.log('');
});
