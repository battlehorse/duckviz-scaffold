"""Backups: a verified Parquet export that restores to the same data, and rotation."""

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
