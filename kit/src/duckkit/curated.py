"""Curated decisions: the tables people (or a model) decide, kept as CSV files in curated/ and committed to git.

The rest of the database comes again from the source files, but a decision costs time or money to make. So every
command that changes one runs inside `curating`, which writes the curated tables to curated/<table>.csv after it,
even when the command fails. `ingest` calls `restore`, which loads into the database the decisions that curated/
holds and the database lacks. The files are sorted, so a git diff shows exactly which decisions changed. They hold
the user's decisions: a repo with curations stays private (`doctor --remote` checks).

A curated table is one of two kinds:
- **its own rows** (no `key`): the decisions are the rows, made by the commands (a merchant's category). `restore`
  inserts each row of the file whose unique key (`order_by`) the table doesn't have.
- **decisions on rows the ingestion makes** (`key`): the ingestion adds the rows, a command fills in some columns (a
  SKU's product). `where` picks the rows that hold a decision. `restore` puts each decision on the row with its key,
  when that row holds none. A decision whose key the database doesn't have (its source isn't ingested) waits in the
  file: the export keeps it, and a later `ingest` restores it.

Nothing that curated/ holds is lost on the way:
- `curating` refuses a command while the database lacks decisions that curated/ could restore (a rebuilt database
  before `ingest`). Only `ingest` may run then, because it restores them.
- `export` never writes a table while it lacks restorable decisions, unless the table held decisions before the
  command: then the command removed them.
"""

from collections.abc import Callable, Collection, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import duckdb

from duckkit.demo import is_demo
from duckkit.snapshot import literal
from duckkit.spec import AppSpec


class Refused(ValueError):
    """A command that changes decisions can't run on this database. The message says why, and what to do."""


@dataclass(frozen=True)
class CuratedTable:
    """A table whose decisions are kept in curated/<name>.csv."""

    name: str
    columns: tuple[str, ...]  # what is exported and restored; with `key`, the key comes first
    order_by: str  # the columns of a unique key, comma-separated: the file's order (so diffs stay small)
    where: str | None = None  # only rows that hold a decision (SQL); None: every row
    key: str | None = None  # set: restore updates the ingestion's rows by this column instead of inserting

    def __post_init__(self):
        if self.key and self.key not in self.columns:
            raise ValueError(f"{self.name}: the key {self.key} must be one of the columns")
        if self.key and not self.where:
            raise ValueError(f"{self.name}: a keyed table needs `where`, the rows that hold a decision")
        if missing := [c for c in self.unique_key if c not in self.columns]:
            raise ValueError(f"{self.name}: order_by names {', '.join(missing)}, which are not columns")

    @property
    def unique_key(self) -> tuple[str, ...]:
        """The columns of `order_by`: they tell one row from another."""
        return tuple(c.strip() for c in self.order_by.split(","))


def not_manual(column: str = "classified_by") -> str:
    """SQL that is true for a decision a model may redo: anything not made by hand ('manual')."""
    return f"{column} IS DISTINCT FROM 'manual'"


def holds_decisions(con: duckdb.DuckDBPyConnection, tables: list[CuratedTable]) -> bool:
    """Whether the database holds any curated decision."""
    return any(_count(con, t) for t in tables)


def restorable(con: duckdb.DuckDBPyConnection, directory: Path, tables: list[CuratedTable]) -> dict[str, int]:
    """The decisions in `directory` that `restore` would load into this database, per table (tables with none are
    left out)."""
    counts = {}
    for table in tables:
        path = directory / f"{table.name}.csv"
        if path.exists() and (count := _restorable(con, table, path)):
            counts[table.name] = count
    return counts


def export(con: duckdb.DuckDBPyConnection, directory: Path, tables: list[CuratedTable],
           held_before: Collection[str] = ()) -> bool:
    """Write each table to `directory`/<name>.csv, sorted. Each file is replaced atomically. Returns True when it
    wrote every table.

    - A table that lacks decisions its file could restore is not written, unless its name is in `held_before`: it
      held decisions before the command, so the command removed them. `curating` passes the tables that held
      decisions as the command began.
    - A keyed table keeps the file's decisions whose key the database doesn't have: they wait for their source.
    """
    directory.mkdir(parents=True, exist_ok=True)
    wrote_every_table = True
    for table in tables:
        target = directory / f"{table.name}.csv"
        if target.exists() and table.name not in held_before and _restorable(con, table, target):
            wrote_every_table = False
            continue
        rows = _select(table)
        if table.key and target.exists():
            waiting = _waiting_in_file(con, table, target)
            rows = f"SELECT * FROM ({rows}) UNION ALL {waiting}"
        tmp = target.with_name(f".{target.name}.tmp")
        con.execute(f"COPY (SELECT * FROM ({rows}) ORDER BY {table.order_by}) TO {literal(str(tmp))} (HEADER)")
        tmp.replace(target)
    return wrote_every_table


def restore(con: duckdb.DuckDBPyConnection, directory: Path, tables: list[CuratedTable],
            after: Callable[[duckdb.DuckDBPyConnection], None] | None = None) -> dict[str, int] | None:
    """Load the decisions that `directory` holds and the database lacks, in one transaction. Run it at the end of
    every ingestion, once the rows that keyed tables update exist.

    Returns the rows restored per table, or None when it restored nothing. A file without a column (written before
    the column existed) restores it empty. A missing file is skipped. `after(con)` runs inside the transaction when
    something was restored: whatever the app derives from the decisions.
    """
    con.begin()
    try:
        counts = {}
        for table in tables:
            path = directory / f"{table.name}.csv"
            if path.exists() and _restorable(con, table, path) and (loaded := _load(con, table, path)):
                counts[table.name] = loaded
        if counts and after:
            after(con)
        con.commit()
    except BaseException:
        con.rollback()
        raise
    return counts or None


