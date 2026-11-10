@echo off
setlocal EnableDelayedExpansion
REM ============================================================
REM BUILD.bat  —  NAB v3.0.0
REM Builds NAB.exe + nab_updater.exe via PyInstaller.
REM
REM NAB.exe is built from NAB_entry.pyw, which pulls in every
REM other nab_*.py module via their own "import nab_X" statements.
REM
REM Bundled INTO NAB.exe and dispatched by command-line flag
REM (see nab_app.py), NOT built as separate EXEs:
REM   image_ocr_finder.py  -->  NAB.exe --ocr-finder
REM   nab_pdf.py           -->  NAB.exe --pdf-bot       (NEW in 2.1.4)
REM
REM NEW MODULES IN 2.1.4 — must be present next to this file:
REM   nab_pdf.py        PDF Maker (was the standalone PDF.py)
REM   nab_ui_scale.py   DPI awareness + small-monitor window fitting
REM   nab_clip_scan.py  "which papers were clipped today" scanner
REM   nab_loading.py    reusable loading-spinner overlay for slow operations
REM
REM Required next to this file before running:
REM   NAB_entry.pyw, nab_constants.py, nab_telegram.py,
REM   nab_update.py, nab_access.py, nab_auth.py, nab_dialogs.py,
REM   nab_server.py, nab_bubble.py, nab_app.py, nab_updater.py,
REM   nab_pdf.py, nab_ui_scale.py, nab_clip_scan.py,
REM   image_ocr_finder.py, surgical_tools.py, nab_tracker.py,
REM   app_icon.ico, Logos\, nab-bot-498413-3ae32f0a2eec.json
REM ============================================================

echo.
echo ===============================================
echo   NAB BUILD  v2.1.4
echo ===============================================

REM ---- Pre-flight: fail early with a clear message instead of
REM ---- letting PyInstaller produce an EXE that crashes on launch.
set MISSING=0
set LOGOCOUNT=0
if exist "Logos" for %%L in ("Logos\*.png" "Logos\*.jpg" "Logos\*.jpeg" "Logos\*.webp") do set /a LOGOCOUNT+=1
if "%LOGOCOUNT%"=="0" (
    echo.
    echo  [WARNING] The Logos folder is EMPTY. Copy your newspaper logo files ^(Daily Star.png, TBS.png ...^) into
    echo            "%CD%\Logos" before building, or the EXE will have no logos.
    echo            ^(You can also add logos later in Settings ^> Papers.^)
    echo.
    pause
)
for %%F in (
    NAB_entry.pyw nab_constants.py nab_telegram.py nab_update.py
    nab_access.py nab_auth.py nab_dialogs.py nab_server.py
    nab_bubble.py nab_app.py nab_updater.py nab_pdf.py
    nab_ui_scale.py nab_clip_scan.py image_ocr_finder.py
    nab_loading.py nab_batch.py nab_batch_ui.py nab_subscriptions.py
    nab_tabreader.py nab_learn.py nab_recent.py
    nab_settings_sync.py nab_sync_ui.py nab_connections.py
    nab_session.py nab_meta.py nab_core.py nab_clipboard.py nab_engine.py nab_engine_host.py
    nab_headless_ops.py nab_web.py nab_main.py nab_winutil.py nab_tabserver.py nab_classic.py
    nab_tools.py nab_ai.py nab_riko.py nab_tool_ai.py nab_tool_shot.py nab_tool_pr.py nab_tool_hunt.py nab_tool_wa.py pr_rates_default.json riko_knowledge.md nhunt\bdfilter.py nhunt\engine.py nab_tool_tracker.py nab_tool_subs.py nab_tool_pdf.py nab_tool_search.py nab_tool_phone.py nab_tool_reports.py nab_accounts.py nab_archive.py nab_health.py nab_reports.py nab_schedule.py nab_agent.py nab_google.py nab_extras.py nab_mailer.py nab_mail_host.py
    nab_ui\intro.html nab_ui\catsearch.js nab_ui\tool_wa.js nab_ui\tool_hunt.js nab_ui\tool_tracker.js nab_ui\tool_tracker.css nab_ui\tool_mail.js nab_ui\tool_mail.css nab_ui\pet.html nab_ui\tool_pdf.js nab_ui\tool_pdf.css nab_ui\tool_search.js nab_ui\tool_search.css
    nab_ui\index.html nab_ui\app.css nab_ui\common.js nab_ui\clip.js nab_ui\main.js
    nab_ui\settings.js nab_ui\i18n.js nab_ui\overlay.html nab_ui\pet.html nab_ui\overlay.js nab_ui\extras.js nab_ui\mascot.js nab_ui\icons.js nab_ui\mascot_plus.js nab_ui\mascot_care.js nab_ui\mascot_fun.js nab_ui\mascot\skins.json
    surgical_tools.py nab_tracker.py
    NAB_TabReporter\manifest.json NAB_TabReporter\background.js
) do (
    if not exist "%%F" (
        echo   MISSING: %%F
        set MISSING=1
    )
)
if "!MISSING!"=="1" (
    echo.
    echo *** Required files are missing. Nothing was built. ***
    exit /b 1
)

