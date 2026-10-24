"""Open the ingestion's database, creating its schema and bringing an older one up to date.

Each app keeps its own `db/schema.sql` (its tables, then `CREATE OR REPLACE VIEW v_*` for the contract) and its
own schema version with migrations. The database records the version in `schema_version`. A new database gets
the current version; an older one runs each migration in turn; a newer one, or one with no migration, stops
with an error. schema.sql runs on every write connection, so it must only create what is missing (CREATE TABLE IF
NOT EXISTS) and replace the views.

A migration is SQL, or a function of the connection. Nothing here drops a table: a migration that does is
written, reviewed and tested in the app.
"""

from collections.abc import Callable
from pathlib import Path

import duckdb

from duckkit.snapshot import literal
from duckkit.spec import AppSpec

Migration = str | Callable[[duckdb.DuckDBPyConnection], None]


def connect(spec: AppSpec, schema_sql: str | Callable[[], str], version: int = 1,
            migrations: dict[int, Migration] | None = None, path: Path | None = None,
            read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the database (default: spec.db_path), creating or migrating its schema when writable.
    `schema_sql` is the SQL, or a function returning it (read only when needed)."""
    path = path or spec.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path), read_only=read_only)
    if spec.timezone:
        con.execute(f"SET TimeZone = {literal(spec.timezone)}")
    if not read_only:
        init_schema(con, schema_sql() if callable(schema_sql) else schema_sql, version, migrations or {})
    return con


def init_schema(con: duckdb.DuckDBPyConnection, schema_sql: str, version: int,
                migrations: dict[int, Migration]) -> None:
    """Record the schema version of a new database, or migrate an older one, then run `schema_sql`.

    `migrations` maps a version to what brings it to version + 1."""
    con.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    found = con.execute("SELECT max(version) FROM schema_version").fetchone()[0]
    if found is None:
        con.execute("INSERT INTO schema_version VALUES (?)", [version])
    else:
        while found < version:
            if found not in migrations:
                raise RuntimeError(f"no migration from schema version {found}: write one in db/store.py")
            step = migrations[found]
            con.execute(step) if isinstance(step, str) else step(con)
            found += 1
            con.execute("UPDATE schema_version SET version = ?", [found])
        if found > version:
            raise RuntimeError(f"the database has schema version {found}, newer than this code ({version})")
    con.execute(schema_sql)


def tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    """The base tables of the connection's current database (not views), by name."""
    return [t for (t,) in con.execute("""
        SELECT table_name FROM duckdb_tables()
        WHERE database_name = current_database() AND schema_name = current_schema() AND NOT internal
        ORDER BY table_name
    """).fetchall()]
