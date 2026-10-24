"""Publish the contract's views to MotherDuck, so Claude (and a hosted app) can read them from anywhere.

Only the contract views leave this machine, cut to the reference schema's columns (the same copy the browser app
reads), as tables of the same names. Each table and column carries its description from the reference schema as a
comment, so the published database describes itself. Nothing publishes automatically: only `<cli> publish` (or
`/publish`) does.

- `plan`: what would be sent (rows and columns per view), sending nothing (`publish --dry-run`)
- `publish`: replace the published tables, in one transaction
- `compare`: whether the published copy still matches the database, changing nothing (`publish --check`)
"""

from pathlib import Path

import duckdb

from duckkit.snapshot import contract_copy, literal, motherduck
from duckkit.spec import AppSpec


def plan(spec: AppSpec, source: Path | None = None) -> dict[str, tuple[int, list[str]]]:
    """What `publish` would send, without sending anything: {view: (rows, columns)}."""
    con = contract_copy(spec, source)
    try:
        return {view: (con.execute(f"SELECT count(*) FROM memory.{view}").fetchone()[0], list(columns))
                for view, (_, columns) in spec.contract.descriptions().items()}
    finally:
        con.close()


def publish(spec: AppSpec, target: str | None = None, source: Path | None = None) -> dict[str, int]:
    """Replace the contract tables at `target` with the database's current views; returns rows per table.

    `target` is a MotherDuck database (`md:<name>`, created if missing; needs a MotherDuck token) or, for tests
    and offline copies, a DuckDB file. Default: spec.motherduck_target. Everything happens in one transaction:
    readers see the old tables or the new ones, never a mix.
    """
    target = _target(spec, target)
    con = contract_copy(spec, source)
    try:
        catalog = _attach(spec, con, target)
        counts = {}
        con.begin()
        for view, (about, columns) in spec.contract.descriptions().items():
            table = f'"{catalog}".main.{view}'
            con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM memory.{view}")
            con.execute(f"COMMENT ON TABLE {table} IS {literal(about)}")
            for column, text in columns.items():
                con.execute(f"COMMENT ON COLUMN {table}.{column} IS {literal(text)}")
            counts[view] = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        con.commit()
        return counts
    finally:
        con.close()


def compare(spec: AppSpec, target: str | None = None,
            source: Path | None = None) -> dict[str, tuple[int, int | None, bool]]:
    """The database's contract views against the tables published at `target`, changing neither.

    Returns {view: (rows here, rows published or None if the table is missing, same contents)}. Contents are
    compared by a fingerprint of every row (a sum of row hashes: order doesn't matter), so a changed value shows
    even when the row counts agree.
    """
    target = _target(spec, target)
    con = contract_copy(spec, source)
    try:
        if target.startswith("md:"):
            motherduck(spec, con)
        elif not Path(target).exists():
            raise FileNotFoundError(f"nothing published at {target}: run `{spec.cli} publish --to {target}`")
        con.execute(f"ATTACH {literal(target)} AS published (READ_ONLY)")
        tables = {name for (name,) in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE database_name = 'published' AND schema_name = 'main'"
        ).fetchall()}
        result = {}
        for view in spec.contract.descriptions():
            here = fingerprint(con, f"memory.{view}")
            there = fingerprint(con, f"published.main.{view}") if view in tables else None
            result[view] = (here[0], there and there[0], here == there)
        return result
    finally:
        con.close()


def fingerprint(con: duckdb.DuckDBPyConnection, table: str) -> tuple[int, int]:
    """Rows, and the sum of their hashes."""
    return con.execute(f"SELECT count(*), coalesce(sum(hash(t)::HUGEINT), 0) FROM {table} t").fetchone()


def _target(spec: AppSpec, target: str | None) -> str:
    target = target or spec.motherduck_target
    if not target:
        raise ValueError("no target: pass --to md:<name> (this app sets no motherduck_target)")
    return target


def _attach(spec: AppSpec, con: duckdb.DuckDBPyConnection, target: str) -> str:
    """Attach `target` for writing; returns its catalog name."""
    if target.startswith("md:"):
        name = target.removeprefix("md:")
        if not name:
            raise ValueError("name the MotherDuck database: md:<name>")
        motherduck(spec, con)
        con.execute("ATTACH 'md:'")
        con.execute(f'CREATE DATABASE IF NOT EXISTS "{name}"')
        return name
    con.execute(f"ATTACH {literal(target)} AS published")
    return "published"
