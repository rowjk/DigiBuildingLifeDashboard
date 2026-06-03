@echo off
title Life Dashboard Launcher
cd /d "%~dp0"

echo ===================================================
echo   Life Dashboard Launcher
echo ===================================================
echo.

echo [Step 1/2] Checking local SQLite database...
if not exist "dashboard.db" (
    echo Database file not found. Initializing and seeding database...
    python database.py
) else (
    echo Database file exists. [OK]
)
echo.

echo [Step 2/2] Starting Streamlit dashboard service...
echo ===================================================
echo  The web app will automatically open in your browser.
echo  To STOP the service, close this command window.
echo ===================================================
echo.

streamlit run app.py

pause
