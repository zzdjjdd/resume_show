# -*- coding: utf-8 -*-
"""一键启动 Resume Agent（前端 + 后端同一个 FastAPI 服务）。

直接使用当前 Python 解释器，不创建虚拟环境。

用法：
    python run.py                 # 首次自动安装依赖，然后启动
    python run.py --port 9000     # 指定端口
    python run.py --host 127.0.0.1# 只允许本机访问（默认 0.0.0.0 对外可访问）
    python run.py --install       # 强制重新安装依赖后启动
    python run.py --no-install    # 跳过依赖安装直接启动

环境变量覆盖：HOST / PORT
云服务器部署（Linux）后台常驻示例：
    nohup python3 run.py > server.log 2>&1 &
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
REQUIREMENTS = BACKEND / "requirements.txt"

# 直接使用当前 Python 解释器，不创建虚拟环境
PY = sys.executable


def log(msg: str) -> None:
    print(f"[run] {msg}", flush=True)


def run(cmd: list, **kwargs) -> int:
    log("执行: " + " ".join(str(c) for c in cmd))
    return subprocess.call(cmd, **kwargs)


def install_deps(py: str, force: bool = False) -> None:
    marker = BACKEND / ".deps-installed"
    if not force and marker.exists():
        log("依赖已安装（如需重装：python run.py --install）")
        return
    log("安装依赖 requirements.txt ...")
    code = run([str(py), "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    if code != 0:
        log("⚠️ 依赖安装出现问题（可手动执行上面的 pip 命令查看原因），仍尝试启动...")
        return
    marker.write_text("ok", encoding="utf-8")
    log("依赖安装完成")


def main() -> None:
    args = sys.argv[1:]
    force_install = "--install" in args
    skip_install = "--no-install" in args

    host = os.environ.get("HOST", "0.0.0.0")
    port = os.environ.get("PORT", "8000")
    for i, a in enumerate(args):
        if a == "--host" and i + 1 < len(args):
            host = args[i + 1]
        if a == "--port" and i + 1 < len(args):
            port = args[i + 1]

    py = PY
    if not skip_install:
        install_deps(py, force=force_install)

    log(f"启动服务: http://{host}:{port}  （浏览器访问 http://服务器IP:{port}）")
    log("按 Ctrl+C 停止")
    try:
        code = run(
            [str(py), "-m", "uvicorn", "app.main:app",
             "--app-dir", str(BACKEND), "--host", host, "--port", port],
            cwd=str(BACKEND),
        )
        sys.exit(code)
    except KeyboardInterrupt:
        log("已停止")


if __name__ == "__main__":
    main()
