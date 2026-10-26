# Changelog

Each release tags the template and duckkit together (`vX.Y.Z`). An app moves to a release with
`/scaffold-update` (`copier update`). **Steps** are what an app must do by hand.

## Unreleased

- duckkit: `spec-diff` counts each imported name that a spec test uses on its own. Adding another name to a shared
  `from … import a, b` line (for a new unit test) no longer shows as a change of the spec test.
- duckkit: **`duckkit.llm`**, behind the `llm` extra (`duckkit[llm]`): `Claude(spec).call(system, user, schema)`,
  one structured call with the system prompt cached, the server-side fallback and every failure as `LLMError`;
  `Usage` and `PRICES` for the cost of a run; `estimate_cost`; and `cost_gate`, which runs a paid command only with
  `--yes`. `duckkit.testing` has `FakeAnthropic` and `claude_reply`, so no test needs the network or a key.
- duckkit: `[anthropic] api_key` (`ANTHROPIC_API_KEY`) is a standard private setting: `spec.anthropic_api_key()`,
  `privacy-check` refuses its value in git, and `testing.isolate` unsets it. The guard keeps `duckkit.llm` out of
  the browser app.
- duckkit: the guard (`testing.guard.KIT_SERVICE`) also keeps `duckkit.curated` and `duckkit.specdiff` out of the
  browser app, as docs/kit.md already says (both are ingestion-side).
- Template: `/app-check` and the seeded browser checks switch the theme with the Light and Dark buttons of the ⋮
  menu (Streamlit no longer has them under Settings). An app can fix its own `docs/browser-checks.md` the same way.

## v0.6.1

- Template, how we work: **each PR keeps the spec, and Claude merges an extension with its feature when the
  reviewer agrees.**
  - docs/how-we-work.md, "Each PR keeps the spec": the one list of checks. A PR merges only when it shows that the
    app still does all that the spec says: the tests with `-m spec` and `-m realdata`, the contract check,
    `doctor`, `privacy-check`, the browser checks of the pages it changes, and (the reviewer) the architecture and
    the dashboard questions. ➖ only when a check does not apply. A check that cannot run in the session waits.
  - "Extensions and revisions": an extension adds to the spec and keeps each promise (a new browser check, a new
    view with a minor version). Claude merges it with its feature when the reviewer's answer agrees
    (`Extension agreed: <path>`). A revision alters or removes a promise, or edits the Guardrails, and waits for
    the user as before.
  - "The merge rule": every spec file is marked *extends*, none is in the Guardrails, and a review of the head
    commit agrees with each, with no blocking finding. Every review names the commit it read, and a later commit
    needs a new review.
  - CLAUDE.md, `/deliver-outcome`, the reviewer agent, the PR template (*extends* or *revises*, and more evidence),
    docs/review.md and docs/spec.md say the same. The `spec-change` label marks each PR that touches the spec.
  - The PR template and `/deliver-outcome` join the Guardrails of the seeded `.claude/spec-paths`.

**Steps:**
- `docs/spec.md` and `.claude/spec-paths` are seeded. Change their first sentence by hand, as the template's do, and
  add `.claude/skills/deliver-outcome/**` and `.github/pull_request_template.md` to the `[guardrails]` of
  `.claude/spec-paths` and to the Guardrails row of `docs/spec.md`.

## v0.6.0

**A new way of working** (docs/how-we-work.md): the user sets outcomes, Claude works on its own inside the app's spec,
and the user reviews only the changes to the spec.
- duckkit: `spec-diff [--base]`, a standard command, lists what a branch changes in the spec, and exits 1 if
  anything (`duckkit.specdiff`). It reads `.claude/spec-paths`. It counts a spec test (`@pytest.mark.spec`) that
  changed, went, or lost its mark, and reports dependency changes without counting them.
- Template, managed:
  - `docs/how-we-work.md` (the cycle) and `docs/review.md` (the review standards);
  - the `reviewer` agent (`.claude/agents/reviewer.md`) and the `/deliver-outcome` skill;
  - the hard stops: actions that cannot be undone (a publish, a deploy, an access change, deleting `data/` or
    `backups/`, `git clean`, a force-push, deleting a pushed tag) need the user's yes. CLAUDE.md has the rule.
    `.claude/settings.json` has Claude Code `ask` rules that prompt before the usual commands, in every mode;
  - the PR template, and a `spec` CI job that labels a PR that changes the spec (`spec-change`);
  - CLAUDE.md: a "How we work" section. Claude merges a PR that leaves the spec unchanged. Dependencies are reported,
    not asked for;
  - the `spec` pytest marker, and the template's guard test (`test_contract_only.py`) marked as spec.
