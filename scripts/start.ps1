#!/usr/bin/env pwsh
# Start script for Visualizer Agent project
# Starts both backend (uvicorn) and frontend (vite) in separate background processes

param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [string]$BackendPort = "8000",
    [string]$FrontendPort = "5173",
    [switch]$Force
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "apps\backend"
$FrontendDir = Join-Path $ProjectRoot "apps\frontend"
$LogDir = Join-Path $ProjectRoot "scripts\logs"

# Create logs directory if it doesn't exist
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$BackendLog = Join-Path $LogDir "backend.log"
$FrontendLog = Join-Path $LogDir "frontend.log"
$PidFile = Join-Path $LogDir "processes.pid"

# Check if already running
$alreadyRunning = $false
if (Test-Path $PidFile) {
    $pids = Get-Content $PidFile -ErrorAction SilentlyContinue
    foreach ($line in $pids) {
        if ($line -match "backend=(\d+)" -or $line -match "frontend=(\d+)") {
            $processId = $matches[1]
            $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($proc) {
                $alreadyRunning = $true
                break
            }
        }
    }
}

if ($alreadyRunning -and -not $Force) {
    Write-Host "Services are already running!" -ForegroundColor Yellow
    Write-Host "Use -Force to restart anyway, or use check.ps1 to see status." -ForegroundColor Gray
    exit 1
}

# Kill any existing processes first if forcing restart
if ($alreadyRunning -and $Force) {
    Write-Host "Restarting services..." -ForegroundColor Yellow
    & "$PSScriptRoot\stop.ps1" -Quiet
} else {
    Write-Host "Starting services..." -ForegroundColor Green
}

$processes = @()

# Start Backend
if (-not $FrontendOnly) {
    Write-Host "Starting backend on port $BackendPort..." -ForegroundColor Green
    
    # Check if conda environment exists
    $condaEnv = "ml"
    $condaCheck = conda env list | Select-String $condaEnv
    
    if ($condaCheck) {
        $backendCmd = "conda activate $condaEnv; cd '$BackendDir'; uvicorn app.main:app --host 0.0.0.0 --port $BackendPort"
    } else {
        Write-Warning "Conda environment '$condaEnv' not found. Trying without conda..."
        $backendCmd = "cd '$BackendDir'; uvicorn app.main:app --host 0.0.0.0 --port $BackendPort"
    }
    
    $backendJob = Start-Job -ScriptBlock {
        param($cmd, $logFile)
        Invoke-Expression $cmd 2>&1 | Tee-Object -FilePath $logFile -Append
    } -ArgumentList $backendCmd, $BackendLog
    
    $processes += "backend=$($backendJob.Id)"
    Start-Sleep -Seconds 2
}

# Start Frontend
if (-not $BackendOnly) {
    Write-Host "Starting frontend on port $FrontendPort..." -ForegroundColor Green
    
    # Check if bun or npm is available
    $packageManager = "npm"
    if (Get-Command bun -ErrorAction SilentlyContinue) {
        $packageManager = "bun"
    }
    
    $frontendCmd = "cd '$FrontendDir'; $packageManager run dev -- --port $FrontendPort"
    
    $frontendJob = Start-Job -ScriptBlock {
        param($cmd, $logFile)
        Invoke-Expression $cmd 2>&1 | Tee-Object -FilePath $logFile -Append
    } -ArgumentList $frontendCmd, $FrontendLog
    
    $processes += "frontend=$($frontendJob.Id)"
    Start-Sleep -Seconds 2
}

# Save PIDs to file
$processes | Out-File -FilePath $PidFile -Encoding UTF8

Write-Host ""
Write-Host "Project started successfully!" -ForegroundColor Green
Write-Host "Backend: http://localhost:$BackendPort" -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:$FrontendPort" -ForegroundColor Cyan
Write-Host ""
Write-Host "Logs:" -ForegroundColor Yellow
Write-Host "  Backend:  $BackendLog" -ForegroundColor Gray
Write-Host "  Frontend: $FrontendLog" -ForegroundColor Gray
Write-Host ""
Write-Host "Use 'check.ps1' to verify status" -ForegroundColor Yellow
Write-Host "Use 'stop.ps1' to stop all services" -ForegroundColor Yellow
