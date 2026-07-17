# =========================================================
# backup_all.ps1 - backup Postgres + Qdrant + Neo4j (Windows)
# Chay:  powershell -File Data/backups/backup_all.ps1
# Postgres/Qdrant online; Neo4j Community offline (tu dong stop/start).
# LUU Y: dat ErrorActionPreference=Continue vi docker compose ghi tien trinh
#        ra stderr; try/finally dam bao Neo4j LUON duoc start lai.
# =========================================================
$ErrorActionPreference = 'Continue'
$env:Path = "C:\Program Files\Docker\Docker\resources\bin;" + $env:Path

$DIR     = $PSScriptRoot
$STAMP   = Get-Date -Format 'yyyyMMdd-HHmmss'
$COMPOSE = Join-Path (Split-Path $DIR -Parent) 'docker-compose.data.yml'

$PG_USER = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { 'app_be_rw' }
$PG_DB   = if ($env:POSTGRES_DB)   { $env:POSTGRES_DB }   else { 'legal_kg' }
$QDRANT  = if ($env:QDRANT_URL)    { $env:QDRANT_URL }    else { 'http://localhost:6333' }

Write-Host "[1/3] Postgres pg_dump"
$pgOut = Join-Path $DIR "postgres/legal_kg_$STAMP.sql"
docker exec legal_postgres pg_dump -U $PG_USER $PG_DB | Out-File -Encoding utf8 $pgOut
Write-Host ("  -> {0} ({1} bytes)" -f $pgOut, (Get-Item $pgOut).Length)

Write-Host "[2/3] Qdrant snapshots (moi collection)"
foreach ($c in 'khoan','baidang','chude') {
  try {
    $s = Invoke-RestMethod -Method Post -Uri "$QDRANT/collections/$c/snapshots"
    Write-Host ("  -> {0}: {1}" -f $c, $s.result.name)
  } catch { Write-Host ("  -> {0}: skip ({1})" -f $c, $_.Exception.Message) }
}

Write-Host "[3/3] Neo4j dump (offline - stop/start DB)"
docker compose -f $COMPOSE stop neo4j 2>&1 | Out-Null
try {
  docker compose -f $COMPOSE run --rm --entrypoint neo4j-admin neo4j `
    database dump neo4j --to-path=/backups --overwrite-destination=true 2>&1 |
    Select-String -Pattern 'Dump completed|ERROR|failed'
} finally {
  docker compose -f $COMPOSE start neo4j 2>&1 | Out-Null
  Write-Host "  -> Data/backups/neo4j/neo4j.dump (Neo4j da start lai)"
}

Write-Host "DONE backup ($STAMP). MinIO: dung versioning bucket (khong dump o day)."
