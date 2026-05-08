#!/usr/bin/env pwsh
# Check script for Visualizer Agent project
# Verifies if backend and frontend are running and healthy

param(
    [switch]$Quiet,
    [string]$BackendPort = "8000",
    [string]$FrontendPort = "5173",
    [int]$TimeoutSeconds = 5
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot "scripts\logs"
$BackendLog = Join-Path $LogDir "backend.log"
$FrontendLog = Join-Path $LogDir "frontend.log"
$PidFile = Join-Path $LogDir "processes.pid"

$healthy = $true
$results = @()

# Check Backend Health
try {
    $response = Invoke-WebRequest -Uri "http://localhost:$BackendPort/health" -UseBasicParsing -Method GET -TimeoutSec $TimeoutSeconds -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        $backendStatus = "Healthy"
    } else {
        $backendStatus = "Unhealthy (HTTP $($response.StatusCode))"
        $healthy = $false
    }
} catch {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:$BackendPort/docs" -UseBasicParsing -Method GET -TimeoutSec $TimeoutSeconds -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $backendStatus = "Running (API docs available)"
        } else {
            $backendStatus = "Unresponsive"
            $healthy = $false
        }
    } catch {
        $backendStatus = "Not reachable"
        $healthy = $false
    }
}

# Check if backend process is running
$backendRunning = $false
if (Test-Path $PidFile) {
    $pids = Get-Content $PidFile -ErrorAction SilentlyContinue
    foreach ($line in $pids) {
        if ($line -match "backend=(\d+)") {
            $processId = $matches[1]
            $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($proc) {
                $backendRunning = $true
            }
        }
    }
}

$results += [PSCustomObject]@{
    Service = "Backend"
    Port = $BackendPort
    Running = if ($backendRunning) { "Yes" } else { "No" }
    Healthy = $backendStatus
}

# Check Frontend Health
try {
    $response = Invoke-WebRequest -Uri "http://localhost:$FrontendPort" -UseBasicParsing -Method GET -TimeoutSec $TimeoutSeconds -ErrorAction SilentlyContinue
    if ($response.StatusCode -eq 200) {
        $frontendStatus = "Healthy"
    } else {
        $frontendStatus = "Unhealthy (HTTP $($response.StatusCode))"
        $healthy = $false
    }
} catch {
    $frontendStatus = "Not reachable"
    $healthy = $false
}

# Check if frontend process is running
$frontendRunning = $false
if (Test-Path $PidFile) {
    $pids = Get-Content $PidFile -ErrorAction SilentlyContinue
    foreach ($line in $pids) {
        if ($line -match "frontend=(\d+)") {
            $processId = $matches[1]
            $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($proc) {
                $frontendRunning = $true
            }
        }
    }
}

$results += [PSCustomObject]@{
    Service = "Frontend"
    Port = $FrontendPort
    Running = if ($frontendRunning) { "Yes" } else { "No" }
    Healthy = $frontendStatus
}

# Output results
if (-not $Quiet) {
    Write-Host ""
    Write-Host "Visualizer Agent Status Check" -ForegroundColor Cyan
    Write-Host "=============================" -ForegroundColor Cyan
    
    foreach ($result in $results) {
        $color = if ($result.Healthy -match "Healthy|Running") { "Green" } else { "Red" }
        Write-Host ""
        Write-Host "$($result.Service):" -ForegroundColor Yellow
        Write-Host "  Port:     $($result.Port)" -ForegroundColor Gray
        Write-Host "  Running:  $($result.Running)" -ForegroundColor Gray
        Write-Host "  Status:   $($result.Healthy)" -ForegroundColor $color
    }
    
    Write-Host ""
    Write-Host "Log Files:" -ForegroundColor Yellow
    Write-Host "  Backend:  $BackendLog" -ForegroundColor Gray
    Write-Host "  Frontend: $FrontendLog" -ForegroundColor Gray
    
    if ($healthy) {
        Write-Host ""
        Write-Host "All services are healthy!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "Some services are not healthy." -ForegroundColor Red
        Write-Host "Check logs for details." -ForegroundColor Yellow
    }
}

# Return exit code
if ($healthy) {
    exit 0
} else {
    exit 1
}
