from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def apply_migrations(dsn: str) -> list[str]:
    applied: list[str] = []
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS fabops_schema_migrations (
                migration_name TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            exists = connection.execute(
                "SELECT 1 FROM fabops_schema_migrations WHERE migration_name = %s",
                (path.name,),
            ).fetchone()
            if exists:
                continue
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute("INSERT INTO fabops_schema_migrations(migration_name) VALUES (%s)", (path.name,))
            applied.append(path.name)
    return applied


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply FabOps PostgreSQL migrations.")
    parser.add_argument("--dsn", default=os.environ.get("FABOPS_POSTGRES_DSN"))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("FABOPS_POSTGRES_DSN or --dsn is required")
    applied = apply_migrations(args.dsn)
    print(f"migrations_applied={len(applied)}")


if __name__ == "__main__":
    main()
