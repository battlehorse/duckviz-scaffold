# duckviz-scaffold

The scaffold for apps that ingest data with Python into DuckDB, offer it through a versioned SQL contract, and show
it in a Streamlit app that reads only the contract. Two parts release together under one `vX.Y.Z` tag:
- `kit/`: **duckkit**, the shared Python code. Apps depend on it pinned to a tag.
- `template/` and `copier.yml`: the **Copier template**. Apps update with `copier update`.

Read these first:
- README.md
- docs/architecture.md: how an app made from the scaffold works.
- docs/kit.md: duckkit, module by module.
- docs/template.md: the template: answers, options and capabilities, the files it manages, deviations.
- docs/upgrading.md: the cycle (discover → upstream → release → apply), and adopting the scaffold in an existing repo.
- CHANGELOG.md

## Rules

- **This repo is public.** It names no real app and holds no personal data: no names of apps made from it, no
  hosts, tokens, places or real readings. Examples, tests and docs use made-up apps and synthetic data (the `shop`
  contract of `kit/tests/conftest.py`, `shopviz`).
- **Apps depend on what is released.** A release changes every app that updates to it:
  - Keep duckkit's public functions and the spec's fields compatible. When a change needs an app to change its
    code, the CHANGELOG entry lists it under **Steps**.
  - Each change has a CHANGELOG entry under "Unreleased", or under the next version.
  - Never move or delete a pushed tag.
- **Code that every app has goes in duckkit**, made general through `AppSpec` or a hook. **Files that every app has
  go in the template.** Domain code stays in the apps.
- **Capabilities by default, options rarely.** Something new is a capability that every app gets. It becomes an
  option (a `copier.yml` question, an `AppSpec` field or a duckkit switch) only when some apps should refuse it for
  a real cost or risk, and turning it off removes something real. Never offer two ways of doing the same thing:
  pick one and migrate the apps (settings are in `config.toml` only). When you add a question, say which kind it is
  and why (docs/template.md, "Options or capabilities").
- **The browser app imports only** duckkit's `spec`, `contract`, `snapshot` and `app.*` modules. The other modules
  are for the ingestion side (`duckkit.testing.guard.KIT_SERVICE`).
- **Template files:** files that end in `.jinja` are rendered. Files in `_skip_if_exists` are seeded once and the
  app owns them; a change to them reaches only new apps. The `/upstream` skill brings a change from an app into here.
- **Releases** happen only when the user asks, through a PR (`scripts/release.py`, docs/upgrading.md).

## Dependencies and tools

- Ask the user before you add a dependency to duckkit or to the template: every app gets it.
- Discuss a choice of language or library with the user before you build on it.
- Use `uv` for all Python work, and `uv run` for tests and scripts.
- Keep DuckDB at 1.5.x (`duckdb>=1.5.6,<2`). MotherDuck does not support DuckDB 2.0 yet.

## Tests and quality

- `cd kit && uv run pytest -q && uv run ruff check .` must pass.
- `scripts/render.sh` must pass after a change to the template, `copier.yml` or duckkit. It renders a sample app
  with every option on and one with every option off, then runs their ruff, tests and `doctor`. CI runs both.
- Run the tests after a significant change. When a test fails, find the cause and fix it before you continue.

## Notifications

- When a task takes more than a few minutes, tell the user's phone when it is done (the `PushNotification` tool).

## Git

- Commit only when the user asks.
- Never commit or push to `main`. Make a branch, push it, and open a PR (`gh pr create`) for the user to review and
  merge. When a change has several parts, send them as stacked PRs, each on the one before.
- Do not merge a PR, force-push or delete a branch unless the user asks.