REM ---- Version sanity check: the GitHub release tag must match
REM ---- APP_VERSION in nab_constants.py or auto-update silently
REM ---- does nothing on every PC.
echo.
echo Version in nab_constants.py:
findstr /C:"APP_VERSION" nab_constants.py

echo.
echo === Cleaning previous build ===
if exist "build" rmdir /S /Q "build"
if exist "dist"  rmdir /S /Q "dist"
if exist "NAB.spec"         del /Q "NAB.spec"
if exist "nab_updater.spec" del /Q "nab_updater.spec"

echo.
echo === Making sure the web-window packages are installed ===
pip install --quiet -r requirements.txt

echo.
echo === Building NAB.exe ===
REM The Google service-account key is bundled INSIDE the EXE so no PC needs any
REM setup. Put the key file next to this BUILD.bat before building. Either name works:
REM     nab-bot-498413-3ae32f0a2eec.json   or   nab_gdrive_creds.json
REM Never put the key in the GitHub repo or in a zip you share - only in the EXE.
set CRED_FLAG=
if exist "nab-bot-498413-3ae32f0a2eec.json" set "CRED_FLAG=--add-data nab-bot-498413-3ae32f0a2eec.json;."
if not defined CRED_FLAG if exist "nab_gdrive_creds.json" set "CRED_FLAG=--add-data nab_gdrive_creds.json;."
if not defined CRED_FLAG (
    echo.
    echo *** WARNING: no Google key file next to BUILD.bat - Drive/Sheets will NOT work in this build. ***
    echo     Put nab-bot-498413-3ae32f0a2eec.json or nab_gdrive_creds.json here and build again.
    pause
) else (
    echo Bundling the Google key into NAB.exe.
)

set ICON_FLAG=
set ICON_DATA=
if exist "app_icon.ico" set "ICON_FLAG=--icon=app_icon.ico"
if exist "app_icon.ico" set "ICON_DATA=--add-data app_icon.ico;."
set SPLASH_FLAG=
REM (native PyInstaller splash is not used: NAB_Launcher.exe shows the animated splash instead)
set BG_FLAG=
if exist "canvas_bg.png" set "BG_FLAG=--add-data canvas_bg.png;."

pyinstaller --onedir --noconfirm --windowed --name NAB ^
    %SPLASH_FLAG% ^
    %ICON_FLAG% ^
    --collect-all requests ^
    --collect-all urllib3 ^
    --collect-all pytesseract ^
    --collect-all reportlab ^
    --collect-all googleapiclient ^
    --collect-all gspread ^
    --collect-all google ^
    --collect-all webview ^
    --collect-all pythonnet ^
    --collect-all clr_loader ^
    --hidden-import nab_pdf ^
    --hidden-import nab_ui_scale ^
    --hidden-import nab_clip_scan ^
    --hidden-import nab_loading ^
    --hidden-import nab_batch ^
    --hidden-import nab_batch_ui ^
    --hidden-import nab_subscriptions ^
    --hidden-import nab_tabreader ^
    --hidden-import nab_learn ^
    --hidden-import nab_recent ^
    --hidden-import nab_settings_sync ^
    --hidden-import nab_sync_ui ^
    --hidden-import nab_connections ^
    --hidden-import nab_meta ^
    --hidden-import nab_core ^
    --hidden-import nab_clipboard ^
    --hidden-import nab_engine ^
    --hidden-import nab_engine_host ^
    --hidden-import nab_headless_ops ^
    --hidden-import nab_web ^
    --hidden-import nab_main ^
    --hidden-import nab_winutil ^
    --hidden-import nab_tabserver ^
    --hidden-import nab_classic ^
    --hidden-import nab_tools ^
    --hidden-import nab_tool_tracker ^
    --hidden-import nab_tool_subs ^
    --hidden-import nab_extras ^
    --hidden-import nab_session ^
    --hidden-import nab_mailer ^
    --hidden-import nab_mail_host ^
    --hidden-import smtplib ^
    --hidden-import nab_tool_pdf ^
    --hidden-import nab_tool_search ^
    --hidden-import nab_ai ^
    --hidden-import nab_riko ^
    --hidden-import nab_tool_ai ^
    --hidden-import nab_tool_shot ^
    --hidden-import nab_tool_pr ^
    --hidden-import nab_tool_hunt ^
    --hidden-import nab_tool_wa ^
    --hidden-import nab_tool_phone ^
    --hidden-import nab_tool_reports ^
    --hidden-import nab_accounts ^
    --hidden-import nab_archive ^
    --hidden-import nab_health ^
    --hidden-import nab_reports ^
    --hidden-import nab_schedule ^
    --hidden-import nab_agent ^
    --hidden-import nab_google ^
    --hidden-import openpyxl ^
    --collect-submodules nhunt ^
    --hidden-import gspread ^
    --hidden-import google.oauth2.service_account ^
    --hidden-import webview.platforms.edgechromium ^
    --hidden-import cv2 ^
    --hidden-import win32clipboard ^
    --hidden-import win32gui ^
    --hidden-import uiautomation ^
    --hidden-import image_ocr_finder ^
    --hidden-import websockets ^
    --hidden-import tkcalendar ^
    --hidden-import babel.numbers ^
    --exclude-module matplotlib --exclude-module pandas --exclude-module scipy --exclude-module IPython --exclude-module notebook ^
    --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 --exclude-module PySide6 --exclude-module wx ^
    --exclude-module tensorflow --exclude-module torch --exclude-module pytest --exclude-module sphinx --exclude-module onnxruntime ^
    --add-data "Logos;Logos" ^
    --add-data "nab_ui;nab_ui" ^
    --add-data "pr_rates_default.json;." ^
    --add-data "riko_knowledge.md;." ^
    --add-data "NAB_TabReporter;NAB_TabReporter" ^
    %ICON_DATA% ^
    %BG_FLAG% ^
    %CRED_FLAG% ^
    NAB_entry.pyw

