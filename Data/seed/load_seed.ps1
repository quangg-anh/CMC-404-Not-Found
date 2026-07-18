# =========================================================
# load_seed.ps1 - ban Windows/PowerShell cua load_seed.sh
# Chay:  pwsh Data/seed/load_seed.ps1   (can Docker stack dang chay)
# =========================================================
$ErrorActionPreference = 'Stop'
$env:Path = "C:\Program Files\Docker\Docker\resources\bin;" + $env:Path

$DIR  = $PSScriptRoot
$ROOT = Split-Path $DIR -Parent            # thu muc Data/

$NEO4J_PW  = if ($env:NEO4J_PASSWORD) { $env:NEO4J_PASSWORD } else { 'change_me_neo4j' }
$PG_USER   = if ($env:POSTGRES_USER)  { $env:POSTGRES_USER }  else { 'app_be_rw' }
$PG_DB     = if ($env:POSTGRES_DB)    { $env:POSTGRES_DB }    else { 'legal_kg' }
$QDRANT    = if ($env:QDRANT_URL)     { $env:QDRANT_URL }     else { 'http://localhost:6333' }
$DIM       = if ($env:EMBEDDING_DIM)  { [int]$env:EMBEDDING_DIM } else { 1536 }

Write-Host "[1/4] Neo4j: constraints + indexes"
Get-Content "$ROOT/schema/neo4j_constraints.cypher" -Raw | docker exec -i legal_neo4j cypher-shell -u neo4j -p $NEO4J_PW
Get-Content "$ROOT/schema/neo4j_indexes.cypher" -Raw | docker exec -i legal_neo4j cypher-shell -u neo4j -p $NEO4J_PW

Write-Host "[2/4] Neo4j: load van ban mau"
Get-ChildItem "$DIR/van_ban_mau/*.cypher" | ForEach-Object {
  Write-Host "  - $($_.Name)"
  Get-Content $_.FullName -Raw | docker exec -i legal_neo4j cypher-shell -u neo4j -p $NEO4J_PW
}

Write-Host "[3/5] Postgres: apply incremental migrations (idempotent)"
Get-ChildItem "$ROOT/schema/postgres/*.sql" | Sort-Object Name | ForEach-Object {
  # 001-003 usually applied at first init; re-running later files with IF NOT EXISTS is safe.
  if ($_.Name -match '^(001_|002_|003_)') { return }
  Write-Host "  - $($_.Name)"
  Get-Content $_.FullName -Raw | docker exec -i legal_postgres psql -U $PG_USER -d $PG_DB
}

Write-Host "[4/5] Postgres: seed users + lineage"
Get-Content "$DIR/users_seed.sql" -Raw | docker exec -i legal_postgres psql -U $PG_USER -d $PG_DB

Write-Host "[5/5] Qdrant: ensure collections (dim=$DIM)"
foreach ($c in 'khoan','baidang','chude') {
  $body = @{ vectors = @{ size = $DIM; distance = 'Cosine' } } | ConvertTo-Json
  try { Invoke-RestMethod -Method Put -Uri "$QDRANT/collections/$c" -ContentType 'application/json' -Body $body | Out-Null } catch {}
}

Write-Host "DONE seed. (admin@local/admin123)"
