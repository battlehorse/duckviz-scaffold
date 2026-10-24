"""Paths and settings: the environment wins over .env, which wins over config.toml; empty values are unset."""

from duckkit import AppEntry, AppSpec
from tests.conftest import make_contract


def test_paths_and_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("SHOP_DB", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("SHOP_APP_DB", "md:shop")
    spec = AppSpec(package="shop", root=tmp_path, contract=make_contract(), apps=[AppEntry("app", 8600)])
    assert spec.db_path == tmp_path / "x.duckdb" and spec.app_db == "md:shop"
    assert spec.cli == "shop" and spec.env_prefix == "SHOP" and spec.backup_prefix == "shop-"
    assert spec.main_script() == tmp_path / "src" / "shop" / "app" / "main.py"
    assert spec.app().tailnet_port == 8600


def test_setting_precedence(spec, monkeypatch):
    spec.config_path.write_text('[shop]\naccount = "from-toml"\nempty = ""\n[backup]\ndir = "snaps"\nkeep = 3\n')
    assert spec.setting("shop", "account", "SHOP_ACCOUNT") == "from-toml"
    assert spec.setting("shop", "empty", default="d") == "d"
    spec.env_file.write_text('# comment\nexport SHOP_ACCOUNT="from-dotenv"\n')
    assert spec.setting("shop", "account", "SHOP_ACCOUNT") == "from-dotenv"
    monkeypatch.setenv("SHOP_ACCOUNT", "from-env")
    assert spec.setting("shop", "account", "SHOP_ACCOUNT") == "from-env"
    assert spec.backup_dir() == spec.root / "snaps" and spec.backup_keep() == 3


def test_unknown_app(spec):
    try:
        spec.app("nope")
    except KeyError as e:
        assert "app" in str(e)
    else:
        raise AssertionError
