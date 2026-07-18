#!/usr/bin/env python3
"""Seed schema into Railway DBs via public TCP proxy.

Requires only Python packages (no psql / cypher-shell):
  pip install "psycopg[binary]" neo4j httpx

Env:
  DATABASE_PUBLIC_URL  postgresql://...@tokaido.proxy.rlwy.net:.../railway
  NEO4J_BOLT_HOST      default tokaido.proxy.rlwy.net
  NEO4J_BOLT_PORT      default 20113
  NEO4J_USER           default neo4j
  NEO4J_PASSWORD       required
  QDRANT_URL           default http://tokaido.proxy.rlwy.net:30541
  EMBEDDING_DIM        default 1536
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import httpx
import psycopg
from neo4j import GraphDatabase

SEED_DIR = Path(__file__).resolve().parent
DATA_DIR = SEED_DIR.parent


def env(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if val is None or val == "":
        raise SystemExit(f"Set {name} first.")
    return val


def run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    print(f"  {path.name}")
    sql = path.read_text(encoding="utf-8")
    conn.execute(sql)


def strip_cypher_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.lstrip().startswith("//"):
            continue
        # drop trailing // comments (seed files are simple)
        if "//" in line:
            line = line.split("//", 1)[0]
        lines.append(line)
    return "\n".join(lines)


def cypher_statements(text: str) -> list[str]:
    cleaned = strip_cypher_comments(text)
    parts = re.split(r";\s*", cleaned)
    return [p.strip() for p in parts if p.strip()]


def run_cypher_file(session, path: Path) -> None:
    print(f"  {path.name}")
    for stmt in cypher_statements(path.read_text(encoding="utf-8")):
        session.run(stmt)


def main() -> None:
    if not (DATA_DIR / "schema").is_dir():
        raise SystemExit(f"Data/schema not found under {DATA_DIR}")

    pg_url = env("DATABASE_PUBLIC_URL")
    # psycopg wants postgresql:// (not postgres://)
    if pg_url.startswith("postgres://"):
        pg_url = "postgresql://" + pg_url[len("postgres://") :]

    neo4j_host = os.environ.get("NEO4J_BOLT_HOST", "tokaido.proxy.rlwy.net")
    neo4j_port = os.environ.get("NEO4J_BOLT_PORT", "20113")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_pw = env("NEO4J_PASSWORD")
    qdrant_url = os.environ.get("QDRANT_URL", "http://tokaido.proxy.rlwy.net:30541").rstrip("/")
    dim = int(os.environ.get("EMBEDDING_DIM", "1536"))
    bolt = f"bolt://{neo4j_host}:{neo4j_port}"

    print("== Postgres migrations ==")
    # Railway public proxy usually needs TLS
    with psycopg.connect(pg_url, sslmode="require", autocommit=True) as conn:
        for name in (
            "001_init.sql",
            "002_jobs_lineage.sql",
            "003_content_publish.sql",
            "004_retention_audit.sql",
            "009_alert_provenance.sql",
        ):
            run_sql_file(conn, DATA_DIR / "schema" / "postgres" / name)

        print("== Postgres seed ==")
        run_sql_file(conn, DATA_DIR / "seed" / "users_seed.sql")
        run_sql_file(conn, DATA_DIR / "seed" / "demo_content_seed.sql")

    print("== Neo4j constraints + indexes ==")
    driver = GraphDatabase.driver(bolt, auth=(neo4j_user, neo4j_pw))
    try:
        driver.verify_connectivity()
        with driver.session() as session:
            run_cypher_file(session, DATA_DIR / "schema" / "neo4j_constraints.cypher")
            run_cypher_file(session, DATA_DIR / "schema" / "neo4j_indexes.cypher")
            print("== Neo4j sample documents ==")
            for path in sorted((DATA_DIR / "seed" / "van_ban_mau").glob("*.cypher")):
                run_cypher_file(session, path)
    finally:
        driver.close()

    print(f"== Qdrant collections (dim={dim}) ==")
    body = {"vectors": {"size": dim, "distance": "Cosine"}}
    with httpx.Client(timeout=60.0) as client:
        for name in ("khoan", "baidang", "chude"):
            print(f"  PUT {name}")
            r = client.put(f"{qdrant_url}/collections/{name}", json=body)
            # 200 = created/updated; 409 = already exists with same config — ok
            if r.status_code not in (200, 201) and r.status_code != 409:
                # Qdrant returns 200 even when exists sometimes; surface body on hard fail
                if r.status_code >= 400:
                    detail = r.text[:500]
                    # collection already exists is fine for idempotent re-run
                    if "already exists" not in detail.lower() and r.status_code != 409:
                        raise SystemExit(f"Qdrant PUT {name} failed: {r.status_code} {detail}")
            print(f"    -> {r.status_code}")

    print("DONE. Login: admin@local / admin123")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
