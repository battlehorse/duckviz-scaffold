"""Demo databases: building one, and telling one apart from the real database, wherever its file is.

A demo database (synthetic data, for screenshots and demos) holds the marker table `demo_params`: the parameters
it was built from. The marker is the only test: where the file is doesn't count. Commands that send or curate the
user's own data refuse a demo database (`publish` does).

`build_demo` writes one: the app's `connect` creates the schema, the app's `fill` writes the made-up data, and
`build_demo` adds the marker. It only ever replaces an earlier demo database, and deletes a half-built file.
"""

from collections.abc import Callable
from pathlib import Path

import duckdb

from duckkit.spec import AppSpec

MARKER = "demo_params"


def has_marker(con: duckdb.DuckDBPyConnection) -> bool:
    """Whether this open database holds the demo marker table."""
    return bool(con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = ?", [MARKER]).fetchone()[0])


def is_demo(spec: AppSpec, path: Path | None = None) -> bool:
    """Whether the database at `path` (default: spec.db_path) holds the demo marker. False for a missing file or one
    that isn't a database."""
    return _holds_marker(path or spec.db_path)


def params(con: duckdb.DuckDBPyConnection) -> str | None:
    """The parameters a demo database was built from (the text `build_demo` stored), or None if it isn't one."""
    if not has_marker(con):
        return None
    row = con.execute(f"SELECT * FROM {MARKER} LIMIT 1").fetchone()
    return str(row[0]) if row else ""


def build_demo(spec: AppSpec, connect: Callable[[Path], duckdb.DuckDBPyConnection],
               fill: Callable[[duckdb.DuckDBPyConnection], None], params: str, path: Path | None = None) -> Path:
    """Build a demo database at `path` (default: spec.demo_db_path) and return its path.

    `connect(path)` opens a new database with the app's schema (its db/store.py); `fill(con)` writes the made-up
    data; `params` is the text that rebuilds it (TOML, say), stored in the marker table. An existing file at `path`
    is replaced only if it is a demo database: never the real database, nor any other file. If anything fails, the
    half-built file is deleted.
    """
    path = path or spec.demo_db_path
    if path is None:
        raise ValueError("this app has no demo database (spec.demo_file)")
    if path.resolve() == spec.db_path.resolve():
        raise ValueError(f"{path} is your database: choose another path for the demo")
    if path.exists():
        if not is_demo(spec, path):
            raise ValueError(f"{path} exists and isn't a demo database: choose another path")
        _delete(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with connect(path) as con:
            fill(con)
            con.execute(f"CREATE TABLE {MARKER} (params VARCHAR NOT NULL)")
            con.execute(f"INSERT INTO {MARKER} VALUES (?)", [params])
    except BaseException:
        _delete(path)
        raise
    return path


def _holds_marker(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        with duckdb.connect(str(path), read_only=True) as con:
            return has_marker(con)
    except duckdb.Error:
        return False


def _delete(path: Path) -> None:
    path.unlink(missing_ok=True)
    path.with_name(path.name + ".wal").unlink(missing_ok=True)
