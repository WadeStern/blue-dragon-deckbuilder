@echo off
REM Launch the Blue Dragon Deck Builder.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH. Install Python 3.10+ from python.org and re-run.
  pause
  exit /b 1
)

REM Install dependencies on first run (quietly).
python -c "import flask, PIL" >nul 2>nul
if errorlevel 1 (
  echo Installing dependencies ^(first run^)...
  python -m pip install -r requirements.txt
)

python app.py
pause
