# Changelog

Each release tags the template and duckkit together (`vX.Y.Z`). An app moves to a release with
`/scaffold-update` (`copier update`). **Steps** are what an app must do by hand.

## Unreleased

- Template: CLAUDE.md says what its `@.claude/project-rules.md` line does; docs/scaffold.md says "options", not
  "feature flags".

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
