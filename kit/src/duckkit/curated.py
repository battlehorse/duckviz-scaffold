"""Curated decisions: the tables people (or a model) decide, kept as CSV files in curated/ and committed to git.

The rest of the database comes again from the source files, but a decision costs time or money to make. The database
is the source of truth: the commands change it, and the app reads it. curated/*.csv is its backup in git:
- **write path:** every command that changes a decision runs inside `curating`, which exports the curated tables to
  curated/<table>.csv after the command, and after a failure too. The caller can't forget it. The files are sorted,
  so a git diff shows exactly which decisions changed.
- **read path:** `restore` loads the files into a rebuilt database, at the end of its `ingest`. Nothing else reads
  them.
- **guardrails:** a database with no decisions never overwrites files that hold some (`export`). Git keeps every
  version, and `file_changes` (the `curated-check` command, in the pre-commit hook) stops a commit that loses many
  decisions. A demo database is refused (`Refused`).

The files hold the user's decisions: a repo with curations stays private (`doctor --remote` checks).

A curated table is one of two kinds:
- **its own rows** (no `key`): the decisions are the rows, made by the commands (a merchant's category). `restore`
  inserts them.
- **decisions on rows the ingestion makes** (`key`): the ingestion adds the rows, a command fills in some columns (a
  SKU's product). `where` picks the rows that hold a decision, and `restore` updates the rows by `key`. A key the
  database doesn't have yet (its source file isn't ingested) is skipped.
"""

import csv
import io
import subprocess
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import duckdb

from duckkit.demo import is_demo
from duckkit.snapshot import literal
from duckkit.spec import AppSpec


class Refused(ValueError):
    """The decisions of this database must not reach curated/: it is a demo database."""


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
    are no files). A text column keeps an empty text ("" in the file) apart from a NULL (an empty field). A file
    without a column (written before the column existed) restores it as NULL; a missing file is skipped.
    `after(con)` runs inside the transaction: whatever the app derives from the decisions.
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
        raise Refused(f"{spec.db_path} is a demo database: commands that change decisions work on your own database"
                      f" only (`{spec.cli} demo` rebuilds the demo)")
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
    # Quoted values stay text: COPY writes an empty text as "" and a NULL as nothing, so the two stay apart.
    source = f"read_csv({literal(str(path))}, header = true, all_varchar = true, allow_quoted_nulls = false)"
    types = dict(con.execute("""
        SELECT column_name, data_type FROM duckdb_columns()
        WHERE database_name = current_database() AND schema_name = current_schema() AND table_name = ?
    """, [table.name]).fetchall())
    in_file = {c for (c,) in con.execute(f"SELECT column_name FROM (DESCRIBE SELECT * FROM {source})").fetchall()}

    def value(column: str) -> str:
        if column not in in_file:
            return f"CAST(NULL AS {types[column]})"
        if types[column] == "VARCHAR":
            return f"c.{column}"
        return f"CAST(nullif(c.{column}, '') AS {types[column]})"  # a hand-written "" in a date, say

    if table.key is None:
        cols = ", ".join(table.columns)
        sql = f"INSERT INTO {table.name} ({cols}) SELECT {', '.join(value(c) for c in table.columns)} FROM {source} c"
    else:
        if table.key not in in_file:
            raise ValueError(f"{path.name} has no {table.key} column")
        sets = ", ".join(f"{c} = {value(c)}" for c in table.columns if c != table.key)
        sql = f"UPDATE {table.name} t SET {sets} FROM {source} c WHERE t.{table.key} = {value(table.key)}"
    return con.execute(sql).fetchone()[0]


# ─── The git guard: what a commit does to the curated files ───

@dataclass(frozen=True)
class FileChange:
    """What a change does to one curated file: its rows (without the header) before and after, and the rows added
    and removed. A changed row counts as one removed and one added."""

    name: str
    before: int
    after: int
    added: int
    removed: int

    @property
    def loses_many(self) -> bool:
        """The file is emptied, or loses more than 5 rows and more than a tenth of them: that is rarely a decision."""
        lost = self.before - self.after
        return (self.before > 0 and self.after == 0) or (lost > 5 and lost > self.before / 10)

    def line(self) -> str:
        return f"{self.name}: {self.before} → {self.after} rows (+{self.added}, −{self.removed})"


def file_changes(spec: AppSpec, base: str | None = None) -> list[FileChange]:
    """The curated files that a change touches, with their rows before and after.

    Without `base`, it compares the staged files with HEAD: what the next commit does (the pre-commit hook). With
    `base` (a branch, say), it compares the working tree with the point where the branch left `base`: what a PR does.
    It raises ValueError when git can't answer (an unknown `base`, not a git repo)."""
    folder = spec.curated_dir.relative_to(spec.root).as_posix()
    if base is None:
        before_ref = "HEAD" if _git(spec, "rev-parse", "--verify", "-q", "HEAD^{commit}", check=False) else None
        names = set(_git(spec, "ls-files", "--", f"{folder}/").splitlines())
    else:
        if not _git(spec, "rev-parse", "--verify", "-q", f"{base}^{{commit}}", check=False):
            raise ValueError(f"{base} is not a branch or commit of this repo")
        before_ref = _git(spec, "merge-base", base, "HEAD").strip()
        names = {f"{folder}/{p.name}" for p in spec.curated_dir.glob("*.csv")}
    if before_ref:  # the first commit has nothing before it
        names |= set(_git(spec, "ls-tree", "-r", "--name-only", before_ref, "--", f"{folder}/").splitlines())
    changes = []
    for path in sorted(n for n in names if n.endswith(".csv")):
        old = _records(_git(spec, "show", f"{before_ref}:{path}", check=False) if before_ref else None)
        new = _records(_git(spec, "show", f":{path}", check=False) if base is None else _file_text(spec.root / path))
        if old == new:
            continue
        added, removed = Counter(new) - Counter(old), Counter(old) - Counter(new)
        changes.append(FileChange(Path(path).name, len(old), len(new), sum(added.values()), sum(removed.values())))
    return changes


def _records(text: str | None) -> list[tuple[str, ...]]:
    """The records of a CSV's text, without its header. A quoted field may hold line breaks (a note)."""
    if not text:
        return []
    return [tuple(record) for record in csv.reader(io.StringIO(text))][1:]


def _git(spec: AppSpec, *args: str, check: bool = True) -> str:
    """git's output. With `check`, a failure raises ValueError. Without, a failure gives "" (a file or a commit that
    doesn't exist)."""
    done = subprocess.run(["git", *args], cwd=spec.root, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        if check:
            raise ValueError(f"git {' '.join(args)} failed: {done.stderr.strip()}")
        return ""
    return done.stdout


def _file_text(path: Path) -> str | None:
    return path.read_text() if path.exists() else None
