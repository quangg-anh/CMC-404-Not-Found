# =========================================================
# load_seed_railway.ps1 - seed schema into Railway DBs (public TCP proxy)
# Run from repo root. Set env vars first (see README / chat notes).
#
# Requires: Python 3 + packages (no psql / cypher-shell):
#   python -m pip install "psycopg[binary]" neo4j httpx
# =========================================================
$ErrorActionPreference = 'Stop'
$DIR  = $PSScriptRoot                 # .../Data/seed
$DATA = Split-Path $DIR -Parent       # .../Data
if (-not (Test-Path (Join-Path $DATA 'schema'))) {
  throw "Data/schema not found. Run this script from the repo (Data/seed/load_seed_railway.ps1)."
}

if (-not $env:DATABASE_PUBLIC_URL) {
  throw "Set DATABASE_PUBLIC_URL first."
}
if (-not $env:NEO4J_PASSWORD) {
  throw "Set NEO4J_PASSWORD first."
}

$py = Join-Path $DIR 'load_seed_railway.py'
Write-Host "Running $py (Python drivers, no psql needed)..." -ForegroundColor Cyan
& python $py
if ($LASTEXITCODE -ne 0) { throw "load_seed_railway.py failed (exit $LASTEXITCODE)" }
