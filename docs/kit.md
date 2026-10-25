# duckkit

The code every app shares. An app installs it at the scaffold release its files come from:

```toml
"duckkit @ git+https://github.com/battlehorse/duckviz-scaffold@v0.1.0#subdirectory=kit"
```

## The spec: one description, passed everywhere

duckkit has no settings of its own. Each app describes itself once, in `src/<package>/spec.py`:

```python
SPEC = AppSpec(
    package="shopviz", cli="shopviz", root=Path(__file__).resolve().parents[2],
    contract=CONTRACT,                      # duckkit.Contract: name, version, reference schema, rules
    env_prefix="SHOPVIZ",                   # SHOPVIZ_DB, _APP_DB, _CONFIG, _VERSION, _BACKUP_DIR, …
    db_file="shop.duckdb", timezone="Europe/London",
    motherduck_target="md:shop", config_style="toml",
    apps=[AppEntry("app", port=8501, title="Shop")],
    private_settings=(("shop", "api_key", "SHOP_API_KEY", "shop API key"), …),
    forbidden=("ingest", "db", "cli"),
)
```

Every function takes the spec: `contract_snapshot(SPEC)`, `publish(SPEC, target)`, `backup(SPEC, con)`,
`run_app(SPEC, "app", tailnet=True)`. Paths and environment overrides are resolved when the spec is made; tests
change them on the spec (`duckkit.testing.isolate`). Settings come from the environment, then `.env`, then
`config.toml`, then the default (`SPEC.setting(section, key, env, default)`), so an app can use either file.

The spec is imported by the browser app too, so it must not import the ingestion.

## Modules

| Module | Side | What it does |
|---|---|---|
| `spec` | both | `AppSpec`, `AppEntry`, settings |
| `contract` | both | `Contract`: the reference schema (`reference()`), descriptions from its comments, `check(con)` (shape, keys, NOT NULL, rules, custom checks, version); `enum_rule`, `relation_rule` |
| `snapshot` | both | `contract_snapshot` (the app's in-memory copy: contract columns only, no file access, no lock), `contract_copy`, `database_snapshot`, `motherduck`, `ContractError` |
| `app.common` | app | the cached snapshot and a cursor per query, `sidebar` (caption, version, *Reload data*), `watch_theme`, `watch_idle` (Cloud Run), `table` |
| `app.theme` | app | the checked light/dark palettes, `mode()`, `base_option()`, `entity_colors()` |
| `store` | service | `connect` with the schema version and migrations (SQL or functions), `tables` |
| `publish` | service | `plan` (`--dry-run`), `publish` (one transaction, with comments), `compare` (`--check`) |
| `backup` | service | verified Parquet snapshots: `backup`, `verify`, `snapshots`, `prune`, `restore` (never overwrites) |
| `privacy` | service | scans committable files for the private settings, `[privacy] terms` and the app's own terms |
| `serve` | service | Streamlit on localhost, `tailscale serve` while it runs, several apps, the demo database |
| `cli` | service | `add_standard_commands(app, SPEC, connect=…, status=…, privacy_terms=…)`: `status`, `sql`, `publish`, `backup(s)`, `restore`, `app`, `privacy-check`, `doctor` |
| `doctor` | service | the repo against the scaffold: release vs duckkit, expected files, opt-outs explained |
| `testing` | tests | `isolate`, `contract_db`, and `guard`: the app's SQL reads only contract views, and the app never imports the ingestion |

"Side": the browser app may import only the "both" and "app" modules. `testing.guard` fails an app that imports a
"service" module.

## Hooks: where an app's domain goes in

- **Contract rules**: `Contract(rules=[(sql counting bad rows, message), …], checks=[fn(con) -> [problems]])`.
- **Status**: `add_standard_commands(…, status=fn(con) -> [lines])`.
- **Privacy**: `add_standard_commands(…, privacy_terms=fn(spec) -> {term: what})` (names in the database, say).
- **Schema**: the app's `db/store.py` passes its `schema.sql`, `SCHEMA_VERSION` and `MIGRATIONS` to `store.connect`.
- **Pages**: an app's `app/common.py` binds duckkit's helpers to its spec and adds its own.

Anything an app needs that no hook allows is a candidate for a new hook: upstream it (docs/upgrading.md).

## Compatibility

duckkit follows the release version. Within a major version (0.x counts each minor as major), a release only
adds; a change an app must follow is listed under **Steps** in CHANGELOG.md.
