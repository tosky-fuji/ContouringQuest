@echo off
setlocal
chcp 65001 >nul

rem ============================================
rem  app_env.tar.gz ビルドスクリプト（開発者向け）
rem
rem  conda-pack を使って配布用の Python 環境を
rem  tar.gz にアーカイブする。
rem ============================================

set "ENV_NAME=contouring_pack"
set "PYTHON_VER=3.11"
set "OUTPUT=app_env.tar.gz"
set "ROOT=%~dp0"

echo [1/5] 既存の一時環境を削除 ...
conda deactivate 2>nul
conda env remove -n %ENV_NAME% -y 2>nul

echo [2/5] conda 環境を作成 (Python %PYTHON_VER%) ...
conda create -n %ENV_NAME% python=%PYTHON_VER% -y
if errorlevel 1 (
  echo [!] conda create に失敗しました。
  exit /b 1
)

echo [3/5] requirements.txt からパッケージをインストール ...
conda run -n %ENV_NAME% pip install -r "%ROOT%requirements.txt"
if errorlevel 1 (
  echo [!] pip install に失敗しました。
  exit /b 1
)

echo [4/5] conda-pack をインストール ...
conda install -n %ENV_NAME% -c conda-forge conda-pack -y
if errorlevel 1 (
  echo [!] conda-pack のインストールに失敗しました。
  exit /b 1
)

echo [5/5] %OUTPUT% を生成中 ...
conda run -n %ENV_NAME% conda-pack -n %ENV_NAME% -o "%ROOT%%OUTPUT%" --force
if errorlevel 1 (
  echo [!] conda-pack に失敗しました。
  exit /b 1
)

echo.
echo ============================================
echo  完了: %ROOT%%OUTPUT%
echo ============================================
echo.
echo  一時環境 %ENV_NAME% を削除する場合:
echo    conda env remove -n %ENV_NAME% -y
echo.

endlocal
