"""Backups: the whole database exported as Parquet, one folder per snapshot, checked after writing.

`backup` exports the database with EXPORT DATABASE (Parquet files + schema.sql + load.sql: readable by any Parquet
tool, independent of the DuckDB version), imports the export into an in-memory database and compares every table's
rows and content with the source, then keeps the newest `keep` snapshots. `restore` rebuilds a database file from
a snapshot, and never overwrites one.

The folder is spec.backup_dir() (`[backup] dir` in config.toml or <PREFIX>_BACKUP_DIR; default backups/, which
the template's .gitignore excludes).
"""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from duckkit.snapshot import literal
from duckkit.spec import AppSpec
from duckkit.store import tables


class BackupError(RuntimeError):
    """A snapshot doesn't match the database it was taken from."""


def backup(spec: AppSpec, con: duckdb.DuckDBPyConnection, folder: Path | None = None,
           keep: int | None = None) -> Path:
    """Export `con`'s database to a new snapshot folder, verify it, prune old ones. Returns the snapshot."""
    folder = folder or spec.backup_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{spec.backup_prefix}{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    con.execute(f"EXPORT DATABASE {literal(str(target))} (FORMAT parquet)")
    _order_schema(target / "schema.sql")
    problems = verify(spec, target, counts(con))
    if problems:
        raise BackupError(f"{target.name}: " + "; ".join(problems))
    prune(spec, folder, keep if keep is not None else spec.backup_keep())
    return target


def _order_schema(path: Path) -> None:
    """Rewrite an exported schema.sql so that each statement comes after what it reads.

    EXPORT DATABASE writes every macro before every view. A macro that reads a view (or a view that reads a view
    made later) then fails on import. This finds an order that works, by running the statements in an empty
    database and moving each one that fails after the others, until all of them run."""
    with duckdb.connect(":memory:") as con:
        waiting = [s.query for s in con.extract_statements(path.read_text())]
        done: list[str] = []
        while waiting:
            failed = []
            for statement in waiting:
                try:
                    con.execute(statement)
                    done.append(statement)
                except duckdb.CatalogException:  # it reads something not made yet
                    failed.append(statement)
            if len(failed) == len(waiting):  # no progress: a real error, which the import reports
                done += failed
                break
            waiting = failed
    path.write_text("".join(f"{statement};\n" for statement in done))


def counts(con: duckdb.DuckDBPyConnection) -> dict[str, tuple[int, int]]:
    """Rows and a content fingerprint (sum of row hashes) per table."""
    return {t: con.execute(f"SELECT count(*), coalesce(sum(hash(x)::HUGEINT), 0) FROM {t} x").fetchone()
            for t in tables(con)}


def verify(spec: AppSpec, snapshot: Path, expected: dict[str, tuple[int, int]] | None = None) -> list[str]:
    """Import `snapshot` into memory; the differences from `expected` (or, without it, just that it loads)."""
    with duckdb.connect(":memory:") as con:
        if spec.timezone:
            con.execute(f"SET TimeZone = {literal(spec.timezone)}")
        con.execute(f"IMPORT DATABASE {literal(str(snapshot))}")
        found = counts(con)
    if expected is None:
        return []
    return [f"{t}: {found.get(t)} rows/hash, expected {want}" for t, want in expected.items() if found.get(t) != want]


def snapshots(spec: AppSpec, folder: Path | None = None) -> list[Path]:
    """Snapshot folders, oldest first."""
    folder = folder or spec.backup_dir()
    return sorted(p for p in folder.glob(f"{spec.backup_prefix}*") if p.is_dir()) if folder.exists() else []


def prune(spec: AppSpec, folder: Path, keep: int) -> list[Path]:
    """Delete all but the newest `keep` snapshots in `folder` (keep 0: delete none). Returns the deleted ones."""
    old = snapshots(spec, folder)[:-keep] if keep > 0 else []
    for path in old:
        shutil.rmtree(path)
    return old


def restore(spec: AppSpec, snapshot: Path, db_path: Path) -> dict[str, tuple[int, int]]:
    """Build a new database file at `db_path` from `snapshot`. Refuses to overwrite an existing file."""
    if db_path.exists():
        raise FileExistsError(f"{db_path} exists: move it away first (restore never overwrites a database)")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        if spec.timezone:
            con.execute(f"SET TimeZone = {literal(spec.timezone)}")
        con.execute(f"IMPORT DATABASE {literal(str(snapshot))}")
        return counts(con)
