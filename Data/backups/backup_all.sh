#!/usr/bin/env bash
# =========================================================
# backup_all.sh - backup Postgres + Qdrant + Neo4j
# Chay:  bash Data/backups/backup_all.sh
# Postgres/Qdrant online; Neo4j Community offline (tu dong stop/start).
# =========================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
COMPOSE="$ROOT/docker-compose.data.yml"
# Khong bat buoc --env-file: compose da co gia tri default cho moi bien.

PG_USER="${POSTGRES_USER:-app_be_rw}"
PG_DB="${POSTGRES_DB:-legal_kg}"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"

echo "[1/3] Postgres pg_dump"
docker exec legal_postgres pg_dump -U "$PG_USER" "$PG_DB" > "$DIR/postgres/legal_kg_$STAMP.sql"
echo "  -> $DIR/postgres/legal_kg_$STAMP.sql"

echo "[2/3] Qdrant snapshots"
for c in khoan baidang chude; do
  curl -s -X POST "$QDRANT_URL/collections/$c/snapshots" >/dev/null && echo "  -> $c ok" || echo "  -> $c skip"
done

echo "[3/3] Neo4j dump (offline)"
docker compose -f "$COMPOSE" stop neo4j >/dev/null
docker compose -f "$COMPOSE" run --rm --entrypoint neo4j-admin neo4j \
  database dump neo4j --to-path=/backups --overwrite-destination=true
docker compose -f "$COMPOSE" start neo4j >/dev/null
echo "  -> Data/backups/neo4j/neo4j.dump"

echo "DONE backup ($STAMP). MinIO: dung versioning bucket."
