#!/usr/bin/env pwsh
# Stop script for Visualizer Agent project
# Stops all running backend and frontend processes

param(
    [switch]$Quiet,
    [switch]$Force
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $ProjectRoot "scripts\logs"
$PidFile = Join-Path $LogDir "processes.pid"

# Check if anything is running first
$anythingRunning = $false
if (Test-Path $PidFile) {
    $pids = Get-Content $PidFile -ErrorAction SilentlyContinue
    foreach ($line in $pids) {
        if ($line -match "backend=(\d+)" -or $line -match "frontend=(\d+)") {
            $processId = $matches[1]
            $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($proc) {
                $anythingRunning = $true
                break
            }
        }
    }
}

# Also check for uvicorn/node processes
if (-not $anythingRunning) {
    $uvicornProcs = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*uvicorn*" -and $_.CommandLine -like "*app.main*"
    }
    $nodeProcs = Get-Process -Name "node" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*vite*"
    }
    if ($uvicornProcs -or $nodeProcs) {
        $anythingRunning = $true
    }
}

if (-not $anythingRunning) {
    if (-not $Quiet) {
        Write-Host "No services are currently running." -ForegroundColor Yellow
    }
    exit 0
}

$stopped = $false

# Stop processes from PID file
if (Test-Path $PidFile) {
    $pids = Get-Content $PidFile -ErrorAction SilentlyContinue
    
    foreach ($line in $pids) {
        if ($line -match "backend=(\d+)") {
            $processId = $matches[1]
            try {
                $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
                if ($proc) {
                    Stop-Process -Id $processId -Force:$Force -ErrorAction SilentlyContinue
                    if (-not $Quiet) {
                        Write-Host "Stopped backend process (PID: $processId)" -ForegroundColor Green
                    }
                    $stopped = $true
                }
            } catch {
                Write-Warning "Failed to stop backend process (PID: $processId): $_"
            }
        }
        if ($line -match "frontend=(\d+)") {
            $processId = $matches[1]
            try {
                $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
                if ($proc) {
                    Stop-Process -Id $processId -Force:$Force -ErrorAction SilentlyContinue
                    if (-not $Quiet) {
                        Write-Host "Stopped frontend process (PID: $processId)" -ForegroundColor Green
                    }
                    $stopped = $true
                }
            } catch {
                Write-Warning "Failed to stop frontend process (PID: $processId): $_"
            }
        }
    }
    
    # Remove PID file
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

# Also try to find and stop any remaining uvicorn or node/vite processes related to our project
if (-not $stopped) {
    # Stop uvicorn processes in backend directory
    $uvicornProcs = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*uvicorn*" -and $_.CommandLine -like "*app.main*"
    }
    
    foreach ($proc in $uvicornProcs) {
        try {
            Stop-Process -Id $proc.Id -Force:$Force -ErrorAction SilentlyContinue
            if (-not $Quiet) {
                Write-Host "Stopped uvicorn process (PID: $($proc.Id))" -ForegroundColor Green
            }
            $stopped = $true
        } catch {
            Write-Warning "Failed to stop uvicorn process (PID: $($proc.Id)): $_"
        }
    }
    
    # Stop node processes running vite in frontend directory
    $nodeProcs = Get-Process -Name "node" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*vite*"
    }
    
    foreach ($proc in $nodeProcs) {
        try {
            Stop-Process -Id $proc.Id -Force:$Force -ErrorAction SilentlyContinue
            if (-not $Quiet) {
                Write-Host "Stopped frontend/vite process (PID: $($proc.Id))" -ForegroundColor Green
            }
            $stopped = $true
        } catch {
            Write-Warning "Failed to stop node process (PID: $($proc.Id)): $_"
        }
    }
}

if (-not $Quiet) {
    if ($stopped) {
        Write-Host ""
        Write-Host "All services stopped." -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "No running services found." -ForegroundColor Yellow
    }
}

# Return exit code
if ($stopped -or $Quiet) {
    exit 0
} else {
    exit 1
}
