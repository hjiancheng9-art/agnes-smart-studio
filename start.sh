#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CRUX Studio - quick start
#  运行 ./start.sh 即可启动，自动检测环境并安装依赖
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -e
cd "$(dirname "$0")"

# 颜色
G='\033[92m'; Y='\033[93m'; R='\033[91m'; C='\033[96m'; D='\033[2m'; B='\033[1m'; X='\033[0m'

# ── 1. 查找 Python ──────────────────────────
PY=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY="$cmd"; break
    fi
done
if [ -z "$PY" ]; then
    echo -e "\n  ${R}[错误]${X} 未找到 Python，请安装 Python 3.10+"
    exit 1
fi

# ── 2. 检查 .env ────────────────────────────
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
    else
        printf "# CRUX AI API 配置\nCRUX_API_KEY=sk-your-api-key-here\nCRUX_BASE_URL=https://apihub.agnes-ai.com/v1\n" > .env
    fi
fi

# ── 3. 检查 API Key ─────────────────────────
if ! $PY -c "from core.config import SETTINGS; import sys; sys.exit(0 if SETTINGS.api_key and 'sk-your' not in SETTINGS.api_key else 1)" 2>/dev/null; then
    echo -e "\n  ${B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${X}"
    echo -e "   API Key 未配置"
    echo -e "  ${B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${X}\n"
    read -rp "   请输入 CRUX_API_KEY: " KEY
    if [ -n "$KEY" ]; then
        $PY -c "
from pathlib import Path
p = Path('.env')
lines = []
for l in p.read_text(encoding='utf-8').splitlines(True):
    if l.startswith('CRUX_API_KEY=') or l.startswith('AGNES_API_KEY='):
        lines.append('CRUX_API_KEY=$KEY\n')
    else:
        lines.append(l)
p.write_text(''.join(lines), encoding='utf-8')
"
    fi
fi

# ── 4. 安装依赖（静默） ────────────────────
if ! $PY -c "import httpx, rich, PIL, dotenv" 2>/dev/null; then
    echo -e "  ${D}安装依赖中...${X}"
    $PY -m pip install -q -r requirements.txt 2>/dev/null || true
fi

# ── 5. 创建输出目录 ─────────────────────────
mkdir -p output/images output/videos

# ── 6. 启动 ─────────────────────────────────
exec $PY crux_studio.py "$@"
