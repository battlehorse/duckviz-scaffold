# duckkit

duckkit is the code that every app made from the scaffold shares. It lives in `kit/`, and an app installs it at
the scaffold release its files come from:

```toml
dependencies = ["duckkit @ git+https://github.com/battlehorse/duckviz-scaffold@v0.2.0#subdirectory=kit"]
```

`copier update` moves this pin and the template's files together, so they always come from the same release. To
see where the modules fit in an app, read docs/architecture.md first.

- [The spec](#the-spec-one-description-passed-everywhere)
- [Which side may import what](#which-side-may-import-what)
- Modules: [spec](#duckkitspec) · [contract](#duckkitcontract) · [snapshot](#duckkitsnapshot) ·
  [store](#duckkitstore) · [publish](#duckkitpublish) · [backup](#duckkitbackup) · [privacy](#duckkitprivacy) ·
  [serve](#duckkitserve) · [cli](#duckkitcli) · [doctor](#duckkitdoctor) · [demo](#duckkitdemo) · [curated](#duckkitcurated) · [app.common](#duckkitappcommon) ·
  [app.theme](#duckkitapptheme) · [testing](#duckkittesting) · [testing.guard](#duckkittestingguard)
- [Hooks](#hooks-where-an-apps-domain-goes-in)
- [Compatibility](#compatibility)

## The spec: one description, passed everywhere

duckkit has no settings and no global state. Each app describes itself once, in `src/<package>/spec.py`:

```python
SPEC = AppSpec(
    package="shopviz", cli="shopviz", root=Path(__file__).resolve().parents[2],
    contract=CONTRACT,                      # duckkit.Contract: name, version, reference schema, rules
    env_prefix="SHOPVIZ",                   # SHOPVIZ_DB, _APP_DB, _CONFIG, _VERSION, _BACKUP_DIR, …
    db_file="shop.duckdb", timezone="Europe/London",
    motherduck_target="md:shop",
    apps=[AppEntry("app", port=8501, title="Shop")],
    private_settings=(("shop", "api_key", "SHOP_API_KEY", "shop API key"), …),
    forbidden=("ingest", "db", "cli"),
)
```

Every function takes the spec: `contract_snapshot(SPEC)`, `publish(SPEC, target)`, `backup(SPEC, con)`,
`run_app(SPEC, "app", tailnet=True)`. Nothing in duckkit knows which app it serves.

## Which side may import what

An app has an ingestion side (the CLI, `ingest/`, `db/`) and a browser side (the Streamlit app). Each duckkit
module belongs to one of them:

| Module | Side | In one line |
|---|---|---|
| [`spec`](#duckkitspec) | both | the app's description: paths, ports, contract, settings |
| [`contract`](#duckkitcontract) | both | the contract: reference schema, descriptions, conformance check |
| [`snapshot`](#duckkitsnapshot) | both | read-only, in-memory copies of the database or of its contract views |
| [`app.common`](#duckkitappcommon) | browser | the cached snapshot, sidebar, theme and idle watchers, tables |
| [`app.theme`](#duckkitapptheme) | browser | colour palettes and shared chart options, light and dark |
| [`store`](#duckkitstore) | ingestion | open the database for writing: schema and migrations |
| [`publish`](#duckkitpublish) | ingestion | send the contract's views to MotherDuck; dry run; compare |
| [`backup`](#duckkitbackup) | ingestion | verified Parquet snapshots, and restore |
| [`privacy`](#duckkitprivacy) | ingestion | find personal data in the files git would commit |
| [`serve`](#duckkitserve) | ingestion | run a Streamlit app on localhost, optionally on the tailnet |
| [`cli`](#duckkitcli) | ingestion | the command-line commands every app has |
| [`doctor`](#duckkitdoctor) | ingestion | compare the repo with the scaffold release it comes from |
| [`demo`](#duckkitdemo) | ingestion | build a demo database, and tell one apart from the real one |
| [`curated`](#duckkitcurated) | ingestion | keep curated decisions in `curated/*.csv`, and restore them into a rebuilt database |
| [`testing`](#duckkittesting) | tests | isolate tests from real data; build contract databases |
| [`testing.guard`](#duckkittestingguard) | tests | keep the browser app on the contract |

The browser app may import only the "both" and "browser" modules. `testing.guard` fails a build where it imports
an ingestion module (`guard.KIT_SERVICE`).

---

## `duckkit.spec`

**What it is for:** describing one app, and reading its settings. Every other module gets what it needs from here.

**`AppEntry(name, port, title="", hosted=True, tailnet_port=None)`** describes one Streamlit app of the project.
Its entry point is `src/<package>/<name>/main.py`.
- `hosted=False` marks a local-only app, such as a curation tool. It may read the whole database, and it never
  runs on Cloud Run.
- `tailnet_port` is the HTTPS port `--tailnet` serves on. It defaults to the local port, not 443, because other
  apps on the machine may use 443.

**`AppSpec`** has two kinds of field.

The fields you set:

| Field | Default | Meaning |
|---|---|---|
| `package`, `root`, `contract`, `apps` | required | the import name, the project folder, the `Contract`, the `AppEntry` list |
| `cli` | `package` | the command's name, used in messages |
| `env_prefix` | `PACKAGE` | the start of every environment variable: `<PREFIX>_DB`, `_APP_DB`, `_CONFIG`, … |
| `db_file` / `demo_file` | `app.duckdb` / none | the database file, and the demo one, in `data/` |
| `timezone` | none | the `TimeZone` setting of every connection duckkit opens |
| `motherduck_target` | none | where `publish` writes (`md:<name>`). None turns publishing off. |
| `private_settings` | `()` | `(section, key, env, what)` of the personal settings that `privacy-check` refuses in git |
| `app_code` | `app`, `query`, `analysis.py` | the browser app's code, which the guard checks |
| `forbidden` | `ingest`, `db`, `cli` | the app's ingestion modules, which the browser app must not import |
| `forbidden_in_tests` | `()` | test modules that `tests/app` must not import, such as the ingestion's fixtures |
| `page_modules` | `()` | modules of the browser app that run only inside Streamlit (they declare a component when imported), beyond `views/` and `main.py`; the guard's loading check skips them |
| `refresh_hint` | "Run `<cli> ingest`…" | what to tell the user when the database doesn't offer the contract |
| `idle_minutes` | 15 | how long before a hosted app pauses an idle tab (0: never) |
| `backup_prefix` | `<package>-` | the start of each backup folder's name |

The fields resolved when the spec is made, which can be overridden from the environment:

| Field | Environment | Default |
|---|---|---|
| `data_dir` | | `<root>/data` |
| `curated_dir` | | `<root>/curated`: the curated decisions (`duckkit.curated`) |
| `db_path` | `<PREFIX>_DB` | `data/<db_file>` |
| `demo_db_path` | | `data/<demo_file>` |
| `app_db` | `<PREFIX>_APP_DB` | none. When set, the app reads this (a file or `md:<name>`) instead: a hosted app. |
| `config_path` | `<PREFIX>_CONFIG` | `<root>/config.toml` |
| `version` | `<PREFIX>_VERSION` | none. The deployed commit, which a hosted app shows. |

Methods:
- `setting(section, key, env, default)` returns one setting: the environment variable `env` when it is set,
  else `[section] key` in `config.toml`, else `default`. Empty values count as unset. Settings live in
  `config.toml` only. The variable is for CI, tests and Cloud Run, which passes secrets as variables.
- `motherduck_token()` and `where_token()`: the token, and a sentence that says where the user puts it.
- `backup_dir()` and `backup_keep()`: from `[backup] dir` / `<PREFIX>_BACKUP_DIR` (default `backups/`) and
  `[backup] keep` (default 30).
- `app(name)` returns an `AppEntry`. `main_script(name)` returns its entry point.

Tests change the resolved paths on the spec itself (`duckkit.testing.isolate`). The browser app imports the spec,
so `spec.py` must not import the ingestion.

## `duckkit.contract`

**What it is for:** knowing exactly what the contract promises, and checking that a database keeps the promise.

**`Contract(name, version, schema, rules=[], checks=[], prelude="")`**
- `schema` is the reference schema file, usually `files("<package>.contract") / "schema.sql"`. It declares each
  view as a `CREATE TABLE` of the same name, with types, `PRIMARY KEY` and `NOT NULL`. A block of comments above a
  table describes the view. The comment after a column describes the column.
- `rules` are `(sql, message)` pairs. The SQL counts the rows that break a promise; the message contains `{n}`.
- `checks` are functions `fn(con) -> [problems]`, for anything a single count can't express.
- `prelude` is SQL that runs before the schema, such as the macros it uses.

Methods:

| Method | Returns |
|---|---|
| `reference()` | an empty in-memory database with the contract's exact shape |
| `views()`, `columns()` | the view names, and each view's columns, in the schema's order |
| `descriptions()` | `{view: (description, {column: description})}`, from the comments. `publish` writes these as comments, and the guard checks docs/contract.md against them. |
| `check(con)` | one message per problem, or `[]` when `con` conforms. It checks the shape first (views, columns, types; extra columns are fine), then primary keys, `NOT NULL`, the rules, the custom checks, and `v_contract`. |
| `accepts(name, version)` | whether code for this contract can read a database at that name and version: the same name and major version |

Helpers that build rules:
- `enum_rule(view, column, values)`: the column holds only these values.
- `relation_rule(view, column, parent, parent_column=None)`: every value exists in the parent view.

## `duckkit.snapshot`

**What it is for:** reading the database without ever changing it or locking it. Each function attaches the source
read-only, copies what it needs into an in-memory database, and detaches. So `ingest` can run while the app or
`sql` is open.

| Function | Gives | Used by |
|---|---|---|
| `contract_snapshot(spec, source=None)` | only the contract's views, as tables with only the reference schema's columns. External access is off, so the copy can't read files. It refuses a database with another contract name or major version (`ContractError`). `source` defaults to `spec.app_db`, then the local database. | the browser app |
| `contract_copy(spec, source=None)` | the same copy, with external access still on, so `publish` can attach its target | `publish` |
| `database_snapshot(spec, path=None)` | everything: tables and views. External access is off. | `sql`, `status`, local-only apps |
| `attach(spec, source)` | an in-memory database with the source attached read-only as `src` | the above |
| `motherduck(spec, con)` | loads the MotherDuck extension and signs in with the token, or says where to put one | the above, `publish` |
| `memory(spec)`, `literal(text)` | an empty database in the app's time zone; a quoted SQL string | everywhere |

A source is a DuckDB file or a MotherDuck database (`md:<name>`). A missing file raises `FileNotFoundError` with
a hint to run `ingest`.

## `duckkit.store`

**What it is for:** opening the database for writing, creating its schema, and migrating an older one.

- `connect(spec, schema_sql, version=1, migrations=None, path=None, read_only=False)` opens `spec.db_path` (or
  `path`) in the app's time zone. When it is writable, it calls `init_schema`. `schema_sql` can be the SQL text,
  or a function that returns it.
- `init_schema(con, schema_sql, version, migrations)`:
  - A new database gets its version recorded in `schema_version`.
  - An older one runs `migrations[v]` for each version `v` up to the current one. A migration is SQL, or a
    function of the connection.
  - It stops with an error when a migration is missing, or when the database is newer than the code.
  - Then it runs `schema_sql`, which must create only what is missing (`IF NOT EXISTS`) and replace the views.
- `tables(con)` lists the base tables of the current database, not the views.

The app's `db/store.py` wraps this with its own `SCHEMA_VERSION` and `MIGRATIONS`. Nothing in duckkit drops a
table.

## `duckkit.publish`

**What it is for:** making the contract's views available away from this machine: in MotherDuck, where a hosted
app, Claude or any DuckDB client can read them. Only the contract leaves, cut to the reference schema's columns.
Nothing publishes on its own.

| Function | Does | Command |
|---|---|---|
| `plan(spec)` | `{view: (rows, columns)}`: what would be sent. Sends nothing. | `publish --dry-run` |
| `publish(spec, target=None)` | replaces the tables at `target` in one transaction, so readers see all old or all new. Each table and column gets its description as a comment. A MotherDuck database is created if missing. Returns the rows per table. | `publish` |
| `compare(spec, target=None)` | `{view: (rows here, rows there, same)}`. Changes nothing. Contents are compared by a fingerprint, so a changed value shows even when the counts agree. | `publish --check` |
| `fingerprint(con, table)` | `(rows, sum of row hashes)`, which doesn't depend on row order | |

`target` defaults to `spec.motherduck_target`. It can also be a DuckDB file, for tests and offline copies.

## `duckkit.backup`

**What it is for:** a copy of the database that survives a broken file, a bad migration or a mistake, in a
format any tool can read.

- `backup(spec, con, folder=None, keep=None)`:
  1. exports the whole database with `EXPORT DATABASE` (Parquet files, `schema.sql`, `load.sql`) into a new
     `<backup_prefix><UTC time>` folder;
  2. imports the export into memory and compares every table's row count and content hash with the source,
     raising `BackupError` on any difference;
  3. deletes all but the newest `keep` snapshots.
- `verify(spec, snapshot, expected=None)` imports a snapshot and lists its differences from `expected`.
- `snapshots(spec)` lists the snapshot folders, oldest first. `prune(spec, folder, keep)` deletes the older ones.
- `restore(spec, snapshot, db_path)` builds a **new** database file from a snapshot. It refuses to overwrite an
  existing one.
- `counts(con)` gives each table's `(rows, hash)`.

Parquet doesn't depend on the DuckDB version, so a backup is also the way to move to a new major DuckDB version:
restore it with the new version into a new file.

## `duckkit.privacy`

**What it is for:** keeping personal data out of the repo, so the repo is always safe to share.

- `personal_terms(spec, extra=None)` collects `{term: what it is}` from:
  - the values of `spec.private_settings` and the MotherDuck token on this machine;
  - the terms under `[privacy] terms` (or `<PREFIX>_PRIVACY_TERMS`);
  - the app's own `extra(spec)` function, such as names found in its database.
- `committable_files(root)` lists the files git tracks, plus the untracked files that aren't ignored.
- `scan(files, terms, root)` finds every line that contains a term, ignoring case. Terms shorter than 3
  characters are skipped.
- `check(spec, extra=None)` combines the three. Each `Finding(path, line, what)` names the *kind* of term, never
  the term itself, so the report is safe to print.

The pre-commit hook runs this as `<cli> privacy-check`.

## `duckkit.serve`

**What it is for:** running a Streamlit app the same safe way every time.

- `run_app(spec, name=None, tailnet=False, demo=False)` runs the app until Ctrl+C and returns Streamlit's exit
  code. `demo=True` points `<PREFIX>_DB` at the demo database. `tailnet=True` also starts a forwarding for as long
  as the app runs.
- `streamlit_args(spec, name)` builds the command line: localhost only, headless, no usage statistics, no Deploy
  button.
- `tailnet_forward(port, tailnet_port)` starts `tailscale serve --https=<tailnet_port> <port>` in the foreground,
  so only devices on your tailnet can open it. `stop(process)` ends it as Ctrl+C would, which removes the
  forwarding. `tailscale funnel`, which would publish to the internet, is never used.
- `tailscale()` finds the CLI on `PATH` or in the macOS app. `tailnet_name()` returns this machine's tailnet
  name. Both raise `ServeError` when Tailscale is missing or not connected.

## `duckkit.cli`

**What it is for:** the command-line commands that run an app's shared functions, so every app is used the
same way. The app's `cli.py` makes its [Typer](https://typer.tiangolo.com) app, adds its own commands such as `ingest`, then calls:

```python
add_standard_commands(app, SPEC, connect=connect, status=status_lines, privacy_terms=terms,
                      backups=True, publishing=True, privacy=True)
```

| Command | Does | Built on |
|---|---|---|
| `status` | prints the app's `status(con)` lines, a "Demo:" line for a demo database, the backups line, and the contract check | `snapshot.database_snapshot`, `Contract.check` |
| `sql "SELECT …" [--limit]` | runs exactly one `SELECT` on a snapshot of the whole database and prints a table | `snapshot.database_snapshot` |
| `publish [--to] [--dry-run] [--check]` | sends the views (refusing a demo database), shows what would go, or compares | `publish`, `demo.is_demo` |
| `backup` / `backups` / `restore <snapshot> [--to]` | makes a verified snapshot, lists them, or rebuilds a new file from one | `backup` |
| `app [name] [--tailnet] [--demo]` | serves an app | `serve.run_app` |
| `privacy-check` | fails when a committable file holds personal data | `privacy.check` |
| `doctor [--remote]` | compares the repo with the scaffold | `doctor.diagnose` |
| `curated-check [--base]` | what a commit (or a branch) does to the curated files; fails on a large loss | `curated.file_changes` |

The hooks:
- `connect` opens the database for writing; `backup` needs it.
- `status` returns the app's summary lines.
- `privacy_terms` returns the app's own personal terms.

`backups` and `publishing` follow the template's `backup` and `motherduck` options: when one is False, its
commands are left out. `privacy-check` is a capability every app has.

The module also exports helpers for the app's own commands:
- `fail(message)` prints the message and exits with status 1.
- `contract_line(spec, problems)` prints the contract check, as `ingest` does at the end.
- `backups_line(spec)` returns the backups line of `status`.

## `duckkit.demo`

**What it is for:** building a demo database safely, and making sure synthetic data never goes where the user's own
data goes. A demo database holds the marker table `demo_params` (the parameters it was built from), wherever its
file is.

- `build_demo(spec, connect, fill, params, path=None)`: builds a demo database at `path` (default
  `spec.demo_db_path`) and returns its path. `connect(path)` opens a new database with the app's schema (its
  `db/store.py` connect); `fill(con)` writes the made-up data; `params` (text, TOML say) is what rebuilds it, stored
  in the marker. It refuses `spec.db_path`, and replaces an existing file only if it is a demo database. If
  anything fails, it deletes the half-built file (and its `.wal`).
- `params(con)`: the parameters text of an open demo database, or None for one without the marker.

- `is_demo(spec, path=None)`: whether the database at `path` (default `spec.db_path`) holds the marker. The marker
  is the only test: a file at `spec.demo_db_path` without it is not a demo database. A missing file, or one that
  isn't a database, is not one either.
- `has_marker(con)`: the same check on an open connection.
- `MARKER`: `"demo_params"`. An app's demo builder creates this table.

`publish` refuses a demo database, and `status` says "Demo: made-up data" for one. An app's own commands that send or
curate data should refuse one too (`curated.curating` does).

## `duckkit.curated`

**What it is for:** decisions that cost time or money to make (a category chosen by hand, a model's
classification) and that the source files can't give again. docs/architecture.md ("Curated decisions") is the
canonical description of the flow. The database holds them. `curated/*.csv` is a copy in git, written after each
command and read only to rebuild a database.

A `CuratedTable(name, columns, order_by, where=None, key=None)` is one of two kinds:
- **its own rows** (no `key`): the decisions are the rows (a merchant and its category). `restore` inserts them.
- **decisions on the ingestion's rows** (`key`): the ingestion makes the rows, and a command fills in some columns
  (a SKU's product). `where` picks the rows that hold a decision, and `restore` updates rows by `key`, skipping keys
  the database doesn't have yet.

The functions:
- `curating(spec, connect, tables, restores=False)`: the connection for every command that changes a decision. It
  exports the tables after the command, and after a failure too. On a failure it rolls back the half-finished
  transaction, and exports what earlier batches committed. It raises `Refused` (a `ValueError`) in two cases:
  - a demo database;
  - a database that holds no decisions while the files hold some: a rebuilt database that `ingest` has not restored
    yet. The export would replace the files with this command's decisions only. `ingest` passes `restores=True`,
    because it calls `restore` before the export.
- `export(con, directory, tables, held_decisions_before=False)`: writes `<name>.csv` per table, sorted by
  `order_by`. It replaces each file atomically. A database with no decisions at all never replaces files that hold
  some: it writes nothing and returns False. With `held_decisions_before=True` it writes anyway, because no
  decisions now means that a command removed them. `curating` passes it when the database held decisions as the
  command began.
- `restore(con, directory, tables, after=None)`: loads the files into a database with no decisions yet, in one
  transaction, and returns the rows per table (None when there was nothing to do). Run it at the end of the
  ingestion. A file written before a column existed restores the column empty; a missing file is skipped.
  `after(con)` runs in the same transaction: what the app derives from the decisions.
- `holds_decisions(con, tables)`: whether the database holds any.
- `file_changes(spec, base=None)`: what a change does to each curated file: its rows before and after, and the
  rows added and removed (a changed row is one of each). Without `base`, it compares the staged files with HEAD,
  for the next commit. With `base`, it compares the working tree with the point where the branch left `base`, for
  a PR. It counts CSV records, so a note with line breaks is one row. `FileChange.loses_many` is True when the file
  is emptied, or when it loses more than 5 rows and more than a tenth of its rows. The `curated-check` command
  (`add_standard_commands(..., curations=True)`) prints them. It fails on one that loses many, unless
  `ALLOW_CURATED_LOSS=1`.
- `not_manual(column="classified_by")`: SQL for "a model may redo this decision": not made by hand.

Name the decision columns the same way in every app: `classified_by` (`llm` or `manual`; a manual decision is never
overwritten by a model), `classified_at`, `model`, and an optional `note`.

## `duckkit.doctor`

**What it is for:** telling whether an app is in step with the scaffold, and what to do when it isn't.

`diagnose(spec, remote=False)` reads `.copier-answers.yml` and returns a `Report` of problems and notes. Problems
make `doctor` fail; notes don't. It checks that:
- the files come from the same release as the installed duckkit;
- with `--remote`, whether a newer release exists (`git ls-remote --tags` on the scaffold);
- with `--remote`, that a repo whose git holds `curated/` is not public on GitHub (`gh repo view`): a problem if it
  is, a note if `gh` can't tell;
- every file in `EXPECTED` is present, unless an option turns it off or `opt_out` lists it;
- every opted-out file is explained in `docs/deviations.md`.

CI runs `doctor` on every PR. `/catch-up` runs it with `--remote`.

## `duckkit.app.common`

**What it is for:** what every page needs. The app's own `app/common.py` binds these helpers to its spec and adds
its own.

| Name | Does |
|---|---|
| `load_contract_snapshot(spec)` | the contract snapshot, made once per process (`st.cache_resource`) and shared by every session |
| `con(spec)` | a new cursor on the snapshot, one per query, which is safe across Streamlit's threads |
| `sidebar(spec, caption=None)` | the top of every sidebar: how fresh the data is, the deployed version, *Reload data*, and the theme and idle watchers |
| `reload_button()` | clears the caches, so the next run takes a new snapshot |
| `watch_theme()` | reruns the page when the browser switches light/dark, so charts drawn in Python follow it |
| `watch_idle(spec)` | in a hosted app, sends a tab that has been idle for `idle_minutes` to `static/paused.html`, so Cloud Run can scale to zero |
| `table(df, headers=None, timezone=None, float_format="%.1f")` | `st.dataframe` with readable headers, local times and number formats |
| `header(column, known)` | `first_seen` → "First seen", unless `known` names it |
| `DATA_ERRORS` | `(FileNotFoundError, ContractError)`: the errors a page shows as "no data yet" |

## `duckkit.app.theme`

**What it is for:** charts that look the same in every app and stay readable in light and dark.
- `CATEGORICAL[mode]`: 8 colours, checked for colour-blind separation. Assign them in order and never cycle.
- `OTHER[mode]`: a grey for the rest.
- `INK[mode]`: text, grid, axis and surface colours. `PAGE[mode]`: Streamlit's background. `FONT`.
- `mode()` returns `"light"` or `"dark"`. It prefers what `watch_theme` saw, because `st.context.theme` can lag.
- `base_option(mode)` gives the ECharts options every chart shares: font, tooltip, animation.
- `entity_colors(names, mode)` gives each entity a fixed colour. Pass the full list, so a filter never repaints
  an entity. Entities past the eighth share `OTHER`.

## `duckkit.testing`

**What it is for:** tests that can't touch real data, and tests for the browser app that need no ingestion.
- `isolate(spec, tmp_path, monkeypatch, env=())` points every path of the spec into `tmp_path`: the database,
  `data/`, `curated/`, `config.toml` and the backups. It also unsets `MOTHERDUCK_TOKEN`, `<PREFIX>_APP_DB`, the
  privacy terms, and any `env` you name. Call it from an autouse fixture in `tests/conftest.py`.
- `contract_db(spec, path)` creates a database with the contract's exact shape and its `v_contract` row, still
  open so the test can fill it. The browser app's tests build their data this way.

## `duckkit.testing.guard`

**What it is for:** enforcing the contract boundary in every app's CI. `tests/app/test_contract_only.py`, which
the template keeps current, calls:

- `sql_problems(spec)`:
  - finds every SQL string in `spec.app_code`; an f-string's `{NAME}` is filled from the module's string
    constants;
  - lists the tables each one names, using DuckDB's own parser (`json_serialize_sql`);
  - runs each one against the reference schema;
  - fails on anything that is not a contract view, or on a column the contract doesn't have.
- `import_problems(spec, path)` lists the forbidden imports in one file: the modules in `spec.forbidden` and
  duckkit's ingestion modules.
- `loaded_problems(spec)` imports the app and its tests in a fresh interpreter and lists every forbidden module
  that got loaded, which catches indirect imports.
- `doc_problems(spec, doc)` checks that `docs/contract.md` has a section for every view, listing its columns in
  the schema's order.

There are also smaller helpers: `app_files`, `app_tests`, `sql_strings`, `tables`, `check_sql`, `imports`,
`forbidden_modules`.

---

## Hooks: where an app's domain goes in

| Hook | Where | Shape |
|---|---|---|
| Contract rules | `contract/__init__.py` | `Contract(rules=[(sql counting bad rows, message), …], checks=[fn(con) -> [problems]])` |
| Status | `cli.py` | `add_standard_commands(…, status=fn(con) -> [lines])` |
| Privacy | `cli.py` | `add_standard_commands(…, privacy_terms=fn(spec) -> {term: what})` |
| Schema | `db/store.py` | `store.connect(SPEC, schema.sql, SCHEMA_VERSION, MIGRATIONS)` |
| Personal settings | `spec.py` | `AppSpec(private_settings=…)` |
| Pages | `app/common.py` | binds duckkit's helpers to the spec and adds the app's own |

When an app needs something that no hook allows, that is a candidate for a new hook. Upstream it as
docs/upgrading.md explains.

## Compatibility

duckkit's version is the release version. Within a major version (in 0.x, each minor counts as a major), a
release only adds: new functions, new optional parameters, new spec fields with defaults. When a change needs an
app to change its code, CHANGELOG.md lists it under **Steps**.
