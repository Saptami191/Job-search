@echo off
setlocal
cd /d "%~dp0"
echo ========================================================
echo     Running Daily AI Job Scout & Screening Routine
echo ========================================================

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please run:
    echo py -m venv .venv
    echo .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

.\.venv\Scripts\python.exe -m job_scout.cli daily

echo ========================================================
echo     Daily Routine Completed!
echo     Check output\ranked_jobs.xlsx and output\applications\
echo ========================================================
pause
