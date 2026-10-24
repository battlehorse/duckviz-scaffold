# Changelog

Each release tags the template and duckkit together (`vX.Y.Z`). An app moves to a release with
`/scaffold-update` (`copier update`). **Steps** are what an app must do by hand.

## v0.2.0

- duckkit: `status` reports the backups (how many, how old the newest is) in apps with backups.
- Template: CLAUDE.md's data rule mentions it, and wraps cleanly.

**Steps:** none.

## v0.1.0

The first release, drawn from heatmiserviz, sainsburysviz and amex-parser.

- duckkit: `AppSpec`, `Contract` (rules, `enum_rule`, `relation_rule`, custom checks), `snapshot`
  (`contract_snapshot`, `contract_copy`, `database_snapshot`, MotherDuck sign-in), `store` (schema version and
  migrations), `publish` (`plan`, `publish`, `compare`), `backup`, `privacy`, `serve` (localhost, `--tailnet`, several
  apps, `--demo`), `cli.add_standard_commands`, `doctor`, `app.common` (snapshot cache, sidebar, theme watcher,
  idle pause, tables), `app.theme`, `testing` (`isolate`, `contract_db`, `guard`).
- Template: flags `motherduck`, `cloud_run`, `tailnet`, `backup`, `privacy_hook`, `demo_data`, `extra_apps`,
  `config_style`, `opt_out`; skills `app`, `app-check`, `catch-up`, `scaffold-update`, `publish`, `backup`,
  `hosting`; the weekly `scaffold-update` workflow.