if errorlevel 1 (
    echo.
    echo *** NAB.exe build FAILED — see errors above. Stopping. ***
    exit /b 1
)

echo.
echo === Building NAB_Launcher.exe ===
set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
set "LICON="
if exist "app_icon.ico" set "LICON=/win32icon:app_icon.ico"
"%CSC%" /nologo /target:winexe /optimize+ /out:dist\NAB_Launcher.exe %LICON% /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /resource:splash_launcher.png,splash.png /resource:splash_mascot.png,mascot.png NABLauncher.cs
if errorlevel 1 (
    echo *** NAB_Launcher.exe build FAILED - NAB.exe still works without it. ***
)

echo === Building nab_updater.exe ===
pyinstaller --onefile --noconsole --name nab_updater %ICON_FLAG% nab_updater.py

if errorlevel 1 (
    echo.
    echo *** nab_updater.exe build FAILED — see errors above. Stopping. ***
    exit /b 1
)

echo.
echo === Collecting build output ===
if exist "build_output" rmdir /S /Q "build_output"
mkdir "build_output\NAB"
xcopy /E /I /Y /Q "dist\NAB" "build_output\NAB" >nul
copy /Y "dist\nab_updater.exe" "build_output\NAB\nab_updater.exe" >nul
if exist "dist\NAB_Launcher.exe" copy /Y "dist\NAB_Launcher.exe" "build_output\NAB\NAB_Launcher.exe" >nul

echo.
echo === Making the update package NAB_win.zip ===
powershell -NoProfile -Command "Compress-Archive -Path 'build_output\NAB\*' -DestinationPath 'build_output\NAB_win.zip' -Force"
if errorlevel 1 echo *** zip failed - run this step by hand ***

echo.
echo === Making the installer NAB_Setup.exe (needs Inno Setup 6, optional) ===
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
    for /f %%v in ('python -c "import re;print(re.search(r'APP_VERSION\s*=\s*.([0-9.]+)',open('nab_constants.py').read()).group(1))"') do set "APPV=%%v"
    "%ISCC%" /Q /DAppVer=%APPV% NAB_Setup.iss
) else (
    echo Inno Setup 6 not found - skipping the installer. Get it free from jrsoftware.org, then run:  ISCC NAB_Setup.iss
)

echo.
echo ===============================================
echo   DONE - build_output\
echo ===============================================
dir /B "build_output"
echo.
echo NEXT:
echo   1. Test build_output\NAB\NAB_Launcher.exe on THIS PC before releasing.
echo   2. GitHub release tagged v^<APP_VERSION^> (must match APP_VERSION). Upload:
echo        NAB_win.zip     - what running copies download for auto-update
echo        NAB_Setup.exe   - for installing on a new PC
echo   3. Do NOT upload NAB.exe or nab_updater.exe on their own any more.
echo.
pause
