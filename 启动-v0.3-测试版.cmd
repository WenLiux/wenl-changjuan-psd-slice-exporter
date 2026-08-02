@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
  echo 测试环境不存在，请先安装项目依赖。
  pause
  exit /b 1
)

if not exist "frontend\dist\index.html" (
  echo Web UI 尚未构建，请先在 frontend 目录运行 npm.cmd run build。
  pause
  exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" -m app.main
endlocal
