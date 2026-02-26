@echo off
setlocal
chcp 65001 >nul

rem === 設定（展開済み conda-pack 環境を使用） ===
set "ENV_DIR=app_env"
rem ===========

set "ROOT=%~dp0"
set "PY=%ROOT%%ENV_DIR%\python.exe"

if not exist "%PY%" (
  echo [!] Python が見つかりません: %PY%
  echo [!] 先に 0_install.bat を実行して環境を展開してください。
  pause
  exit /b 1
)

rem conda-pack 環境のパスを通す
set "PATH=%ROOT%%ENV_DIR%;%ROOT%%ENV_DIR%\Scripts;%ROOT%%ENV_DIR%\Library\bin;%PATH%"

echo [*] Launching Contouring Quest ...
cd /d "%ROOT%"
"%PY%" -m app

endlocal
