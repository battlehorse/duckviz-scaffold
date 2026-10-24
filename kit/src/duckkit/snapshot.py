"""Read-only snapshots of the database: the contract's views for the browser app, everything for the service.

The browser app reads the views of its data contract and nothing else, so its snapshot holds only those, with only
the columns of the reference schema. `sql` and `status` belong to the ingestion service and take a database
snapshot. Either way the real file is attached read-only just long enough to copy it, so no lock is held
afterwards: `ingest` keeps working while the app is open.
"""

from pathlib import Path

import duckdb

from duckkit.spec import AppSpec


class ContractError(RuntimeError):
    """The database doesn't offer the contract the browser app reads (missing, older or newer views)."""


def contract_snapshot(spec: AppSpec, source: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """An in-memory copy of the contract's views, for the browser app.

    `source` is a database file or a MotherDuck database ("md:<name>", as `publish` writes it); by default
    `spec.app_db` when set (a hosted app), else the local database. Refuses a database whose contract has another
    name or major version (ContractError). Each view becomes a table of the same name with only the reference
    schema's columns, so a query naming anything else fails. External access is off: it can't read or write files.
    """
    con = contract_copy(spec, source or spec.app_db)
    con.execute("SET enable_external_access = false")
    return con


def contract_copy(spec: AppSpec, source: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """`contract_snapshot` with external access still on, for `publish` to attach where it sends the copy.
    `source` defaults to the local database."""
    con = attach(spec, source)
    try:
        _check_version(spec, con)
        for view, columns in spec.contract.columns().items():
            try:
                con.execute(f"CREATE TABLE memory.{view} AS SELECT {', '.join(columns)} FROM src.{view}")
            except duckdb.Error as e:  # a view or column missing: views older than the code
                raise ContractError(
                    f"the database's {view} doesn't match the app's contract ({e}). {spec.refresh_hint}") from e
    finally:
        con.execute("DETACH src")
    return con


def database_snapshot(spec: AppSpec, path: Path | None = None) -> duckdb.DuckDBPyConnection:
    """An in-memory copy of the whole database (tables and views), for `sql`, `status` and local-only apps.

    The copy can't change the real database, and external file access is switched off, so queries can't read or
    write files either. Take a new snapshot to see newer data.
    """
    con = attach(spec, path)
    con.execute("COPY FROM DATABASE src TO memory")
    con.execute("DETACH src")
    con.execute("SET enable_external_access = false")
    return con


def motherduck(spec: AppSpec, con: duckdb.DuckDBPyConnection) -> None:
    """Load the MotherDuck extension and sign in with the app's token."""
    token = spec.motherduck_token()
    if not token:
        raise ValueError(f"no MotherDuck token: create one in MotherDuck (Settings → Access tokens) and set"
                         f" {spec.where_token()}")
    con.execute("INSTALL motherduck")  # once: DuckDB downloads it to ~/.duckdb/extensions (a Cloud Run image has it)
    con.execute("LOAD motherduck")  # before SET: the token is the extension's setting
    con.execute(f"SET motherduck_token = {literal(token)}")


def attach(spec: AppSpec, source: Path | str | None) -> duckdb.DuckDBPyConnection:
    """An in-memory database with `source` attached read-only as `src`. `source` is a MotherDuck database
    ("md:<name>"), a DuckDB file, or None for the local database."""
    if isinstance(source, str) and source.startswith("md:"):  # the published copy: tables named like the views
        con = memory(spec)
        motherduck(spec, con)
        con.execute(f"ATTACH {literal(source)} AS src (READ_ONLY)")
        return con
    path = Path(source) if source else spec.db_path
    if not path.exists():
        raise FileNotFoundError(f"no database at {path}: run `/ingest` in Claude Code (or `{spec.cli} ingest`) first")
    con = memory(spec)
    con.execute(f"ATTACH {literal(str(path))} AS src (READ_ONLY)")
    return con


def memory(spec: AppSpec) -> duckdb.DuckDBPyConnection:
    """An empty in-memory database, in the app's time zone."""
    con = duckdb.connect(":memory:")
    if spec.timezone:
        con.execute(f"SET TimeZone = {literal(spec.timezone)}")
    return con


def literal(text: str) -> str:
    """A SQL string literal (ATTACH, SET, COMMENT ON, EXPORT and IMPORT take no bound parameters)."""
    return "'" + text.replace("'", "''") + "'"


def _check_version(spec: AppSpec, con: duckdb.DuckDBPyConnection) -> None:
    """The database implements the contract's name and major version (a newer minor version only adds)."""
    contract = spec.contract
    try:
        rows = con.execute("SELECT contract, version FROM src.v_contract").fetchall()
    except duckdb.Error as e:
        raise ContractError(f"the database has no v_contract view: it predates the app's contract. {spec.refresh_hint}") from e
    if len(rows) != 1 or not contract.accepts(*rows[0]):
        found = ", ".join(f"{name} {version}" for name, version in rows) or "nothing"
        raise ContractError(f"the database offers {found}; this app reads {contract.name} {contract.major}.x."
                            f" {spec.refresh_hint}")
