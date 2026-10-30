"""Backups: the whole database exported as Parquet, one folder per snapshot, checked after writing.

`backup` exports the database with EXPORT DATABASE (Parquet files + schema.sql + load.sql: readable by any Parquet
tool, independent of the DuckDB version), imports the export into an in-memory database and compares every table's
rows and content with the source, then keeps the newest `keep` snapshots. `restore` rebuilds a database file from
a snapshot, and never overwrites one.

The folder is spec.backup_dir() (`[backup] dir` in config.toml or <PREFIX>_BACKUP_DIR; default backups/, which
the template's .gitignore excludes).

Off the machine: with `[backup] remote = "gs://<bucket>"`, `upload` copies a verified snapshot, byte for byte, to
`gs://<bucket>/<package>/<snapshot>/` with `gcloud storage` (the user's own login). load.sql goes up last, so a
snapshot without it is incomplete, and each file's MD5 must match the local one. `fetch` brings one back into the
backup folder, checked the same way, and `prune_remote` keeps the newest `keep` there too.
"""

import base64
import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from duckkit.snapshot import literal
from duckkit.spec import AppSpec
from duckkit.store import tables


class BackupError(RuntimeError):
    """A snapshot doesn't match the database it was taken from."""


class OffsiteError(RuntimeError):
    """The off-machine copy can't be made, read or fetched: the message says why."""


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
        waiting = [s.query.strip().rstrip(";") for s in con.extract_statements(path.read_text())]
        waiting = [statement for statement in waiting if statement]
        done: list[str] = []
        while waiting:
            failed = []
            for statement in waiting:
                try:
                    con.execute(statement)
                    done.append(statement)
                except duckdb.Error:  # most often it reads something not made yet: try it again after the others
                    failed.append(statement)
            if len(failed) == len(waiting):  # no progress: these keep their order, and the import reports the error
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


# ─── Off the machine ───

@dataclass
class RemoteSnapshot:
    """A snapshot in Cloud Storage: its folder name and its files, each with its base64 MD5 (as Cloud Storage keeps
    it). Without load.sql it is incomplete: an upload that stopped half-way."""

    name: str
    files: dict[str, str] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return "load.sql" in self.files


def md5(path: Path) -> str:
    """A file's MD5, base64-encoded as Cloud Storage gives it."""
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return base64.b64encode(digest.digest()).decode()


def differences(local: Path, remote: RemoteSnapshot | None) -> list[str]:
    """How the files of the snapshot folder `local` differ from `remote`; empty when they are the same bytes."""
    if remote is None:
        return ["not in Cloud Storage"]
    here = {p.name: md5(p) for p in local.iterdir() if p.is_file()}
    problems = [f"{name}: missing there" for name in sorted(here.keys() - remote.files.keys())]
    problems += [f"{name}: missing here" for name in sorted(remote.files.keys() - here.keys())]
    problems += [f"{name}: different contents" for name in sorted(here.keys() & remote.files.keys())
                 if here[name] != remote.files[name]]
    return problems


def remote_snapshots(spec: AppSpec) -> list[RemoteSnapshot]:
    """The snapshots in Cloud Storage, oldest first; empty when `[backup] remote` is not set. Raises OffsiteError."""
    root = spec.backup_remote()
    if root is None:
        return []
    listed = _gcloud(spec, ["storage", "objects", "list", f"{root}/**", "--raw", "--format=json"], empty_ok=True)
    try:
        objects = json.loads(listed or "[]")
    except json.JSONDecodeError as e:
        raise OffsiteError("`gcloud storage objects list` gave an answer that is not JSON") from e
    found: dict[str, RemoteSnapshot] = {}
    for item in objects:
        parts = item.get("name", "").removeprefix(f"{spec.package}/").split("/")
        if len(parts) == 2 and parts[0].startswith(spec.backup_prefix) and parts[1]:
            found.setdefault(parts[0], RemoteSnapshot(parts[0])).files[parts[1]] = item.get("md5Hash", "")
    return [found[name] for name in sorted(found)]


