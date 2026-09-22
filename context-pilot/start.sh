#!/bin/bash
# Context Pilot - 启动脚本 (Linux/Mac)
echo "========================================"
echo "  Context Pilot - 启动脚本"
echo "========================================"

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未检测到 Python3，请先安装 Python 3.8+"
    exit 1
fi

# 安装依赖
echo "[1/2] 正在检查/安装依赖..."
cd "$(dirname "$0")/backend"
pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet

# 启动服务
echo "[2/2] 启动服务..."
echo "========================================"
echo "  服务已启动: http://localhost:8000"
echo "  按 Ctrl+C 停止服务"
echo "========================================"
cd "$(dirname "$0")"
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
