@echo off
REM Start the Deepr worker on Windows

echo Starting Deepr Worker...
python "%~dp0start-worker.py" %*
