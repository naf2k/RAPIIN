#!/usr/bin/env python3
"""Copy a RAPIIN SQLite database into an empty PostgreSQL database."""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))


def migrate(source: Path, database_url: str) -> dict:
    if not source.is_file():
        raise FileNotFoundError(f"SQLite source tidak ditemukan: {source}")
    if not database_url.startswith(("postgresql://", "postgres://")):
        raise ValueError("Target wajib berupa PostgreSQL DATABASE_URL.")
    import psycopg
    from psycopg import sql
    from rapiin.database import SCHEMA
    from rapiin.postgres_support import postgres_schema

    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    copied: dict[str, int] = {}
    try:
        with psycopg.connect(database_url) as dst:
            with dst.cursor() as cur:
                cur.execute(postgres_schema(SCHEMA))
                tables = [row[0] for row in src.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
                )]
                for table in tables:
                    columns = [row[1] for row in src.execute(f'PRAGMA table_info("{table}")')]
                    rows = src.execute(f'SELECT * FROM "{table}"').fetchall()
                    if rows and columns:
                        statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                            sql.Identifier(table),
                            sql.SQL(",").join(map(sql.Identifier, columns)),
                            sql.SQL(",").join(sql.Placeholder() for _ in columns),
                        )
                        cur.executemany(statement, [tuple(row[column] for column in columns) for row in rows])
                    copied[table] = len(rows)
                    if "id" in columns:
                        cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
                        sequence = cur.fetchone()[0]
                        if sequence:
                            cur.execute(
                                sql.SQL("SELECT setval({}, COALESCE((SELECT MAX(id) FROM {}), 1), (SELECT COUNT(*) > 0 FROM {}))").format(
                                    sql.Literal(sequence), sql.Identifier(table), sql.Identifier(table)
                                )
                            )
    finally:
        src.close()
    return {"tables": len(copied), "rows": sum(copied.values()), "copied": copied}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--database-url", default=os.getenv("RAPIIN_DATABASE_URL", ""))
    parser.add_argument("--confirm-empty-target", action="store_true")
    args = parser.parse_args()
    if not args.confirm_empty_target:
        raise SystemExit("Tambahkan --confirm-empty-target setelah memastikan database target kosong.")
    print(migrate(args.source, args.database_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
