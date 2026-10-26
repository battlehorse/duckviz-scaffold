"""Test helpers for apps: isolation from the real data (`isolate`), a database with the contract's exact shape
(`contract_db`), and the guard rails that keep the browser app on the contract (`guard`)."""

from pathlib import Path

import duckdb

from duckkit.spec import AppSpec

PROTECTED_ENV = ("MOTHERDUCK_TOKEN",)


def isolate(spec: AppSpec, tmp_path: Path, monkeypatch, env: tuple[str, ...] = ()) -> None:
    """Point every default path of `spec` at `tmp_path` and unset the app's variables, so no test can touch the real
    data, settings or MotherDuck. Call it from an autouse fixture in tests/conftest.py."""
    monkeypatch.setattr(spec, "db_path", tmp_path / "test.duckdb")
    monkeypatch.setattr(spec, "data_dir", tmp_path / "data")
    monkeypatch.setattr(spec, "curated_dir", tmp_path / "curated")
    monkeypatch.setattr(spec, "config_path", tmp_path / "config.toml")
    monkeypatch.setattr(spec, "app_db", None)
    monkeypatch.setattr(spec, "version", None)
    monkeypatch.setenv(f"{spec.env_prefix}_BACKUP_DIR", str(tmp_path / "backups"))
    if spec.demo_db_path:
        monkeypatch.setattr(spec, "demo_db_path", tmp_path / "demo.duckdb")
    for name in (*PROTECTED_ENV, *env, f"{spec.env_prefix}_APP_DB", f"{spec.env_prefix}_PRIVACY_TERMS"):
        monkeypatch.delenv(name, raising=False)


def contract_db(spec: AppSpec, path: Path) -> duckdb.DuckDBPyConnection:
    """A new database at `path` with the contract's exact shape and its v_contract row, still open for filling.
    The browser app's tests build their data this way, without the ingestion."""
    con = duckdb.connect(str(path))
    if spec.contract.prelude:
        con.execute(spec.contract.prelude)
    con.execute(spec.contract.schema_sql())
    con.execute("INSERT INTO v_contract VALUES (?, ?)", [spec.contract.name, spec.contract.version])
    return con
