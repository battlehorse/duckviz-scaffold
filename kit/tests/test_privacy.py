"""The privacy check finds the private settings, [privacy] terms and the app's own terms in committable files."""

import subprocess

from duckkit import privacy


def test_terms(spec, monkeypatch):
    spec.config_path.write_text('[shop]\naccount = "12345678"\n[privacy]\nterms = ["Smithson"]\n')
    monkeypatch.setenv("MOTHERDUCK_TOKEN", "md-secret")
    terms = privacy.personal_terms(spec, extra=lambda s: {"Alice's Room": "a zone name"})
    assert terms == {"12345678": "account number", "md-secret": "MotherDuck token", "Smithson": "a [privacy] term",
                     "Alice's Room": "a zone name"}


def test_scan_reads_only_committable_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / ".gitignore").write_text("config.toml\n")
    (repo / "config.toml").write_text('token = "secret-token"\n')
    (repo / "notes.md").write_text("ok\nthe account is 12345678\n")
    found = privacy.scan(privacy.committable_files(repo), {"12345678": "account", "secret-token": "token"}, repo)
    assert [(f.path, f.line, f.what) for f in found] == [("notes.md", 2, "account")]