def upload(spec: AppSpec, snapshot: Path) -> RemoteSnapshot:
    """Copy the snapshot folder to Cloud Storage, load.sql last, and check every file's MD5 there. Raises
    OffsiteError; the local snapshot is never touched."""
    root = _remote(spec)
    files = sorted(snapshot.iterdir())
    if any(not p.is_file() for p in files) or not (snapshot / "load.sql").is_file():
        raise OffsiteError(f"{snapshot.name}: not a snapshot folder (only files, with a load.sql)")
    target = f"{root}/{snapshot.name}/"
    _gcloud(spec, ["storage", "cp", *(str(p) for p in files if p.name != "load.sql"), target])
    _gcloud(spec, ["storage", "cp", str(snapshot / "load.sql"), target])
    remote = next((r for r in remote_snapshots(spec) if r.name == snapshot.name), None)
    problems = differences(snapshot, remote)
    if problems:
        raise OffsiteError(f"{target}: " + "; ".join(problems))
    return remote


def prune_remote(spec: AppSpec, keep: int | None = None) -> list[str]:
    """Delete all but the newest `keep` complete snapshots in Cloud Storage (keep 0: delete none), and the incomplete
    ones older than the newest complete one. Returns their names."""
    root = _remote(spec)
    keep = keep if keep is not None else spec.backup_keep()
    found = remote_snapshots(spec)
    complete = [r.name for r in found if r.complete]
    old = complete[:-keep] if keep > 0 else []
    if complete:
        old += [r.name for r in found if not r.complete and r.name < complete[-1]]
    for name in old:
        _gcloud(spec, ["storage", "rm", "--recursive", f"{root}/{name}/"])
    return old


def fetch(spec: AppSpec, name: str | None = None, folder: Path | None = None) -> Path:
    """Download a snapshot from Cloud Storage (default: the newest complete one) into the backup folder. Every file's
    MD5 must match, and the snapshot must import. Never overwrites a local snapshot. Raises OffsiteError."""
    root = _remote(spec)
    found = remote_snapshots(spec)
    if name is None:
        complete = [r for r in found if r.complete]
        if not complete:
            raise OffsiteError(f"no complete snapshot in {root}")
        remote = complete[-1]
    else:
        remote = next((r for r in found if r.name == name), None)
        if remote is None:
            raise OffsiteError(f"no snapshot {name} in {root}")
        if not remote.complete:
            raise OffsiteError(f"{name} in {root} is incomplete (no load.sql): its upload stopped half-way")
    folder = folder or spec.backup_dir()
    target = folder / remote.name
    if target.exists():
        raise OffsiteError(f"{target} exists already")
    partial = folder / f".fetching-{remote.name}"  # outside snapshots(): it lists only the prefix
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    try:
        _gcloud(spec, ["storage", "cp", f"{root}/{remote.name}/*", str(partial)])
        problems = differences(partial, remote)
        if problems:
            raise OffsiteError(f"{remote.name}: " + "; ".join(problems))
        try:
            verify(spec, partial)
        except duckdb.Error as e:
            raise OffsiteError(f"{remote.name} doesn't import: {str(e).splitlines()[0]}") from e
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    partial.rename(target)
    return target


def _remote(spec: AppSpec) -> str:
    root = spec.backup_remote()
    if root is None:
        raise OffsiteError('no off-machine copy: set [backup] remote = "gs://<bucket>" in config.toml')
    return root


def _gcloud(spec: AppSpec, args: list[str], empty_ok: bool = False) -> str:
    """Run `gcloud`; its output. `empty_ok`: a listing that matches nothing gives "" rather than an error."""
    try:
        out = subprocess.run(["gcloud", *args], cwd=spec.root, capture_output=True, text=True, check=False,
                             timeout=1800)
    except FileNotFoundError as e:
        raise OffsiteError("`gcloud` is not installed (cloud.google.com/sdk)") from e
    except subprocess.TimeoutExpired as e:
        raise OffsiteError(f"`gcloud storage {args[1]}` did not finish in 30 minutes") from e
    if out.returncode != 0:
        if empty_ok and "matched no objects" in out.stderr:
            return ""
        message = (out.stderr.strip().splitlines() or ["no message"])[-1]
        raise OffsiteError(f"`gcloud storage {args[1]}` failed: {message}")
    return out.stdout.strip()
