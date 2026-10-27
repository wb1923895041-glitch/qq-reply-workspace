@echo off
chcp 65001 >nul
setlocal
set "RUNTIME="
for /d %%D in ("%~dp0output\napcat\NapCat.*.Shell") do if exist "%%~D\NapCatWinBootMain.exe" if exist "%%~D\QQ.exe" set "RUNTIME=%%~D"
if not defined RUNTIME (
  echo 未找到本地 NapCat 运行环境，请先根据使用说明准备。
  pause
  exit /b 1
)
pushd "%RUNTIME%"
echo 将启动独立的 QQ 机器人登录流程，请按窗口提示登录。
"%RUNTIME%\NapCatWinBootMain.exe"
popd
pause
