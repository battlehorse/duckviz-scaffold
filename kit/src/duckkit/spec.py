"""An app's description: where things live, its ports, its contract, and how it reads its settings.

Paths and environment overrides are resolved when the spec is made (at import, like module constants). Tests
change them on the spec itself (`duckkit.testing.isolate`).

Settings live in `config.toml` (`[section] key`), which is gitignored. An environment variable overrides one, for
CI, tests and a hosted app (Cloud Run passes secrets as variables). Empty values count as unset.
"""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from duckkit.contract import Contract

TAILSCALE_APP = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"  # the CLI when `tailscale` isn't on PATH


@dataclass
class AppEntry:
    """One Streamlit app of the project: `src/<package>/<name>/main.py`.

    A `hosted` app reads only the contract; the others (a curation app, say) read the whole database. Only the
    browser app (`app`) goes to Cloud Run: an extra app runs on this machine, whatever its `hosted` flag. `tailnet_port` is the HTTPS port `--tailnet` serves on (default:
    the local port again, not 443, which other apps on this machine may serve)."""

    name: str
    port: int
    title: str = ""
    hosted: bool = True
    tailnet_port: int | None = None

    def __post_init__(self):
        self.tailnet_port = self.tailnet_port or self.port


@dataclass(eq=False)
class AppSpec:
    """Everything duckkit needs to know about one app. Made once, in `<package>/spec.py`."""

    package: str  # the import name, e.g. "shopviz"
    root: Path  # the project root (the folder of pyproject.toml)
    contract: Contract
    apps: list[AppEntry]
    env_prefix: str = ""  # e.g. "SHOPVIZ": SHOPVIZ_DB, SHOPVIZ_APP_DB, …
    cli: str = ""  # the command, default the package name
    db_file: str = "app.duckdb"  # in data/
    demo_file: str | None = None  # in data/, when the app has a demo database
    timezone: str | None = None  # every connection's TimeZone; None: DuckDB's default
    motherduck_target: str | None = None  # where `publish` writes, e.g. "md:shop"; None: no publishing
    # Settings that are personal (section, key, env, what): `privacy-check` refuses them in committed files
    private_settings: tuple[tuple[str, str, str | None, str], ...] = ()
    # The browser app's code, relative to src/<package>: it may read only the contract (duckkit.testing.guard)
    app_code: tuple[str, ...] = ("app", "query", "analysis.py")
    # Modules of the package that the browser app must never import (the ingestion side), relative names
    forbidden: tuple[str, ...] = ("ingest", "db", "cli")
    # Test modules the browser app's tests (tests/app) must not import either: the ingestion's fixtures, full names
    forbidden_in_tests: tuple[str, ...] = ()
    # Modules of the browser app that run only inside a Streamlit session (they declare a component when imported),
    # beyond each app's views/ and main.py, relative to src/<package>: the guard doesn't import them outside one
    page_modules: tuple[str, ...] = ()
    refresh_hint: str = ""  # what to tell the user when the database doesn't offer the contract
    idle_minutes: int = 15  # a hosted app pauses an idle tab after this long (0: never)
    backup_prefix: str = ""  # the start of each backup snapshot's folder name, default "<package>-"

    # Resolved in __post_init__
    data_dir: Path = field(init=False)
    curated_dir: Path = field(init=False)  # curated/: the decisions kept in git (duckkit.curated)
    db_path: Path = field(init=False)
    demo_db_path: Path | None = field(init=False)
    app_db: str | None = field(init=False)
    config_path: Path = field(init=False)
    version: str | None = field(init=False)

    def __post_init__(self):
        self.cli = self.cli or self.package
        self.backup_prefix = self.backup_prefix or f"{self.package}-"
        self.env_prefix = self.env_prefix or self.package.upper().replace("-", "_")
        self.refresh_hint = self.refresh_hint or (
            f"Run `{self.cli} ingest` (or `/ingest` in Claude Code) to bring its views up to date.")
        self.data_dir = self.root / "data"
        self.curated_dir = self.root / "curated"
        self.db_path = Path(self.env("DB") or self.data_dir / self.db_file)
        self.demo_db_path = self.data_dir / self.demo_file if self.demo_file else None
        self.app_db = self.env("APP_DB")  # where a hosted app reads the contract, e.g. "md:shop"
        self.config_path = Path(self.env("CONFIG") or self.root / "config.toml")
        self.version = self.env("VERSION")  # the deployed commit, shown by a hosted app
        self.idle_minutes = int(self.env("IDLE_MINUTES") or self.idle_minutes)

    def env(self, name: str) -> str | None:
        """The environment variable `<env_prefix>_<name>`, or None when unset or empty."""
        return os.environ.get(f"{self.env_prefix}_{name}") or None

    def app(self, name: str | None = None) -> AppEntry:
        """The app called `name`; the first one by default."""
        if name is None:
            return self.apps[0]
        for entry in self.apps:
            if entry.name == name:
                return entry
        raise KeyError(f"no app {name!r}: the apps are {', '.join(a.name for a in self.apps)}")

    def main_script(self, name: str | None = None) -> Path:
        """The Streamlit entry point of an app."""
        return self.root / "src" / self.package / self.app(name).name / "main.py"

    # ─── Settings ───

    def load(self) -> dict:
        """The parsed config.toml; empty when there is none."""
        try:
            with open(self.config_path, "rb") as f:
                return tomllib.load(f)
        except FileNotFoundError:
            return {}

    def setting(self, section: str | None, key: str | None, env: str | None = None, default=None):
        """One setting: the environment variable `env`, else `[section] key` in config.toml, else `default`. Empty
        strings count as unset."""
        if env and os.environ.get(env):
            return os.environ[env]
        if section and key:
            value = self.load().get(section, {}).get(key)
            if value not in (None, ""):
                return value
        return default

    def motherduck_token(self) -> str | None:
        """The MotherDuck access token (`publish`, and a hosted app). None: MotherDuck is not set up."""
        return self.setting("motherduck", "token", "MOTHERDUCK_TOKEN")

    def where_token(self) -> str:
        """Where the user puts the MotherDuck token, for messages."""
        return "[motherduck] token in config.toml (or the MOTHERDUCK_TOKEN environment variable)"

    def anthropic_api_key(self) -> str | None:
        """The Anthropic API key (`duckkit.llm`). None: the app has no key."""
        return self.setting("anthropic", "api_key", "ANTHROPIC_API_KEY")

    def where_anthropic_key(self) -> str:
        """Where the user puts the Anthropic API key, for messages."""
        return "[anthropic] api_key in config.toml (or the ANTHROPIC_API_KEY environment variable)"

    def backup_dir(self) -> Path:
        """The folder of backup snapshots. A relative `[backup] dir` (or <PREFIX>_BACKUP_DIR) is relative to the root."""
        value = self.setting("backup", "dir", f"{self.env_prefix}_BACKUP_DIR")
        path = Path(value).expanduser() if value else self.root / "backups"
        return path if path.is_absolute() else self.root / path

    def backup_keep(self) -> int:
        """How many of the newest snapshots `backup` keeps."""
        return int(self.setting("backup", "keep", f"{self.env_prefix}_BACKUP_KEEP", default=30))