@contextmanager
def curating(spec: AppSpec, connect: Callable[[], duckdb.DuckDBPyConnection], tables: list[CuratedTable],
             directory: Path | None = None, restores: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    """A connection for a command that changes decisions. It exports them to curated/ after the command, and after a
    failure too (earlier batches may be committed).

    It raises `Refused` for a demo database: its decisions must never reach curated/. It also raises `Refused` while
    the database lacks decisions that curated/ could restore, unless `restores` is True. Only `ingest` passes True:
    it calls `restore` before the export.
    """
    if is_demo(spec):
        raise Refused(f"{spec.db_path} is a demo database: commands that change decisions work on your own database"
                      f" only (`{spec.cli} demo` rebuilds the demo)")
    directory = directory or spec.curated_dir
    with connect() as con:
        missing = restorable(con, directory, tables)
        if missing and not restores:
            listed = ", ".join(f"{n} in {name}" for name, n in missing.items())
            raise Refused(f"{directory.name}/ holds decisions that the database lacks ({listed}): run "
                          f"`{spec.cli} ingest` first, which restores them")
        held = {t.name for t in tables if _count(con, t)} - set(missing)  # an unrestored table is not "held"
        try:
            yield con
        except BaseException:
            try:
                con.rollback()  # drop a half-finished transaction before exporting
            except duckdb.TransactionException:
                pass  # none open
            export(con, directory, tables, held_before=held)
            raise
        export(con, directory, tables, held_before=held)


def _select(table: CuratedTable) -> str:
    return f"SELECT {', '.join(table.columns)} FROM {table.name}" + (f" WHERE {table.where}" if table.where else "")


def _count(con: duckdb.DuckDBPyConnection, table: CuratedTable) -> int:
    return con.execute(f"SELECT count(*) FROM ({_select(table)})").fetchone()[0]


class _File:
    """A curated file, read as text, with each column cast to the table's type."""

    def __init__(self, con: duckdb.DuckDBPyConnection, table: CuratedTable, path: Path):
        self.table = table
        self.source = f"read_csv({literal(str(path))}, header = true, all_varchar = true)"
        self.types = dict(con.execute("""
            SELECT column_name, data_type FROM duckdb_columns()
            WHERE database_name = current_database() AND schema_name = current_schema() AND table_name = ?
        """, [table.name]).fetchall())
        self.columns = {c for (c,) in con.execute(f"SELECT column_name FROM (DESCRIBE SELECT * FROM {self.source})"
                                                  ).fetchall()}
        if table.key and table.key not in self.columns:
            raise ValueError(f"{path.name} has no {table.key} column")

    def value(self, column: str) -> str:
        """The SQL for a column of row `c`, typed. A column the file doesn't have is NULL."""
        if column not in self.columns:
            return f"CAST(NULL AS {self.types[column]})"
        return f"CAST(nullif(c.{column}, '') AS {self.types[column]})"

    def select(self) -> str:
        return f"SELECT {', '.join(self.value(c) for c in self.table.columns)} FROM {self.source} c"

    def not_in_table(self) -> str:
        """SQL that is true when the table has no row with the file row's unique key."""
        same = " AND ".join(f"t.{c} IS NOT DISTINCT FROM {self.value(c)}" for c in self.table.unique_key)
        return f"NOT EXISTS (SELECT 1 FROM {self.table.name} t WHERE {same})"

    def key_in(self, rows: str) -> str:
        """SQL that is true when the file row's key is the key of one of `rows` (a SELECT of the table's key)."""
        return f"{self.value(self.table.key)} IN ({rows})"


def _undecided_keys(table: CuratedTable) -> str:
    """The keys of the table's rows that hold no decision."""
    return f"SELECT {table.key} FROM {table.name} WHERE ({table.where}) IS NOT TRUE"


def _restorable(con: duckdb.DuckDBPyConnection, table: CuratedTable, path: Path) -> int:
    """How many of the file's decisions `restore` would load: the rows the table doesn't have (its own rows), or the
    decisions on rows that hold none (keyed)."""
    file = _File(con, table, path)
    if table.key is None:
        return con.execute(f"SELECT count(*) FROM {file.source} c WHERE {file.not_in_table()}").fetchone()[0]
    return con.execute(f"SELECT count(*) FROM {file.source} c WHERE {file.key_in(_undecided_keys(table))}"
                       ).fetchone()[0]


def _waiting_in_file(con: duckdb.DuckDBPyConnection, table: CuratedTable, path: Path) -> str:
    """A SELECT of the file's decisions whose key the database doesn't have."""
    file = _File(con, table, path)
    return f"{file.select()} WHERE NOT {file.key_in(f'SELECT {table.key} FROM {table.name}')}"


def _load(con: duckdb.DuckDBPyConnection, table: CuratedTable, path: Path) -> int:
    """Load the file's restorable decisions: insert the rows the table doesn't have (its own rows), or update the
    rows that hold no decision (keyed)."""
    file = _File(con, table, path)
    if table.key is None:
        return con.execute(f"INSERT INTO {table.name} ({', '.join(table.columns)}) {file.select()}"
                           f" WHERE {file.not_in_table()}").fetchone()[0]
    sets = ", ".join(f"{c} = {file.value(c)}" for c in table.columns if c != table.key)
    return con.execute(f"""
        UPDATE {table.name} t SET {sets} FROM {file.source} c
        WHERE t.{table.key} = {file.value(table.key)} AND {file.key_in(_undecided_keys(table))}
    """).fetchone()[0]
