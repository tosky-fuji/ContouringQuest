@echo off
setlocal
chcp 65001 >nul

rem === 設定 ===
set "ENV_DIR=app_env"
set "ARCHIVE=app_env.tar.gz"
set "APP_NAME=Contouring Quest"
rem ===========

set "ROOT=%~dp0"

echo ============================================
echo   %APP_NAME% インストーラー
echo ============================================
echo.

rem --- 1. conda-pack 環境の展開 ---
echo [1/4] 環境を展開中 ...

if exist "%ROOT%%ENV_DIR%" (
  echo   既存の %ENV_DIR% を削除しています ...
  rmdir /s /q "%ROOT%%ENV_DIR%"
)

if not exist "%ROOT%%ARCHIVE%" (
  echo [!] %ARCHIVE% が見つかりません。
  echo [!] 配布パッケージに %ARCHIVE% を同梱してください。
  pause
  exit /b 1
)

mkdir "%ROOT%%ENV_DIR%" || (echo [!] mkdir failed & exit /b 1)

tar -xf "%ROOT%%ARCHIVE%" -C "%ROOT%%ENV_DIR%"
if errorlevel 1 (
  echo [!] tar failed. Trying 7za fallback...
  if exist "%ROOT%tools\7za.exe" (
    "%ROOT%tools\7za.exe" x -y "%ROOT%%ARCHIVE%" -o"%ROOT%"
    for %%T in ("%ROOT%*.tar") do (
      "%ROOT%tools\7za.exe" x -y "%%~fT" -o"%ROOT%%ENV_DIR%"
      del /q "%%~fT"
    )
  ) else (
    echo [!] tar も 7za も使えません。tools\7za.exe を置くか、手動で展開してください。
    exit /b 1
  )
)

echo [*] conda-unpack を実行中 ...
set "PY=%ROOT%%ENV_DIR%\python.exe"
if exist "%ROOT%%ENV_DIR%\Scripts\conda-unpack.exe" (
  "%ROOT%%ENV_DIR%\Scripts\conda-unpack.exe"
) else if exist "%ROOT%%ENV_DIR%\Scripts\conda-unpack" (
  "%PY%" "%ROOT%%ENV_DIR%\Scripts\conda-unpack"
) else (
  for /r "%ROOT%%ENV_DIR%" %%P in (conda-unpack.py) do (
    "%PY%" "%%~fP"
    goto :after_unpack
  )
  echo [!] conda-unpack が見つかりませんでした（続行は可能なことが多いです）
)
:after_unpack
echo   環境の展開が完了しました。
echo.

rem --- 2. ディレクトリ作成 ---
echo [2/4] ディレクトリを作成中 ...

if not exist "%ROOT%records" mkdir "%ROOT%records"
if not exist "%ROOT%records\csv" mkdir "%ROOT%records\csv"
if not exist "%ROOT%nifti" mkdir "%ROOT%nifti"

echo   records/  records/csv/  nifti/  を確認しました。
echo.

rem --- 3. デスクトップショートカット作成 ---
echo [3/4] ショートカットを作成中 ...

set "SHORTCUT=%USERPROFILE%\Desktop\%APP_NAME%.lnk"
set "VBS_TEMP=%TEMP%\create_shortcut_%RANDOM%.vbs"

(
  echo Set ws = CreateObject("WScript.Shell"^)
  echo Set sc = ws.CreateShortcut("%SHORTCUT%"^)
  echo sc.TargetPath = "%ROOT%run.bat"
  echo sc.WorkingDirectory = "%ROOT%"
  echo sc.Description = "%APP_NAME%"
  echo sc.WindowStyle = 7
  echo sc.Save
) > "%VBS_TEMP%"
cscript //nologo "%VBS_TEMP%"
del /q "%VBS_TEMP%" 2>nul

if exist "%SHORTCUT%" (
  echo   デスクトップにショートカットを作成しました。
) else (
  echo   [!] ショートカット作成に失敗しました。手動で run.bat のショートカットを作成してください。
)
echo.

rem --- 4. 完了メッセージ ---
echo [4/4] セットアップ完了
echo.
echo ============================================
echo   セットアップが完了しました！
echo ============================================
echo.
echo   起動方法:
echo     - デスクトップの「%APP_NAME%」ショートカット
echo     - または run.bat をダブルクリック
echo.

if not exist "%ROOT%nifti\*.nii.gz" (
  echo   [重要] NIfTI データの配置が必要です:
  echo     nifti/ フォルダに .nii.gz ファイルと
  echo     ラベル定義 .json ファイルを配置してください。
  echo     配置先: %ROOT%nifti\
  echo.
)

pause
endlocal
