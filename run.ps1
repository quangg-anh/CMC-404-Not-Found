<#
=====================================================================
 run.ps1 - Unified launcher for the Legal Knowledge Graph system
=====================================================================
 One file to start the whole stack, end to end. Each long-running
 process opens in its own PowerShell window so you can read its logs
 and Ctrl+C it individually.

 USAGE (from repo root):
   ./run.ps1                # FULL RUN: data stack + seed + backend + workers + frontend
                            #   (auto npm install on first run if node_modules is missing)
   ./run.ps1 -Install       # create venv + pip install + npm install, then run
   ./run.ps1 -Backend       # only backend processes (BE2 + BE3)
   ./run.ps1 -Frontend      # only frontend dev servers (admin + citizen)
   ./run.ps1 -Stack         # only bring up the Docker data stack + seed
   ./run.ps1 -Worker        # also start the Arq workers (BE2 + legal)
   ./run.ps1 -Stop          # stop everything this script started (by port)

 Combine flags freely, e.g.:  ./run.ps1 -Install -Stack -Worker -Backend

 Services / URLs:
   Backend  BE3 API   http://localhost:8000   (docs: /docs)
   Backend  BE2 gate  http://localhost:8002
   Frontend Admin      http://localhost:5173/admin/
   Frontend Citizen    http://localhost:5174/citizen/
 Login (seeded): admin@local / admin123  |  citizen@local / citizen123
 External dep (not started here): Ollama on :11434 with model bge-m3 for embeddings.
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

# ---- Flag resolution -------------------------------------------------
# No flags at all => a complete run of the entire system in one command.
$NoFlags = -not ($Backend -or $Frontend -or $Stack -or $Worker -or $Install -or $Stop)
if ($NoFlags) {
    $Stack = $true; $Worker = $true; $Backend = $true; $Frontend = $true
    # First run convenience: install frontend deps if they're missing.
    if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) { $Install = $true }
}
elseif (-not $Stop -and -not $Backend -and -not $Frontend) {
    # A partial invocation (e.g. only -Stack/-Worker) still implies starting the app servers.
    $Backend = $true; $Frontend = $true
}

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "   [!] $msg" -ForegroundColor Yellow }

function Import-DotEnv($path) {
    # Load KEY=VALUE lines into this process env so the seed step + docker compose share creds.
    if (-not (Test-Path $path)) { return }
    foreach ($line in Get-Content $path) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith('#') -or ($t -notmatch '=')) { continue }
        $k, $v = $t.Split('=', 2)
        [System.Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim().Trim('"').Trim("'"))
    }
}

function Test-TcpPort([string]$TargetHost, [int]$Port) {
    try {
        $c = New-Object Net.Sockets.TcpClient
        $c.Connect($TargetHost, $Port); $c.Close(); return $true
    } catch { return $false }
}

function Stop-ByPort([int[]]$Ports) {
    # Tree-kill (/T) the process holding each port so uvicorn --reload watchers and their
    # multiprocessing worker children are all cleaned up (avoids orphaned listening sockets).
    foreach ($p in $Ports) {
        $ids = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($procId in $ids) {
            if ($procId -and $procId -ne 0) {
                taskkill /F /T /PID $procId 2>$null | Out-Null
            }
        }
    }
}

function Resolve-Python {
    # Pick an interpreter that can actually import uvicorn: prefer the project venv, else fall back
    # to the global `python` on PATH. Returns $null if neither works (tells the user to -Install).
    $ErrorActionPreference = 'SilentlyContinue'
    if (Test-Path $VenvPy) {
        try { & $VenvPy -c "import uvicorn" *>$null } catch {}
        if ($LASTEXITCODE -eq 0) { return $VenvPy }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        try { & python -c "import uvicorn" *>$null } catch {}
        if ($LASTEXITCODE -eq 0) { return 'python' }
    }
    return $null
}

function Wait-ForPostgres([int]$TimeoutSec = 90) {
    $pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { 'app_be_rw' }
    $pgDb   = if ($env:POSTGRES_DB)   { $env:POSTGRES_DB }   else { 'legal_kg' }
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $ErrorActionPreference = 'SilentlyContinue'
        docker exec legal_postgres pg_isready -U $pgUser -d $pgDb *>$null
        if ($LASTEXITCODE -eq 0) { return $true }
        Start-Sleep -Seconds 3
    }
    return $false
}

