# PowerShell Automation Script for Daily Job Scout
# Can be executed manually or scheduled with Windows Task Scheduler

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ScriptDir

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Starting Daily Job Scout & Preparation Agent..." -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$PythonExe = Join-Path $ScriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Error "Virtual environment Python not found at: $PythonExe"
    exit 1
}

& $PythonExe -m job_scout.cli daily

Write-Host "========================================================" -ForegroundColor Green
Write-Host "  Daily run completed successfully!" -ForegroundColor Green
Write-Host "  Review report: $ScriptDir\output\ranked_jobs.xlsx" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
