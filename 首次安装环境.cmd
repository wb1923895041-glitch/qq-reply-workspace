@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo 安装完成，请启动 QQ 工作台。
pause
exit /b 0
:fail
echo 安装失败，请检查 Python 与网络。
pause
exit /b 1
