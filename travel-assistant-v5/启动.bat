@echo off
title AI 智行助手
cd /d "%~dp0"

echo ============================================
echo       AI 智行助手 - 一键启动
echo ============================================
echo.

REM ---------- 1. 检查 Python ----------
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python。
    echo        请先安装 Python 3.10 以上，并勾选 Add Python to PATH，
    echo        安装完成后重新双击本文件。
    echo.
    pause
    exit /b 1
)

REM ---------- 2. 检查或安装依赖 ----------
echo [1/2] 检查运行依赖 ...
python -c "import fastapi, uvicorn, httpx, yaml, pydantic" >nul 2>&1
if errorlevel 1 (
    echo       依赖缺失，正在自动安装，首次可能需 1-2 分钟 ...
    python -m pip install -r backend\requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
) else (
    echo       依赖已就绪。
)

REM ---------- 3. 启动服务 ----------
echo [2/2] 启动后端服务 ...
echo.
echo  ----------------------------------------
echo   启动成功后，浏览器访问:  http://localhost:8765/
echo   停止服务:  在本窗口按 Ctrl+C，或直接关闭窗口
echo  ----------------------------------------
echo.
python -m backend.app

echo.
echo 服务已退出。如有报错请截图反馈。
pause
