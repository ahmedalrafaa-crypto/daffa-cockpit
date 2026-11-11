@echo off
cd /d "%~dp0"
echo Installing Musahhih Ahmed (needs internet once)...
py -3 -m venv .venv || goto :fail
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt || goto :fail
echo.
echo Done. Double-click run.bat to start the program.
pause
exit /b 0
:fail
echo.
echo Installation failed. Make sure Python 3.11+ is installed from python.org
pause
exit /b 1
