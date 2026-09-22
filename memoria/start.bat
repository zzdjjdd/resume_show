@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Memoria
echo ============================================================
echo   Memoria · 短期 + 长期记忆系统
echo   页面地址:  http://127.0.0.1:8000
echo   API 文档:  http://127.0.0.1:8000/docs
echo   关闭此窗口 或 按 Ctrl+C 停止服务
echo ============================================================
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 python，请先安装 Python 并加入 PATH。
  pause
  exit /b 1
)
rem 加载本地密钥与模型配置（secrets.bat 已被 gitignore，不会提交）
if exist secrets.bat call secrets.bat
start "" /min cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8000"
python -m uvicorn web.app:app --host 127.0.0.1 --port 8000
echo.
if errorlevel 1 (
  echo [启动失败] 端口可能被占用或缺少依赖。安装依赖:  pip install -e ".[web]"
) else (
  echo [服务已停止]
)
pause
