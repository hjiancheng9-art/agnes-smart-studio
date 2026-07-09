"""
🔥 新烬龙V2 · 主控脑
====================
CRUX Studio v6 入主接口 — 我是新烬龙的主控脑。
所有 AI 视频生产流水线操作从此经过此模块。
"""

import urllib.request
import urllib.error
import json
import time

BASE = 'http://127.0.0.1:4366'

def _api(method, path, body=None):
    """低层 API 调用"""
    url = f'{BASE}{path}'
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {'error': True, 'status': e.code, 'msg': e.read().decode('utf-8', errors='replace')}
    except Exception as e:
        return {'error': True, 'msg': str(e)}

# ── 驾驶舱状态 ──────────────────────────────────

def status():
    """新烬龙V2 状态"""
    return _api('GET', '/api/status')

# ── 项目管理 ─────────────────────────────────────

def list_projects():
    """列出所有项目"""
    data = _api('GET', '/api/projects')
    return data.get('projects', data) if isinstance(data, dict) else data

def create_project(name, description=''):
    """创建新项目"""
    return _api('POST', '/api/projects', {'name': name, 'description': description})

def get_project(pid):
    """获取项目详情"""
    return _api('GET', f'/api/projects/{pid}')

def update_project(pid, data):
    """更新项目"""
    return _api('PUT', f'/api/projects/{pid}', data)

def delete_project(pid):
    """删除项目"""
    return _api('DELETE', f'/api/projects/{pid}')

# ── 流水线操作 ───────────────────────────────────

def pipeline(pid, action, **kwargs):
    """执行流水线步骤

    步骤流程:
      set_intent      → 设定视频意图
      set_brief       → 设定创意简报
      set_storyboard  → 设定分镜（自动创建镜头）
      set_shot_image  → 生成镜头图 (需 shot_index)
      set_shot_video  → 生成镜头视频 (需 shot_index)
    """
    payload = {'action': action}
    payload.update(kwargs)
    return _api('POST', f'/api/projects/{pid}/pipeline', payload)

def set_intent(pid, intent):
    """Step 1: 设定视频意图"""
    return pipeline(pid, 'set_intent', intent=intent)

def set_brief(pid, brief):
    """Step 2: 设定创意简报"""
    return pipeline(pid, 'set_brief', brief=brief)

def set_storyboard(pid, storyboard):
    """Step 3: 设定分镜（自动创建镜头列表）
    
    支持:
      - 字符串: "镜头1: xxx\\n镜头2: xxx"
      - 列表: ["镜头1: xxx", "镜头2: xxx"]
      - 对象列表: [{"description": "...", "imagePrompt": "...", ...}]
    """
    if isinstance(storyboard, str):
        # 按换行分割成列表
        storyboard = [s.strip() for s in storyboard.replace('\\n', '\n').split('\n') if s.strip()]
    return pipeline(pid, 'set_storyboard', storyboard=storyboard)

def set_shot_image(pid, shot_index, prompt, style=None):
    """Step 4: 设定指定镜头的图像URL"""
    payload = {'shotIndex': shot_index, 'imageUrl': prompt}
    if style: payload['visualStyle'] = style
    return pipeline(pid, 'set_shot_image', **payload)

def set_shot_video(pid, shot_index, prompt=None):
    """Step 5: 设定指定镜头的视频URL"""
    payload = {'shotIndex': shot_index}
    if prompt: payload['videoUrl'] = prompt
    return pipeline(pid, 'set_shot_video', **payload)

# ── 高级自动化 ───────────────────────────────────

def auto_pipeline(name, intent, brief, storyboard, shots=None):
    """一键跑完整流水线：创建项目 → 意图 → 简报 → 分镜 → (图像 → 视频)*

    参数:
      name: 项目名称
      intent: 视频意图描述
      brief: 创意简报
      storyboard: 分镜描述（文字）
      shots: 可选，[(prompt, style?), ...] 自动生成图像

    返回: 项目ID
    """
    proj = create_project(name)
    if proj.get('error'):
        return proj
    pid = proj['id']
    
    print(f'[新烬龙] 项目创建: {pid}')
    print(f'[新烬龙] Step 1/3: 设定意图...')
    set_intent(pid, intent)
    print(f'[新烬龙] Step 2/3: 设定简报...')
    set_brief(pid, brief)
    print(f'[新烬龙] Step 3/3: 设定分镜...')
    set_storyboard(pid, storyboard)
    
    if shots:
        proj_data = get_project(pid)
        total_shots = len(proj_data.get('shots', shots))
        for i, shot in enumerate(shots):
            prompt = shot[0]
            style = shot[1] if len(shot) > 1 else None
            print(f'[新烬龙] 生成镜头 {i+1}/{total_shots} 图像...')
            set_shot_image(pid, i, prompt, style)
            print(f'[新烬龙] 生成镜头 {i+1}/{total_shots} 视频...')
            set_shot_video(pid, i)
    
    return pid

# ── 自检 ─────────────────────────────────────────

def health_check():
    """连通性测试 + 状态报告"""
    s = status()
    if s.get('error'):
        return {'alive': False, 'error': s.get('msg')}
    return {
        'alive': True,
        'name': s['name'],
        'version': s['version'],
        'port': s['port'],
        'projects': s['projects'],
        'uptime': s['uptime'],
        'memory': s['memory']
    }


if __name__ == '__main__':
    # 自检
    h = health_check()
    if h['alive']:
        print(f'🔥 新烬龙V2 v{h["version"]} · 已入主')
        print(f'   端口: {h["port"]}  |  项目: {h["projects"]} 个')
        print(f'   运行: {h["uptime"]:.1f}s  |  内存: {h["memory"]/1024/1024:.1f}MB')
    else:
        print(f'❌ 失联: {h.get("error")}')
