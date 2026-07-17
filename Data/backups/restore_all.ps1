# =========================================================
# restore_all.ps1 - restore Neo4j tu dump (Windows)
# Chay:  powershell -File Data/backups/restore_all.ps1
# CANH BAO: ghi de database 'neo4j' hien tai bang ban dump gan nhat.
# Postgres restore: psql -f <file.sql>  (thu cong, xem README).
# Qdrant restore: Snapshot recover API (xem README).
# =========================================================
$ErrorActionPreference = 'Continue'
$env:Path = "C:\Program Files\Docker\Docker\resources\bin;" + $env:Path

$DIR     = $PSScriptRoot
$COMPOSE = Join-Path (Split-Path $DIR -Parent) 'docker-compose.data.yml'

Write-Host "Neo4j: load tu /backups/neo4j.dump (offline)"
docker compose -f $COMPOSE stop neo4j 2>&1 | Out-Null
try {
  docker compose -f $COMPOSE run --rm --entrypoint neo4j-admin neo4j `
    database load neo4j --from-path=/backups --overwrite-destination=true 2>&1 |
    Select-String -Pattern 'Done|Loaded|ERROR|failed|Selecting'
} finally {
  docker compose -f $COMPOSE start neo4j 2>&1 | Out-Null
  Write-Host "Neo4j da start lai."
}
Write-Host "DONE restore Neo4j."
