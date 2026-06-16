#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Agnes Smart Studio - 一键查询
#  运行 ./query.sh，自动查询最近未完成的视频任务
#  或传入 video_id 参数查询指定任务
#  ⚠ 必须使用 video_id，不要用 task_id
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -e
cd "$(dirname "$0")"

G='\033[92m'; Y='\033[93m'; R='\033[91m'; C='\033[96m'; D='\033[2m'; B='\033[1m'; X='\033[0m'

# ── 查找 Python ──────────────────────────────
PY=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY="$cmd"; break
    fi
done
if [ -z "$PY" ]; then
    echo -e "\n  ${R}[错误]${X} 未找到 Python"
    exit 1
fi

# ── 安装依赖（静默） ─────────────────────────
if ! $PY -c "import httpx, rich, dotenv" 2>/dev/null; then
    echo -e "  ${D}安装依赖中...${X}"
    $PY -m pip install -q -r requirements.txt 2>/dev/null || true
fi

# ── 执行查询 ─────────────────────────────────
# 无参数: 自动查找未完成任务 + --watch 轮询等待
if [ $# -eq 0 ]; then
    exec $PY query.py --watch 10
else
    exec $PY query.py "$@"
fi
