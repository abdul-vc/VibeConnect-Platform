<#
.SYNOPSIS
    VibeConnect Platform One-Command Development Launcher.
.DESCRIPTION
    Starts the Django backend on port 8100 and the Vite frontend on port 6392 in separate,
    clearly titled PowerShell windows. Performs port pre-flight checks, verifies existing
    processes, polls readiness endpoints, and outputs canonical URLs.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$PythonExe = Join-Path $BackendDir "venv\Scripts\python.exe"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "             VibeConnect Local Development Environment Launcher       " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Project Root : $ProjectRoot"
Write-Host "Backend Dir  : $BackendDir"
Write-Host "Frontend Dir : $FrontendDir"
Write-Host ""

# 1. Verify Virtual Environment
if (-not (Test-Path -Path $PythonExe)) {
    Write-Error "ERROR: Python virtual environment not found at '$PythonExe'. Please configure the backend venv first."
    exit 1
}

# 2. Helper functions to test endpoints
function Test-BackendHealth {
    param([string]$Url = "http://127.0.0.1:8100/api/v1/health/")
    try {
        $resp = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 2 -ErrorAction Stop
        if ($resp.service -eq "vibeconnect_backend" -and $resp.status -eq "healthy") {
            return $true
        }
    } catch {
        return $false
    }
    return $false
}

function Test-FrontendHealth {
    param([string]$Url = "http://localhost:6392/")
    try {
        $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($resp.StatusCode -eq 200) {
            return $true
        }
    } catch {
        return $false
    }
    return $false
}

# 3. Check Port 8100 (Backend)
Write-Host "[1/4] Checking Port 8100 (Backend)..." -ForegroundColor Yellow
$BackendAlreadyRunning = $false
$Port8100Conns = Get-NetTCPConnection -LocalPort 8100 -State Listen -ErrorAction SilentlyContinue

if ($Port8100Conns) {
    if (Test-BackendHealth) {
        Write-Host "  -> Port 8100 is already running VibeConnect Backend. Skipping launch." -ForegroundColor Green
        $BackendAlreadyRunning = $true
    } else {
        $Pids = ($Port8100Conns | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
        Write-Error "ERROR: Port 8100 is occupied by an unrelated service (PID: $Pids). Please release port 8100 manually before continuing. Never killing automatically."
        exit 1
    }
}

# 4. Check Port 6392 (Frontend)
Write-Host "[2/4] Checking Port 6392 (Frontend)..." -ForegroundColor Yellow
$FrontendAlreadyRunning = $false
$Port6392Conns = Get-NetTCPConnection -LocalPort 6392 -State Listen -ErrorAction SilentlyContinue

if ($Port6392Conns) {
    if (Test-FrontendHealth) {
        Write-Host "  -> Port 6392 is already running VibeConnect Frontend. Skipping launch." -ForegroundColor Green
        $FrontendAlreadyRunning = $true
    } else {
        $Pids = ($Port6392Conns | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
        Write-Error "ERROR: Port 6392 is occupied by an unrelated service (PID: $Pids). Please release port 6392 manually before continuing. Never killing automatically."
        exit 1
    }
}

# 5. Launch Backend if needed
if (-not $BackendAlreadyRunning) {
    Write-Host "[3/4] Launching VibeConnect Backend on 127.0.0.1:8100..." -ForegroundColor Cyan
    $BackendDirPy = $BackendDir -replace '\\', '/'
    $EnvDbUrl = if ($env:DATABASE_URL) {
        $env:DATABASE_URL
    } else {
        & $PythonExe -c "import urllib.parse, dotenv; vals = dotenv.dotenv_values('$BackendDirPy/.env.local'); u = vals.get('DATABASE_URL',''); p = urllib.parse.urlparse(u); print(urllib.parse.urlunparse(p._replace(path='/vibeconnect_phase2c_test')) if u else '')"
    }
    $BackendCmd = "`$Host.UI.RawUI.WindowTitle = 'VibeConnect Backend - 8100'; Set-Location -Path '$BackendDir'; `$env:DJANGO_SETTINGS_MODULE = 'config.settings.local'; `$env:DATABASE_URL = '$EnvDbUrl'; & '$PythonExe' manage.py runserver 127.0.0.1:8100"
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $BackendCmd
}

# 6. Launch Frontend if needed
if (-not $FrontendAlreadyRunning) {
    Write-Host "[4/4] Launching VibeConnect Frontend on localhost:6392..." -ForegroundColor Cyan
    $FrontendCmd = "`$Host.UI.RawUI.WindowTitle = 'VibeConnect Frontend - 6392'; Set-Location -Path '$FrontendDir'; npm run dev"
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $FrontendCmd
}

# 7. Polling Readiness
Write-Host ""
Write-Host "Polling service readiness..." -ForegroundColor Yellow
$TimeoutSec = 30
$Elapsed = 0
$BackendReady = $BackendAlreadyRunning
$FrontendReady = $FrontendAlreadyRunning

while ($Elapsed -lt $TimeoutSec) {
    if (-not $BackendReady) {
        $BackendReady = Test-BackendHealth
    }
    if (-not $FrontendReady) {
        $FrontendReady = Test-FrontendHealth
    }

    if ($BackendReady -and $FrontendReady) {
        break
    }

    Start-Sleep -Seconds 1
    $Elapsed++
}

Write-Host ""
if ($BackendReady -and $FrontendReady) {
    Write-Host "======================================================================" -ForegroundColor Green
    Write-Host "                       ALL SERVICES READY                             " -ForegroundColor Green
    Write-Host "======================================================================" -ForegroundColor Green
    Write-Host "  Backend URL  : http://127.0.0.1:8100" -ForegroundColor Green
    Write-Host "  Frontend URL : http://localhost:6392" -ForegroundColor Green
    Write-Host "  Public Plans : http://127.0.0.1:8100/api/v1/public/plans/" -ForegroundColor Green
    Write-Host ""
    Write-Host "NOTE: The backend and frontend are running in separate titled windows." -ForegroundColor White
    Write-Host "Closing or cancelling (Ctrl+C) either server window stops that individual service." -ForegroundColor Gray
    Write-Host "======================================================================" -ForegroundColor Green
} else {
    Write-Host "======================================================================" -ForegroundColor Red
    Write-Host "                   SERVICE STARTUP TIMEOUT / FAILURE                  " -ForegroundColor Red
    Write-Host "======================================================================" -ForegroundColor Red
    if (-not $BackendReady) {
        Write-Host "  -> Backend failed to report healthy on http://127.0.0.1:8100/api/v1/health/ within $TimeoutSec seconds." -ForegroundColor Red
    }
    if (-not $FrontendReady) {
        Write-Host "  -> Frontend failed to respond on http://localhost:6392/ within $TimeoutSec seconds." -ForegroundColor Red
    }
    exit 1
}
