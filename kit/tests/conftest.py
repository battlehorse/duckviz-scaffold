"""A small app for duckkit's tests: a two-view contract, its tables and views, in a temporary project."""

import subprocess
from pathlib import Path

import pytest

from duckkit import AppEntry, AppSpec, Contract
from duckkit.contract import enum_rule
from duckkit.store import connect

SCHEMA = Path(__file__).parent / "schema.sql"

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (name VARCHAR PRIMARY KEY, kind VARCHAR, price DOUBLE, secret VARCHAR);
CREATE OR REPLACE VIEW v_contract AS SELECT 'shop' AS contract, '1.2' AS version;
CREATE OR REPLACE VIEW v_items AS SELECT name AS item, kind, price FROM items;
"""


def git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args], cwd=root, check=True,
                   capture_output=True)


def make_contract(version: str = "1.0") -> Contract:
    return Contract(name="shop", version=version, schema=SCHEMA,
                    rules=[enum_rule("v_items", "kind", ["fruit", "veg"])])


@pytest.fixture
def spec(tmp_path, monkeypatch) -> AppSpec:
    for name in ("MOTHERDUCK_TOKEN", "ANTHROPIC_API_KEY", "SHOP_DB", "SHOP_APP_DB", "SHOP_BACKUP_DIR",
                 "SHOP_BACKUP_REMOTE"):
        monkeypatch.delenv(name, raising=False)
    return AppSpec(package="shop", root=tmp_path, contract=make_contract(), apps=[AppEntry("app", port=8600)],
                   timezone="Europe/London", motherduck_target="md:shop", demo_file="demo.duckdb",
                   private_settings=(("shop", "account", "SHOP_ACCOUNT", "account number"),))


@pytest.fixture
def db(spec):
    """The app's database with three items, open for writing."""
    con = connect(spec, DB_SCHEMA)
    con.execute("INSERT INTO items VALUES ('apple', 'fruit', 0.4, 'x'), ('leek', 'veg', NULL, 'y'),"
                " ('pear', 'fruit', 0.5, 'z')")
    yield con
    con.close()


@pytest.fixture
def closed_db(db, spec):
    """`db`, closed so a snapshot can attach it. Returns its path."""
    db.close()
    return spec.db_path


class FakeGcloud:
    """Answers `gcloud storage` as Cloud Storage would, with the bucket gs://shop-backups kept in a folder. Keeps the
    commands. `fail`: the subcommand ("cp", "rm", …) that fails; `corrupt`: uploads change each file's last byte."""

    BUCKET = "gs://shop-backups"

    def __init__(self, folder: Path):
        self.folder, self.commands, self.fail, self.corrupt = folder, [], None, False

    def path(self, url: str) -> Path:
        return self.folder / url.removeprefix(self.BUCKET + "/").rstrip("/*")

    def __call__(self, command, **kwargs):
        import base64
        import hashlib
        import json
        import shutil

        self.commands.append(command)
        assert command[:2] == ["gcloud", "storage"], command
        if command[2] == self.fail:
            return subprocess.CompletedProcess(command, 1, "", "ERROR: (gcloud.storage) [you] does not have access\n")
        if command[2:4] == ["objects", "list"]:
            root = self.path(command[4].removesuffix("**"))
            objects = [{"name": str(p.relative_to(self.folder)),
                        "md5Hash": base64.b64encode(hashlib.md5(p.read_bytes()).digest()).decode()}
                       for p in sorted(root.rglob("*")) if p.is_file()] if root.exists() else []
            if not objects:
                return subprocess.CompletedProcess(command, 1, "", "ERROR: (gcloud.storage.objects.list) One or "
                                                   "more URLs matched no objects.\n")
            return subprocess.CompletedProcess(command, 0, json.dumps(objects), "")
        if command[2] == "cp" and command[-1].startswith("gs://"):
            target = self.path(command[-1])
            target.mkdir(parents=True, exist_ok=True)
            for source in command[3:-1]:
                data = Path(source).read_bytes()
                (target / Path(source).name).write_bytes(data[:-1] + b"!" if self.corrupt else data)
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[2] == "cp":
            for source in self.path(command[3]).iterdir():
                shutil.copy(source, Path(command[4]) / source.name)
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[2:4] == ["rm", "--recursive"]:
            shutil.rmtree(self.path(command[4]))
            return subprocess.CompletedProcess(command, 0, "", "")
        raise AssertionError(f"unexpected command {command}")


@pytest.fixture
def gcs(spec, tmp_path, monkeypatch) -> FakeGcloud:
    """`[backup] remote` set to gs://shop-backups, and a fake `gcloud` that keeps the bucket in a folder."""
    fake = FakeGcloud(tmp_path / "bucket")
    monkeypatch.setenv("SHOP_BACKUP_REMOTE", FakeGcloud.BUCKET)
    monkeypatch.setattr("duckkit.backup.subprocess.run", fake)
    return fake
