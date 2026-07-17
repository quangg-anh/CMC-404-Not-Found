<#
=====================================================================
 run.ps1 - Unified launcher for the Legal Knowledge Graph system
=====================================================================
 One file to start the whole stack. Each long-running process opens in
 its own PowerShell window so you can read its logs and Ctrl+C it.

 USAGE (from repo root):
   ./run.ps1                # start backend (BE2+BE3) + frontend (admin+citizen)
   ./run.ps1 -Backend       # only backend processes
   ./run.ps1 -Frontend      # only frontend dev servers
   ./run.ps1 -Stack         # also bring up the Docker data stack + seed first
   ./run.ps1 -Worker        # also start the Arq workers (BE2 + legal)
   ./run.ps1 -Install       # create venv + pip install + npm install, then run
   ./run.ps1 -Stop          # stop everything this script started (by port)

 Combine flags freely, e.g.:  ./run.ps1 -Install -Stack -Worker

 Services / URLs:
   Backend  BE3 API   http://localhost:8000   (docs: /docs)
   Backend  BE2 gate  http://localhost:8002
   Frontend Admin      http://localhost:5173/admin/
   Frontend Citizen    http://localhost:5174/citizen/
 Requires (not started here): Ollama on :11434 with models `bge-m3` + the chat model.
=====================================================================
#>
[CmdletBinding()]
param(
    [switch]$Backend,
    [switch]$Frontend,
    [switch]$Stack,
    [switch]$Worker,
    [switch]$Install,
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'
$Root       = $PSScriptRoot
$BackendDir = Join-Path $Root 'Backend'
$FrontendDir= Join-Path $Root 'Frontend'
$DataCompose= Join-Path $Root 'Data/docker-compose.data.yml'
$DataEnv    = Join-Path $Root 'Data/.env'
$VenvPy     = Join-Path $BackendDir '.venv/Scripts/python.exe'

# If neither -Backend nor -Frontend is given, run both.
if (-not $Backend -and -not $Frontend) { $Backend = $true; $Frontend = $true }

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

function Stop-ByPort([int[]]$Ports) {
    foreach ($p in $Ports) {
        Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique |
            ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    }
}

function Start-InWindow($title, $workdir, $command) {
    # Launch a command in its own titled PowerShell window (stays open).
    $inner = "`$host.UI.RawUI.WindowTitle='$title'; Set-Location '$workdir'; $command"
    Start-Process -FilePath 'powershell' -ArgumentList @(
        '-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $inner
    ) | Out-Null
    Write-Host "   started: $title" -ForegroundColor Green
}

# ---------------------------------------------------------------- STOP
if ($Stop) {
    Write-Step 'Stopping backend (8000, 8002) and frontend (5173, 5174)'
    Stop-ByPort @(8000, 8002, 5173, 5174)
    Write-Host 'Done. (Docker data stack left running; use docker compose down if needed.)' -ForegroundColor Yellow
    return
}

# ------------------------------------------------------------- INSTALL
if ($Install) {
    if ($Backend) {
        Write-Step 'Backend: create venv + install requirements'
        if (-not (Test-Path $VenvPy)) {
            python -m venv (Join-Path $BackendDir '.venv')
        }
        & $VenvPy -m pip install --upgrade pip
        & $VenvPy -m pip install -r (Join-Path $BackendDir 'requirements.txt')
    }
    if ($Frontend) {
        Write-Step 'Frontend: npm install (workspaces)'
        Push-Location $FrontendDir
        npm install
        Pop-Location
    }
}

# --------------------------------------------------------- DATA STACK
if ($Stack) {
    Write-Step 'Docker data stack: up -d (postgres, neo4j, qdrant, redis, minio)'
    docker compose -f $DataCompose --env-file $DataEnv up -d
    Write-Host '   waiting 8s for containers to become healthy...' -ForegroundColor DarkGray
    Start-Sleep -Seconds 8
    $seed = Join-Path $Root 'Data/seed/load_seed.ps1'
    if (Test-Path $seed) {
        Write-Step 'Seeding data stack'
        powershell -ExecutionPolicy Bypass -File $seed
    }
}

# ------------------------------------------------------------- BACKEND
if ($Backend) {
    if (-not (Test-Path $VenvPy)) {
        Write-Host "venv not found at $VenvPy. Run './run.ps1 -Install' first." -ForegroundColor Red
        return
    }
    Write-Step 'Backend: freeing ports 8000 / 8002'
    Stop-ByPort @(8000, 8002)
    Start-Sleep -Seconds 1

    Write-Step 'Backend: starting BE2 intelligence gateway (:8002) and BE3 API (:8000)'
    Start-InWindow 'BE2 gateway :8002' $BackendDir "& '$VenvPy' -m uvicorn be2_service:app --port 8002"
    Start-Sleep -Seconds 2
    Start-InWindow 'BE3 API :8000'     $BackendDir "& '$VenvPy' -m uvicorn app.main:app --reload --port 8000"

    if ($Worker) {
        Write-Step 'Backend: starting Arq workers (BE2 + legal)'
        Start-InWindow 'Arq BE2 worker'   $BackendDir "& '$VenvPy' -m arq app.workers.arq_settings.WorkerSettings"
        Start-InWindow 'Arq legal worker' $BackendDir "& '$VenvPy' -m arq app.workers.arq_settings.LegalWorkerSettings"
    }
}

# ------------------------------------------------------------ FRONTEND
if ($Frontend) {
    if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
        Write-Host "Frontend node_modules missing. Run './run.ps1 -Install' first." -ForegroundColor Red
        return
    }
    Write-Step 'Frontend: freeing ports 5173 / 5174'
    Stop-ByPort @(5173, 5174)
    Start-Sleep -Seconds 1

    Write-Step 'Frontend: starting Admin (:5173) and Citizen (:5174) dev servers'
    Start-InWindow 'Admin :5173'   $FrontendDir 'npm run dev -w admin'
    Start-InWindow 'Citizen :5174' $FrontendDir 'npm run dev -w citizen'
}

Write-Host "`n=====================================================================" -ForegroundColor Cyan
Write-Host ' System starting. Open:' -ForegroundColor Cyan
if ($Backend)  { Write-Host '   BE3 API      http://localhost:8000/docs' }
if ($Backend)  { Write-Host '   BE2 gateway  http://localhost:8002/health' }
if ($Frontend) { Write-Host '   Admin        http://localhost:5173/admin/' }
if ($Frontend) { Write-Host '   Citizen      http://localhost:5174/citizen/' }
Write-Host ' Stop all with:  ./run.ps1 -Stop' -ForegroundColor DarkGray
Write-Host "=====================================================================`n" -ForegroundColor Cyan