function Wait-ForNeo4j([int]$TimeoutSec = 120) {
    $pw = if ($env:NEO4J_PASSWORD) { $env:NEO4J_PASSWORD } else { 'change_me_neo4j' }
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $ErrorActionPreference = 'SilentlyContinue'
        "RETURN 1;" | docker exec -i legal_neo4j cypher-shell -u neo4j -p $pw *>$null
        if ($LASTEXITCODE -eq 0) { return $true }
        Start-Sleep -Seconds 4
    }
    return $false
}

function Test-BackendPrereqs {
    # Non-fatal preflight so failures are obvious instead of silent 500s / broken login.
    if (-not (Test-TcpPort 'localhost' 5432)) {
        Write-Warn 'Postgres :5432 not running - login and data will fail. Run: ./run.ps1 -Stack'
    }
    if (-not (Test-TcpPort 'localhost' 11434)) {
        Write-Warn 'Ollama :11434 not running - embeddings (bge-m3) will fail; QA/ingest cannot build vectors.'
    } else {
        try {
            $tags = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 4
            if (-not ($tags.models.name -match 'bge-m3')) { Write-Warn 'Ollama missing model bge-m3 - run: ollama pull bge-m3' }
        } catch {}
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
    # Share Data/.env creds with the seed step (and any docker exec below).
    Import-DotEnv $DataEnv

    Write-Step 'Docker data stack: up -d (postgres, neo4j, qdrant, redis, minio)'
    docker compose -f $DataCompose --env-file $DataEnv up -d

    Write-Step 'Waiting for Postgres + Neo4j to accept connections'
    if (Wait-ForPostgres) { Write-Host '   Postgres ready.' -ForegroundColor Green }
    else { Write-Warn 'Postgres not ready in time - seeding may fail.' }
    if (Wait-ForNeo4j)    { Write-Host '   Neo4j ready.' -ForegroundColor Green }
    else { Write-Warn 'Neo4j not ready in time - graph seed may fail.' }

    $seed = Join-Path $Root 'Data/seed/load_seed.ps1'
    if (Test-Path $seed) {
        Write-Step 'Seeding data stack (constraints, sample documents, users, Qdrant collections)'
        powershell -ExecutionPolicy Bypass -File $seed
    }
}

# ------------------------------------------------------------- BACKEND
if ($Backend) {
    $Py = Resolve-Python
    if (-not $Py) {
        Write-Host "No Python with uvicorn/fastapi found (checked .venv and global python)." -ForegroundColor Red
        Write-Host "Run './run.ps1 -Install' first, or 'pip install -r Backend/requirements.txt'." -ForegroundColor Red
        return
    }
    Write-Host "   using interpreter: $Py" -ForegroundColor DarkGray
    Test-BackendPrereqs

    Write-Step 'Backend: freeing ports 8000 / 8002'
    Stop-ByPort @(8000, 8002)
    Start-Sleep -Seconds 1

    Write-Step 'Backend: starting BE2 intelligence gateway (:8002) and BE3 API (:8000)'
    Start-InWindow 'BE2 gateway :8002' $BackendDir "& '$Py' -m uvicorn be2_service:app --port 8002"
    Start-Sleep -Seconds 2
    Start-InWindow 'BE3 API :8000'     $BackendDir "& '$Py' -m uvicorn app.main:app --reload --port 8000"

    if ($Worker) {
        Write-Step 'Backend: starting Arq workers (BE2 + legal)'
        Start-InWindow 'Arq BE2 worker'   $BackendDir "& '$Py' -m arq app.workers.arq_settings.WorkerSettings"
        Start-InWindow 'Arq legal worker' $BackendDir "& '$Py' -m arq app.workers.arq_settings.LegalWorkerSettings"
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
if ($Frontend) { Write-Host '   Admin        http://localhost:5173/admin/   (admin@local / admin123)' }
if ($Frontend) { Write-Host '   Citizen      http://localhost:5174/citizen/' }
Write-Host ' Stop all with:  ./run.ps1 -Stop' -ForegroundColor DarkGray
Write-Host "=====================================================================`n" -ForegroundColor Cyan
