#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CRUX Studio v5.0 — 引导脚本 (Linux / macOS)
#  首次运行自动安装依赖，之后直接启动。
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
set -e
cd "$(dirname "$0")"

G='\033[92m'; Y='\033[93m'; R='\033[91m'; D='\033[2m'; X='\033[0m'

# ── 1. 找 Python ──────────────────────────
PY=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY="$cmd"; break
    fi
done
if [ -z "$PY" ]; then
    echo -e "\n  ${R}[✖]${X} 未找到 Python，请安装 Python 3.10+"
    exit 1
fi

# ── 2. 安装依赖（静默）──────────────────────
if ! $PY -c "import httpx, rich, dotenv" 2>/dev/null; then
    echo -e "  ${D}安装依赖中...${X}"
    $PY -m pip install -q httpx rich python-dotenv nest-asyncio Pillow pyyaml prompt_toolkit playwright edge-tts || true
fi

# ── 3. 启动 ─────────────────────────────────
echo -e "  ${G}[✔]${X} 启动 CRUX Studio..."
echo
exec $PY crux_studio.py "$@"