- Template, seeded: `docs/spec.md` and `.claude/spec-paths` (the app's spec), and the example's key tests marked
  `@pytest.mark.spec`, each with a docstring that states its rule.
- duckkit: `doctor` expects the new managed files, `docs/spec.md` and `.claude/spec-paths`.
- duckkit: `spec-diff` exits 2 (can't tell) when a test file doesn't parse or git fails, instead of 1 (the spec
  changed).
- Fixes, `curations`:
  - `restore` keeps an empty text apart from a NULL. Before, a decision with an empty text came back as NULL.
  - `/rebuild-database` names the ingest command of `/ingest`, with the source files only when it takes them.
- Template: `/scaffold-update` takes the options to turn on in plain words (`/scaffold-update turn on cloud_run`),
  and docs/scaffold.md says so. It asks for an option's own answers (`gcp_project`, `gcp_region`, `motherduck_db`),
  and brings the seeded files of `demo_data` and `curations` from a fresh render.

**Steps:**
- Seeded files don't arrive with an update. Write `docs/spec.md` and `.claude/spec-paths` (the template's show
  how), with this app's own sub-docs and files. Mark this app's key functional tests `@pytest.mark.spec`, each
  with a docstring that states its rule.
- `.claude/settings.json` is now managed. Settings of your own move to `.claude/settings.local.json`. Add the
  app's own hard stops (a paid command, say) to its `ask` list, and list them in `docs/deviations.md`.
- Create the `spec-change` label, or let the first PR's CI create it. The CI job needs `pull-requests: write`.

## v0.5.2

- duckkit: **a git guard for the curated files.** `curated-check`, a standard command with
  `add_standard_commands(..., curations=True)`, lists what the next commit does to each curated file (rows before
  and after, added and removed). It fails when a file is emptied or loses more than 5 rows and a tenth of them,
  unless `ALLOW_CURATED_LOSS=1`. With `--base <branch>` it reports what a branch does, from where it left that
  branch. `curated.file_changes` is the function behind it.
- duckkit: `curating` refuses a demo database with `curated.Refused` (a `ValueError`), which names the `demo`
  command.
- Template, `curations`: the pre-commit hook runs `curated-check`. CLAUDE.md says that a commit that removes curated
  rows needs the user's yes. `ingest` catches only `Refused`, so any other error keeps its traceback.
  `/rebuild-database` is for the user to start only (`disable-model-invocation`), and its ingest step says not to
  run the other steps of `/ingest`, such as a paid classification.
- Docs: docs/architecture.md has a "Curated decisions" section: the source of truth (the database), the backup (the
  files), the write path (`curating()`), the read path (a rebuild), matching by key, and the guardrails.

**Steps:**
- With `curations` on: `cli.py` is seeded, so add `curations=True` to its `add_standard_commands(...)` call. The
  managed pre-commit hook runs `curated-check`, and fails without it.

## v0.5.1

- Template, `curations`: the seeded `/fix` skill is now `/fix-curation`, and says it corrects a curated decision in
  the database (not source data or code).

**Steps:**
- With `curations` on: seeded skills don't arrive with an update. Rename the app's `/fix` skill (or its own skill
  for correcting decisions) to `.claude/skills/fix-curation/`, and its `name:`.

## v0.5.0

- duckkit: `curated` keeps curated decisions in `curated/*.csv`, committed to git. `CuratedTable` describes a table
  (its own rows, or decisions on the ingestion's rows by `key`). `curating(spec, connect, tables)` is the connection
  for a command that changes decisions: it exports after the command, and after a failure, and refuses a demo
  database. `export` never lets a database without decisions replace files that hold some. `restore` loads the files
  into a rebuilt database in one transaction. `not_manual()` is the SQL for decisions a model may redo.
- duckkit: `spec.curated_dir` (`<root>/curated`); `testing.isolate` points it into the test's folder.
- duckkit: `doctor --remote` fails when git holds `curated/` and the GitHub repo is public. With `curations` on,
  `doctor` expects `curated/README.md` and `/rebuild-database`.
- Template: a new option, **`curations`** (default off): decisions kept in `curated/*.csv`, committed, restored into
  a rebuilt database; the repo must stay private.
  - Managed: the curated-decisions rule in CLAUDE.md, `curated/.*.tmp` in `.gitignore`, the `/rebuild-database`
    skill.
  - Seeded (new apps only): `src/<package>/curated.py` (the tables, `curating()`, `restore`), an example curated
    table `labels` with `label` / `unlabel` commands and a status line, `ingest` restoring curated/,
    `tests/test_curated.py`, `curated/README.md` and a `/fix` skill.
- Template: the ignore files' comments name `config.toml` (all apps) and `curated/` (with `curations`).

**Steps:**
- To adopt curations in an app that already keeps decisions in `curated/`: answer `curations: true`
  (`uvx copier update --trust -d curations=true`). Seeded files don't arrive with an update: write
  `src/<package>/curated.py` with the app's `CuratedTable`s (the template's shows how), run every command that
  changes a decision in its `curating()`, and call its `restore` at the end of `ingest`. Delete the app's own
  export and restore code. Keep (or write) `curated/README.md`: `doctor` expects it.

## v0.4.0

- duckkit: `demo.build_demo(spec, connect, fill, params, path=None)` builds a demo database. The app's `connect`
  makes the schema, its `fill` writes the made-up data, and the parameters go into the `demo_params` marker table.
  It refuses the real database, replaces an existing file only if that is a demo database, and deletes a half-built
  file. `demo.params(con)` reads the parameters back.
- duckkit: **the marker is the only test of a demo database.** A file at `spec.demo_db_path` without the
  `demo_params` table is no longer one, for `is_demo`, `publish` or `build_demo`.
- duckkit: `status` prints a "Demo: made-up data" line for a demo database.
- Template, `demo_data`: a new app gets a `demo` command, an example generator (`src/<package>/demo.py`), its test
  and a `/demo-data` skill. All four are seeded: the app's own once written.
- Template, `motherduck`: `docs/claude-chat.md` (template-managed), the instructions for a claude.ai project that
  asks the published copy through the MotherDuck connector. `/publish` gains the first-time setup of that project,
  and a reminder to press Sync in it when its files change.
- Template: `docs/deviations.md` says "Options", not "Feature flags" (new apps only: the file is seeded).

**Steps:**
- With `demo_data` on: seeded files never arrive with an update, so an existing app gets no `demo` command from
  it. Write one that calls `duckkit.demo.build_demo` (the template's `cli.py` and `demo.py` show how), or move the
  app's own builder onto it. Make sure every demo database the app builds holds the `demo_params` table: without
  it, `publish` no longer refuses the file.
- If the app's `status` hook printed its own demo line, remove it: `status` prints one now.
- With `motherduck` on: if the app had its own claude.ai instructions, move what only this app needs into its
  `/ask` skill, delete the old file, and point the claude.ai project's files at `docs/claude-chat.md`.

## v0.3.4

- duckkit: `AppSpec.page_modules` names the browser app's modules that run only inside a Streamlit session (a
  helper that declares a component when imported), beyond `views/` and `main.py`. The guard's loading check skips
  them, as it does the pages.

**Steps:** none.

## v0.3.3

- duckkit: clearer messages.
  - `status`: "N problems for the app", and for views older than the code, "→ `<cli> ingest` recreates the views".
  - `publish --check`: an up-to-date copy lists its rows per view. A stale copy gets a header that says how to fix it,
    and "N rows on both sides, with different contents" when only values changed.
  - A missing MotherDuck token names both `[motherduck] token` in config.toml and the `MOTHERDUCK_TOKEN` variable.

**Steps:** none.

## v0.3.2

- duckkit: `demo.is_demo(spec, path)` tells a demo database by its marker table `demo_params`, wherever its file is,
  or by being `spec.demo_db_path`. `publish` refuses one ("… is a demo database"); before, it only compared paths.
- CI and the template's workflows: `actions/checkout@v7` and `astral-sh/setup-uv@v10.3.2`, which run on Node 24
  (GitHub is retiring Node 20 for actions).

## v0.3.1

- Template: the landing page is `app/views/dashboard.py` (was the example `overview.py`), as in the apps; its spec
  is docs/dashboard.md. An app keeps the conventional file names (`views/dashboard.py`, `tests/test_cli.py`), so the
  seeded examples it replaces are its own files, with nothing to opt out of.
- Seeded files are written by `copier copy` only: an update never changes one, and never brings back one the app
  deleted (Copier's `_copier_operation` in `_exclude`; needs Copier 9.19). An app no longer opts out of the seeded
  examples it deleted.
- Template: CLAUDE.md says what its `@.claude/project-rules.md` line does; docs/scaffold.md says "options", not
  "feature flags".

**Steps:** an app that opted out of seeded files it deleted (its `src/` examples, `tests/test_*.py`, …) can drop
them from `opt_out` (`copier update -d 'opt_out=[…]'`) and from docs/deviations.md.

## v0.3.0

- **Options vs capabilities** (docs/template.md). A question is an answer (a name or value), an option (where apps
  truly differ) or nothing: a capability every app has.
  - Settings are in `config.toml` only. The `config_style` question and `.env` support are gone; environment
    variables still override the file.
  - `tailnet` and `privacy_hook` are no longer questions: every app has `app --tailnet`, `privacy-check` and the
    pre-commit hook.
  - `github_owner` is gone (nothing used it).
  - The options are `motherduck`, `cloud_run`, `backup` and `demo_data`.
- duckkit: `AppSpec.config_style`, `AppSpec.env_file`, `AppSpec.dotenv()` and `add_standard_commands(privacy=…)` are
  removed. `doctor` expects `.githooks/pre-commit` and `config.example.toml` in every app.
- Template: CLAUDE.md asks for a branch and a PR for every change (never `main`), stacked PRs for a change in
  parts, a phone notification after a long task, test data in files, and a talk before a new language or library.
- `/scaffold-update` and docs/upgrading.md: a seeded file an app deleted comes back on update unless opted out.
- Docs: docs/architecture.md (how an app made from the scaffold works), docs/kit.md module by module,
  docs/template.md (every answer and option, and what it decides), a longer README.
- `scripts/release.py` works through a PR: it commits the release on a branch; `--tag` tags it on main after the
  merge.

**Steps:**
- An app with a `.env`: move each setting to `config.toml` under its `[section] key`, then delete `.env`:
  `MOTHERDUCK_TOKEN` → `[motherduck] token`, `<PREFIX>_BACKUP_DIR` → `[backup] dir`, `<PREFIX>_PRIVACY_TERMS` →
  `[privacy] terms`, and the app's own `private_settings`. The update brings `config.example.toml`.
- `spec.py`: remove `config_style=…`. `cli.py`: remove `privacy=…` from `add_standard_commands`.
- An app that had `privacy_hook: false`: run `git config core.hooksPath .githooks`.

## v0.2.0

- duckkit: `status` reports the backups (how many, how old the newest is) in apps with backups.
- Template: CLAUDE.md's data rule mentions it, and wraps cleanly.

**Steps:** none.

## v0.1.0

The first release, drawn from several existing apps of this kind.

- duckkit: `AppSpec`, `Contract` (rules, `enum_rule`, `relation_rule`, custom checks), `snapshot`
  (`contract_snapshot`, `contract_copy`, `database_snapshot`, MotherDuck sign-in), `store` (schema version and
  migrations), `publish` (`plan`, `publish`, `compare`), `backup`, `privacy`, `serve` (localhost, `--tailnet`, several
  apps, `--demo`), `cli.add_standard_commands`, `doctor`, `app.common` (snapshot cache, sidebar, theme watcher,
  idle pause, tables), `app.theme`, `testing` (`isolate`, `contract_db`, `guard`).
- Template: flags `motherduck`, `cloud_run`, `tailnet`, `backup`, `privacy_hook`, `demo_data`, `extra_apps`,
  `config_style`, `opt_out`; skills `app`, `app-check`, `catch-up`, `scaffold-update`, `publish`, `backup`,
  `hosting`; the weekly `scaffold-update` workflow.
