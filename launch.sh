#!/usr/bin/env bash
# Agnes Smart Studio 启动器 (macOS/Linux)

cd "$(dirname "$0")"

# 颜色
RED='\033[91m'
GREEN='\033[92m'
YELLOW='\033[93m'
CYAN='\033[96m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

# 检查 Python
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo -e "${RED}[错误]${RESET} 未找到 Python，请安装 Python 3.10+"
    exit 1
fi

echo -e "${GREEN}[OK]${RESET} Python: $($PYTHON --version 2>&1)"

# 检查 .env
if [ ! -f .env ]; then
    echo -e "${YELLOW}[提示]${RESET} 未找到 .env 文件"
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${GREEN}[完成]${RESET} 已从 .env.example 创建 .env"
        echo -e "${YELLOW}[提示]${RESET} 请编辑 .env 填入你的 AGNES_API_KEY"
        echo ""
        ${EDITOR:-nano} .env
    else
        echo -e "${RED}[错误]${RESET} 缺少 .env.example，请手动创建 .env"
        exit 1
    fi
fi

# 检查并安装依赖
$PYTHON -c "import httpx, rich, PIL, dotenv" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}[提示]${RESET} 正在安装依赖..."
    $PYTHON -m pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo -e "${RED}[错误]${RESET} 依赖安装失败"
        exit 1
    fi
fi

# 创建输出目录
mkdir -p output/images output/videos

# 启动
echo ""
echo -e "${BOLD}  Agnes Smart Studio 启动中...${RESET}"
echo ""

if [ $# -eq 0 ]; then
    $PYTHON launcher.py
else
    $PYTHON agnes_studio.py "$@"
fi
