#!/usr/bin/env bash
# =========================================================
# load_seed.sh - nap constraints + seed VB + users + collections
# Chay:  bash Data/seed/load_seed.sh   (can Docker stack dang chay)
# Bien lay tu moi truong (hoac dung default khop .env.example).
# =========================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"            # thu muc Data/

NEO4J_PW="${NEO4J_PASSWORD:-change_me_neo4j}"
PG_USER="${POSTGRES_USER:-app_be_rw}"
PG_DB="${POSTGRES_DB:-legal_kg}"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
DIM="${EMBEDDING_DIM:-1024}"

echo "[1/4] Neo4j: constraints + indexes"
docker exec -i legal_neo4j cypher-shell -u neo4j -p "$NEO4J_PW" < "$ROOT/schema/neo4j_constraints.cypher"
docker exec -i legal_neo4j cypher-shell -u neo4j -p "$NEO4J_PW" < "$ROOT/schema/neo4j_indexes.cypher"

echo "[2/4] Neo4j: load van ban mau"
for f in "$DIR"/van_ban_mau/*.cypher; do
  echo "  - $(basename "$f")"
  docker exec -i legal_neo4j cypher-shell -u neo4j -p "$NEO4J_PW" < "$f"
done

echo "[3/5] Postgres: apply incremental migrations (idempotent)"
for f in "$ROOT"/schema/postgres/*.sql; do
  base="$(basename "$f")"
  case "$base" in
    001_*|002_*|003_*) continue ;;
  esac
  echo "  - $base"
  docker exec -i legal_postgres psql -U "$PG_USER" -d "$PG_DB" < "$f"
done

echo "[4/5] Postgres: seed users + lineage"
docker exec -i legal_postgres psql -U "$PG_USER" -d "$PG_DB" < "$DIR/users_seed.sql"

echo "[5/5] Qdrant: ensure collections (dim=$DIM)"
for c in khoan baidang chude; do
  curl -s -X PUT "$QDRANT_URL/collections/$c" -H 'Content-Type: application/json' \
    -d "{\"vectors\":{\"size\":$DIM,\"distance\":\"Cosine\"}}" >/dev/null || true
done

echo "DONE seed. (admin@local/admin123)"
