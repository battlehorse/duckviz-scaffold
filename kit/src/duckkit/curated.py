"""Curated decisions: the tables people (or a model) decide, kept as CSV files in curated/ and committed to git.

The rest of the database comes again from the source files, but a decision costs time or money to make. So every
command that changes one runs inside `curating`, which writes the curated tables to curated/<table>.csv after it,
even when the command fails. `restore` loads the files back into a rebuilt database. The files are sorted, so a git
diff shows exactly which decisions changed. They hold the user's decisions: a repo with curations stays private
(`doctor --remote` checks).

A curated table is one of two kinds:
- **its own rows** (no `key`): the decisions are the rows, made by the commands (a merchant's category). `restore`
  inserts them.
- **decisions on rows the ingestion makes** (`key`): the ingestion adds the rows, a command fills in some columns (a
  SKU's product). `where` picks the rows that hold a decision, and `restore` updates the rows by `key`; a key the
  database doesn't have yet (its source file isn't ingested) is skipped.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import duckdb

from duckkit.demo import is_demo
from duckkit.snapshot import literal
from duckkit.spec import AppSpec


@dataclass(frozen=True)
class CuratedTable:
    """A table whose decisions are kept in curated/<name>.csv."""

    name: str
    columns: tuple[str, ...]  # what is exported and restored; with `key`, the key comes first
    order_by: str  # the file's order, so diffs stay small: a unique key
    where: str | None = None  # only rows that hold a decision (SQL); None: every row
    key: str | None = None  # set: restore updates the ingestion's rows by this column instead of inserting

    def __post_init__(self):
        if self.key and self.key not in self.columns:
            raise ValueError(f"{self.name}: the key {self.key} must be one of the columns")


def not_manual(column: str = "classified_by") -> str:
    """SQL that is true for a decision a model may redo: anything not made by hand ('manual')."""
    return f"{column} IS DISTINCT FROM 'manual'"


def holds_decisions(con: duckdb.DuckDBPyConnection, tables: list[CuratedTable]) -> bool:
    """Whether the database holds any curated decision."""
    return any(_count(con, t) for t in tables)


def export(con: duckdb.DuckDBPyConnection, directory: Path, tables: list[CuratedTable],
           removed: bool = False) -> bool:
    """Write each table to `directory`/<name>.csv, sorted. Each file is replaced atomically.

    A database with no decisions at all (new, or rebuilt and not restored yet) never replaces files that hold some:
    returns False and writes nothing. Unless `removed`: the decisions were there and a command removed them (what
    `curating` passes when the database held decisions as the command began).
    """
    files = [directory / f"{t.name}.csv" for t in tables]
    if not removed and not holds_decisions(con, tables) and any(_has_rows(f) for f in files):
        return False
    directory.mkdir(parents=True, exist_ok=True)
    for table, target in zip(tables, files):
        tmp = target.with_name(f".{target.name}.tmp")
        con.execute(f"COPY ({_select(table)} ORDER BY {table.order_by}) TO {literal(str(tmp))} (HEADER)")
        tmp.replace(target)
    return True


def restore(con: duckdb.DuckDBPyConnection, directory: Path, tables: list[CuratedTable],
            after: Callable[[duckdb.DuckDBPyConnection], None] | None = None) -> dict[str, int] | None:
    """Load curated/*.csv into a database that holds no decisions yet, in one transaction. Run it at the end of the
    ingestion, once the rows that keyed tables update exist.

    Returns the rows restored per table, or None when there was nothing to do (the database holds decisions, or there
    are no files). A file without a column (written before the column existed) restores it empty; a missing file is
    skipped. `after(con)` runs inside the transaction: whatever the app derives from the decisions.
    """
    files = {t.name: directory / f"{t.name}.csv" for t in tables}
    present = [t for t in tables if files[t.name].exists()]
    if not present or holds_decisions(con, tables):
        return None
    con.begin()
    try:
        counts = {t.name: _load(con, t, files[t.name]) for t in present}
        if after:
            after(con)
        con.commit()
    except BaseException:
        con.rollback()
        raise
    return counts


@contextmanager
def curating(spec: AppSpec, connect: Callable[[], duckdb.DuckDBPyConnection], tables: list[CuratedTable],
             directory: Path | None = None) -> Iterator[duckdb.DuckDBPyConnection]:
    """A connection for a command that changes decisions: exports them to curated/ after it, and after a failure too
    (earlier batches may be committed). Refuses a demo database: its decisions must never reach curated/."""
    if is_demo(spec):
        raise ValueError(f"{spec.db_path} is a demo database: commands that change decisions work on your own "
                         "database only")
    directory = directory or spec.curated_dir
    with connect() as con:
        held = holds_decisions(con, tables)  # then an empty export is a removal, not a database without decisions
        try:
            yield con
        except BaseException:
            try:
                con.rollback()  # drop a half-finished transaction before exporting
            except duckdb.TransactionException:
                pass  # none open
            export(con, directory, tables, removed=held)
            raise
        export(con, directory, tables, removed=held)


def _select(table: CuratedTable) -> str:
    return f"SELECT {', '.join(table.columns)} FROM {table.name}" + (f" WHERE {table.where}" if table.where else "")


def _count(con: duckdb.DuckDBPyConnection, table: CuratedTable) -> int:
    return con.execute(f"SELECT count(*) FROM ({_select(table)})").fetchone()[0]


def _has_rows(path: Path) -> bool:
    """Whether a CSV has a row under its header."""
    if not path.exists():
        return False
    with path.open() as f:
        return sum(1 for _ in zip(range(2), f)) > 1


def _load(con: duckdb.DuckDBPyConnection, table: CuratedTable, path: Path) -> int:
    source = f"read_csv({literal(str(path))}, header = true, all_varchar = true)"
    types = dict(con.execute("""
        SELECT column_name, data_type FROM duckdb_columns()
        WHERE database_name = current_database() AND schema_name = current_schema() AND table_name = ?
    """, [table.name]).fetchall())
    in_file = {c for (c,) in con.execute(f"SELECT column_name FROM (DESCRIBE SELECT * FROM {source})").fetchall()}

    def value(column: str) -> str:
        if column not in in_file:
            return f"CAST(NULL AS {types[column]})"
        return f"CAST(nullif(c.{column}, '') AS {types[column]})"

    if table.key is None:
        cols = ", ".join(table.columns)
        sql = f"INSERT INTO {table.name} ({cols}) SELECT {', '.join(value(c) for c in table.columns)} FROM {source} c"
    else:
        if table.key not in in_file:
            raise ValueError(f"{path.name} has no {table.key} column")
        sets = ", ".join(f"{c} = {value(c)}" for c in table.columns if c != table.key)
        sql = f"UPDATE {table.name} t SET {sets} FROM {source} c WHERE t.{table.key} = {value(table.key)}"
    return con.execute(sql).fetchone()[0]
