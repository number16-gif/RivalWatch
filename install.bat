@echo off
cd /d "%~dp0"
py -m venv .venv
if errorlevel 1 (echo Python 3.11+ not found & pause & exit /b 1)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (echo Installation error & pause & exit /b 1)
echo Installed! Run start_web.bat and start_worker.bat.
pause
