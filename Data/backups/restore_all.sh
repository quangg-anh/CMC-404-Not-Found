#!/usr/bin/env bash
# =========================================================
# restore_all.sh - restore Neo4j tu dump
# Chay:  bash Data/backups/restore_all.sh
# CANH BAO: ghi de database 'neo4j' hien tai bang ban dump gan nhat.
# =========================================================
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
COMPOSE="$ROOT/docker-compose.data.yml"

echo "Neo4j: load tu /backups/neo4j.dump (offline)"
docker compose -f "$COMPOSE" stop neo4j >/dev/null
docker compose -f "$COMPOSE" run --rm --entrypoint neo4j-admin neo4j \
  database load neo4j --from-path=/backups --overwrite-destination=true
docker compose -f "$COMPOSE" start neo4j >/dev/null
echo "DONE restore Neo4j."
