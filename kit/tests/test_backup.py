"""Backups: a verified Parquet export that restores to the same data, and rotation."""

import duckdb
import pytest

from duckkit import backup


def test_round_trip(db, spec, tmp_path):
    snapshot = backup.backup(spec, db, tmp_path / "b")
    assert snapshot.name.startswith("shop-") and any(p.suffix == ".parquet" for p in snapshot.iterdir())
    restored = backup.restore(spec, snapshot, tmp_path / "restored.duckdb")
    assert restored == backup.counts(db) and restored["items"][0] == 3


def test_restore_never_overwrites(db, spec, tmp_path):
    snapshot = backup.backup(spec, db, tmp_path / "b")
    (tmp_path / "there.duckdb").write_text("")
    with pytest.raises(FileExistsError):
        backup.restore(spec, snapshot, tmp_path / "there.duckdb")


def test_a_damaged_snapshot_fails_verification(db, spec, tmp_path):
    snapshot = backup.backup(spec, db, tmp_path / "b")
    expected = backup.counts(db)
    expected["items"] = (4, expected["items"][1])
    assert backup.verify(spec, snapshot, expected) == [f"items: {backup.counts(db)['items']} rows/hash, expected {expected['items']}"]


def test_pruning_keeps_the_newest(spec, tmp_path):
    folder = tmp_path / "b"
    for stamp in ("20260101T000000Z", "20260102T000000Z", "20260103T000000Z"):
        (folder / f"shop-{stamp}").mkdir(parents=True)
    assert [p.name for p in backup.prune(spec, folder, keep=2)] == ["shop-20260101T000000Z"]
    assert len(backup.snapshots(spec, folder)) == 2


def test_a_macro_that_reads_a_view_survives_the_round_trip(db, spec, tmp_path):
    """EXPORT DATABASE writes macros before views: the backup puts each statement after what it reads."""
    db.execute("CREATE VIEW v_kinds AS SELECT DISTINCT kind FROM items")
    db.execute("CREATE MACRO kinds() AS (SELECT count(*) FROM v_kinds)")
    db.execute("CREATE VIEW v_summary AS SELECT kinds() AS n")
    snapshot = backup.backup(spec, db, tmp_path / "b")
    restored = tmp_path / "restored.duckdb"
    assert backup.restore(spec, snapshot, restored) == backup.counts(db)
    with duckdb.connect(str(restored)) as con:
        assert con.execute("SELECT n FROM v_summary").fetchone() == db.execute("SELECT n FROM v_summary").fetchone()


# ─── Off the machine (a fake `gcloud`: no network) ───

def test_without_a_remote_nothing_leaves_the_machine(db, spec, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("duckkit.backup.subprocess.run", lambda *a, **k: calls.append(a))
    backup.backup(spec, db, tmp_path / "b")
    assert spec.backup_remote() is None and backup.remote_snapshots(spec) == [] and calls == []
    with pytest.raises(backup.OffsiteError, match=r"set \[backup\] remote"):
        backup.fetch(spec)


def test_the_remote_is_a_bucket(spec, monkeypatch):
    monkeypatch.setenv("SHOP_BACKUP_REMOTE", "gs://shop-backups/")
    assert spec.backup_remote() == "gs://shop-backups/shop"
    for wrong in ("shop-backups", "gs://", "gs://shop-backups/more", "s3://shop-backups"):
        monkeypatch.setenv("SHOP_BACKUP_REMOTE", wrong)
        with pytest.raises(ValueError, match="Cloud Storage bucket"):
            spec.backup_remote()


def test_an_upload_is_the_same_bytes_with_load_sql_last(db, spec, gcs, tmp_path):
    snapshot = backup.backup(spec, db, tmp_path / "b")
    remote = backup.upload(spec, snapshot)
    assert remote.complete and backup.differences(snapshot, remote) == []
    assert (gcs.folder / "shop" / snapshot.name / "load.sql").read_bytes() == (snapshot / "load.sql").read_bytes()
    uploads = [c for c in gcs.commands if c[2] == "cp"]
    assert uploads[-1] == ["gcloud", "storage", "cp", str(snapshot / "load.sql"),
                           f"gs://shop-backups/shop/{snapshot.name}/"]
    assert all("load.sql" not in arg for arg in uploads[0][3:])


def test_a_failed_or_changed_upload_raises_and_keeps_the_local_snapshot(db, spec, gcs, tmp_path):
    snapshot = backup.backup(spec, db, tmp_path / "b")
    gcs.fail = "cp"
    with pytest.raises(backup.OffsiteError, match="does not have access"):
        backup.upload(spec, snapshot)
    gcs.fail, gcs.corrupt = None, True
    with pytest.raises(backup.OffsiteError, match="different contents"):
        backup.upload(spec, snapshot)
    assert snapshot.exists() and backup.verify(spec, snapshot, backup.counts(db)) == []


def test_remote_pruning_keeps_the_newest(spec, gcs):
    for stamp in ("20260101T000000Z", "20260102T000000Z", "20260103T000000Z"):
        (gcs.folder / "shop" / f"shop-{stamp}").mkdir(parents=True)
        (gcs.folder / "shop" / f"shop-{stamp}" / "load.sql").write_text("")
    (gcs.folder / "other" / "other-20260101T000000Z").mkdir(parents=True)  # another app in the same bucket
    assert backup.prune_remote(spec, keep=2) == ["shop-20260101T000000Z"]
    assert [r.name for r in backup.remote_snapshots(spec)] == ["shop-20260102T000000Z", "shop-20260103T000000Z"]
    assert (gcs.folder / "other" / "other-20260101T000000Z").exists()


def test_a_new_machine_fetches_the_newest_complete_snapshot_and_restores_it(db, spec, gcs, tmp_path):
    first = backup.backup(spec, db, tmp_path / "b")
    first = first.rename(first.with_name("shop-20260101T000000Z"))  # older than the next one
    backup.upload(spec, first)
    db.execute("INSERT INTO items VALUES ('kale', 'veg', 1.0, 'w')")
    second = backup.backup(spec, db, tmp_path / "b", keep=0)
    backup.upload(spec, second)
    half = gcs.folder / "shop" / "shop-29990101T000000Z"  # a newer upload that stopped half-way
    half.mkdir()
    (half / "items.parquet").write_bytes(b"")
    assert [r.complete for r in backup.remote_snapshots(spec)] == [True, True, False]
    fetched = backup.fetch(spec, folder=tmp_path / "new")
    assert fetched == tmp_path / "new" / second.name and backup.snapshots(spec, tmp_path / "new") == [fetched]
    assert backup.restore(spec, fetched, tmp_path / "restored.duckdb") == backup.counts(db)
    with pytest.raises(backup.OffsiteError, match="exists already"):
        backup.fetch(spec, second.name, folder=tmp_path / "new")
    with pytest.raises(backup.OffsiteError, match="incomplete"):
        backup.fetch(spec, half.name, folder=tmp_path / "new")
    with pytest.raises(backup.OffsiteError, match="no snapshot shop-x"):
        backup.fetch(spec, "shop-x", folder=tmp_path / "new")


def test_a_fetch_that_doesnt_match_leaves_nothing(db, spec, gcs, tmp_path):
    snapshot = backup.backup(spec, db, tmp_path / "b")
    backup.upload(spec, snapshot)
    gcs.fail = "cp"
    with pytest.raises(backup.OffsiteError, match="does not have access"):
        backup.fetch(spec, folder=tmp_path / "new")
    assert list((tmp_path / "new").iterdir()) == []
