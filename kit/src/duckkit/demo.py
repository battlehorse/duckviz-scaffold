"""Telling a demo database apart from the real one, wherever its file is.

A demo database (synthetic data, for screenshots and demos) holds the marker table `demo_params`: the parameters
it was built from. Commands that send or curate the user's own data refuse one (`publish` does). The file at
`spec.demo_db_path` counts as a demo database too, marker or not.
"""

from pathlib import Path

import duckdb

from duckkit.spec import AppSpec

MARKER = "demo_params"


def has_marker(con: duckdb.DuckDBPyConnection) -> bool:
    """Whether this open database holds the demo marker table."""
    return bool(con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = ?", [MARKER]).fetchone()[0])


def is_demo(spec: AppSpec, path: Path | None = None) -> bool:
    """Whether the database at `path` (default: spec.db_path) is a demo one. False for a missing file or one that
    isn't a database."""
    path = path or spec.db_path
    if spec.demo_db_path and path.resolve() == spec.demo_db_path.resolve():
        return True
    if not path.exists():
        return False
    try:
        with duckdb.connect(str(path), read_only=True) as con:
            return has_marker(con)
    except duckdb.Error:
        return False
