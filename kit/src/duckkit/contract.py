"""A data contract: its reference schema, the descriptions in its comments, and a conformance check.

The reference schema (`contract/schema.sql` of each app) declares every view as a table of the same name, with
its types, PRIMARY KEY and NOT NULL. Loading it into an empty database gives the contract's exact shape. A comment
block right above a CREATE TABLE describes the view; the comment after a column describes the column.

`v_contract` has one row: the contract's name and version. A minor version only adds views or columns; a major one
renames or removes something. Readers accept the same major version.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.resources.abc import Traversable
from pathlib import Path

import duckdb

# (query counting the rows that break a rule, message with {n})
Rule = tuple[str, str]
# A check of its own: the problems it finds, one short message each
Check = Callable[[duckdb.DuckDBPyConnection], list[str]]


def enum_rule(view: str, column: str, values: list[str] | tuple[str, ...]) -> Rule:
    """A rule: `column` of `view` holds only `values` (NULL is left to NOT NULL)."""
    listed = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    return (f"SELECT count(*) FROM {view} WHERE {column} NOT IN ({listed})",
            f"{view}.{column}: {{n}} rows outside {', '.join(values)}")


def relation_rule(view: str, column: str, parent: str, parent_column: str | None = None) -> Rule:
    """A rule: every `column` of `view` exists in `parent` (a foreign key the views promise)."""
    parent_column = parent_column or column
    return ((f"SELECT count(*) FROM {view} WHERE {column} IS NOT NULL"
            f" AND {column} NOT IN (SELECT {parent_column} FROM {parent})"),
            f"{view}.{column}: {{n}} rows with no match in {parent}.{parent_column}")


@dataclass(eq=False)
class Contract:
    """One app's contract. `schema` is the reference schema file (e.g. files("app.contract") / "schema.sql")."""

    name: str
    version: str
    schema: Traversable | Path
    rules: list[Rule] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    prelude: str = ""  # SQL run before the reference schema (macros it uses, say)

    @property
    def major(self) -> str:
        return self.version.split(".")[0]

    def schema_sql(self) -> str:
        """The text of the reference schema."""
        return self.schema.read_text()

    def reference(self) -> duckdb.DuckDBPyConnection:
        """An empty in-memory database with the contract's exact shape (the app's tests fill one)."""
        con = duckdb.connect(":memory:")
        if self.prelude:
            con.execute(self.prelude)
        con.execute(self.schema_sql())
        return con

    def views(self) -> list[str]:
        """The contract's views, in the reference schema's order."""
        return list(self.descriptions())

    def columns(self) -> dict[str, list[str]]:
        """Each view's columns, in the reference schema's order."""
        columns: dict[str, list[str]] = {}
        for view, column in self.reference().execute("""
            SELECT table_name, column_name FROM information_schema.columns ORDER BY table_name, ordinal_position
        """).fetchall():
            columns.setdefault(view, []).append(column)
        return columns

    def descriptions(self) -> dict[str, tuple[str, dict[str, str]]]:
        """Each view's description and its columns' ({view: (description, {column: description})}), from the
        reference schema's comments.

        A view's description is the block of comment lines right above its CREATE TABLE; a column's is the
        comment after it on its line, joined with any comment-only lines below it.
        """
        views: dict[str, tuple[str, dict[str, str]]] = {}
        block: list[str] = []  # comment lines since the last blank or code line, outside a table
        columns: dict[str, str] | None = None  # the table being read
        column = None
        for line in self.schema_sql().splitlines():
            code, _, comment = (part.strip() for part in line.partition("--"))
            if columns is None:
                if m := re.match(r"CREATE TABLE (\w+)", code):
                    columns = {}
                    views[m[1]] = (" ".join(block), columns)
                elif comment and not code:
                    block.append(comment)
                else:
                    block = []
            elif code.startswith(")"):
                columns, column, block = None, None, []
            elif code:
                column = None if code.startswith(("PRIMARY KEY", "UNIQUE", "CHECK")) else code.split()[0]
                if column:
                    columns[column] = comment
            elif column and comment:
                columns[column] += " " + comment
        return views

    def check(self, con: duckdb.DuckDBPyConnection) -> list[str]:
        """The problems with the contract views of `con`, one short message each; empty when it conforms."""
        ref = self.reference()
        problems = self._shape(con, ref)
        if problems:  # the other checks need every view and column
            return problems
        for view, kind, columns in ref.execute("""
            SELECT table_name, constraint_type, constraint_column_names FROM duckdb_constraints()
            WHERE constraint_type IN ('PRIMARY KEY', 'NOT NULL') ORDER BY table_name, constraint_index
        """).fetchall():
            if kind == "PRIMARY KEY":
                keys = ", ".join(columns)
                n = _count(con, f"SELECT count(*) FROM (SELECT {keys} FROM {view} GROUP BY ALL HAVING count(*) > 1)")
                problems += [f"{view}: {n} duplicate keys ({keys})"] if n else []
            else:
                n = _count(con, f"SELECT count(*) FROM {view} WHERE {columns[0]} IS NULL")
                problems += [f"{view}.{columns[0]}: {n} NULLs"] if n else []
        problems += [message.format(n=n) for sql, message in self.rules if (n := _count(con, sql))]
        for check in self.checks:
            problems += check(con)
        return problems + self._version(con)

    def accepts(self, name: str, version: str) -> bool:
        """Whether a database offering contract `name` `version` is one this code reads (same name and major)."""
        return name == self.name and str(version).split(".")[0] == self.major

    def _shape(self, con: duckdb.DuckDBPyConnection, ref: duckdb.DuckDBPyConnection) -> list[str]:
        """Every view of the reference schema exists with every column, by name and type. Extra columns are fine."""
        expected = ref.execute(_COLUMNS).fetchall()
        actual = {(view, column): type_ for view, column, type_ in con.execute(_COLUMNS).fetchall()}
        present = {view for view, _ in actual}
        views = dict.fromkeys(view for view, _, _ in expected)
        problems = [f"{view}: missing" for view in views if view not in present]
        for view, column, type_ in expected:
            if view not in present:
                continue
            if (view, column) not in actual:
                problems.append(f"{view}.{column}: missing")
            elif actual[view, column] != type_:
                problems.append(f"{view}.{column}: {actual[view, column]}, expected {type_}")
        return problems

    def _version(self, con: duckdb.DuckDBPyConnection) -> list[str]:
        """v_contract has one row, with this contract's name and major version. A minor version may differ."""
        rows = con.execute("SELECT contract, version FROM v_contract").fetchall()
        if len(rows) != 1:
            return [f"v_contract: {len(rows)} rows, expected 1"]
        if not self.accepts(*rows[0]):
            return [f"v_contract: {rows[0][0]} {rows[0][1]}, expected {self.name} {self.major}.x"]
        return []


_COLUMNS = """
    SELECT table_name, column_name, data_type FROM information_schema.columns
    WHERE table_catalog = current_database() AND table_schema = current_schema()
    ORDER BY table_name, ordinal_position
"""


def _count(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    """The single number that `sql` returns."""
    return con.execute(sql).fetchone()[0]
