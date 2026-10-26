# duckviz-scaffold

The scaffold for apps that ingest data with Python into DuckDB, offer it through a versioned SQL contract, and show
it in a Streamlit app that reads only the contract. Two parts release together under one `vX.Y.Z` tag:
- `kit/`: **duckkit**, the shared Python code. Apps depend on it pinned to a tag.
- `template/` and `copier.yml`: the **Copier template**. Apps update with `copier update`.

This repo works the same way as the apps made from it. This file follows the template's CLAUDE.md
(`template/CLAUDE.md.jinja`): the same sections, with this repo's rules in place of an app's.

Read these first:
- README.md
- docs/architecture.md: how an app made from the scaffold works.
- docs/kit.md: duckkit, module by module.
- docs/template.md: the template: answers, options and capabilities, the files it manages, deviations.
- docs/skills.md: the skills the template writes, and the option that adds each one.
- docs/upgrading.md: the cycle (discover → upstream → release → apply), and adopting the scaffold in an existing
  repo.
- CHANGELOG.md
- docs/how-we-work.md, docs/spec.md and docs/review.md: how we work, what the spec is, and the review standards.
  docs/how-we-work.md and docs/review.md are the template's files (`template/docs/`), linked here.

## How we work

The user sets outcomes (GitHub issues with the label `outcome`). Inside the spec (docs/spec.md), you work on your
own: long sessions, PRs you merge yourself. A revision of the spec waits for the user's approval, but you go on
building on top of it, in stacked PRs. docs/how-we-work.md is the canonical description.
- **Every change is a PR.** Each PR passes CI and the `reviewer` agent. Run
  `uv run --project kit python -m duckkit.specdiff` on it: it lists the spec files that it touches, which the PR
  must name.
- **Each PR keeps the spec.** Run the checks of docs/how-we-work.md ("Each PR keeps the spec": in this repo, the
  kit's tests and ruff, `scripts/render.sh` and `spec-diff`), and show each result in the PR's *Evidence* section.
  When a check fails, fix the code. Never weaken a check so that it passes.
- **Merge a PR that leaves the spec unchanged or extends it** (`gh pr merge --merge`). An extension adds to the spec
  and keeps each promise that it already makes (docs/spec.md, "Extensions and revisions here"). It goes in the PR
  of its feature, and follows the merge rule of docs/how-we-work.md ("The merge rule").
- **Never merge a PR that revises the spec**: one that alters or removes a promise, or edits the Guardrails. The
  user merges it, or tells you to. Keep it in a PR of its own. When you are not sure, it is a revision.
- **Name each spec file the PR touches** in its *Spec changes* section, marked *extends* or *revises*.
- **Report** dependency changes and new tags in the PR and in the outcome report.
- **A release is part of an outcome.** It ships to every app, so its PR names the apps' **Steps**. Make the release
  PR and the tag only when the user's outcome includes them.
- **The hard stops** (docs/how-we-work.md, "What waits for the user"): an action that cannot be undone needs the
  user's yes in the chat first, for that action. In this repo: a force-push, deleting or moving a pushed tag, and
  `git clean`. `.claude/settings.json` makes Claude Code prompt before the usual commands. Never write a command
  another way to avoid the prompt.

## Rules

- **This repo is public.** It names no real app and holds no personal data: no names of apps made from it, no
  hosts, tokens, places or real readings. This holds for PR texts, comments and commit messages too. Examples, tests
  and docs use made-up apps and synthetic data (the `shop` contract of `kit/tests/conftest.py`, `shopviz`).
- **Apps depend on what is released.** A release changes every app that updates to it:
  - Keep duckkit's public functions and the spec's fields compatible. When a change needs an app to change its
    code, the CHANGELOG entry lists it under **Steps**.
  - Each change has a CHANGELOG entry under "Unreleased", or under the next version.
- **Code that every app has goes in duckkit**, made general through `AppSpec` or a hook. **Files that every app has
  go in the template.** Domain code stays in the apps.
- **Capabilities by default, options rarely.** Something new is a capability that every app gets. It becomes an
  option (a `copier.yml` question, an `AppSpec` field or a duckkit switch) only when some apps should refuse it for
  a real cost or risk, and turning it off removes something real (docs/template.md, "Options or capabilities").
  - Never offer two ways of doing the same thing: pick one for every app and migrate the apps that do it the other
    way. Settings, for example, are in `config.toml` only; `.env` is not supported.
  - In duckkit, an `AppSpec` field or a parameter of `add_standard_commands` exists only when apps truly differ: a
    name, a hook for domain code, or the switch behind an option. A behaviour every app should have gets no switch.
  - When you add a question or a switch, say in the PR which kind it is and why.
- **The browser app imports only** duckkit's `spec`, `contract`, `snapshot` and `app.*` modules. The other modules
  are for the ingestion side (`duckkit.testing.guard.KIT_SERVICE`).
- **Template files:** files that end in `.jinja` are rendered. Files in `_skip_if_exists` are seeded once and the
  app owns them; a change to them reaches only new apps, so the CHANGELOG **Steps** say what an app does by hand.
  The `/upstream` skill brings a change from an app into here.
- **Releases** go through a PR (`scripts/release.py`, docs/upgrading.md).

## Running

- Use `uv` for all Python work, and `uv run` for tests and scripts. Report a dependency you add to duckkit or to the
  template in the PR: every app gets it. Discuss a choice of language or library with the user before you build on
  it.
- Keep DuckDB at 1.5.x (`duckdb>=1.5.6,<2`). MotherDuck does not support DuckDB 2.0 yet.

## Tests and quality

- `cd kit && uv run pytest -q && uv run ruff check .` must pass.
- `scripts/render.sh` must pass after a change to the template, `copier.yml` or duckkit. It renders three sample
  apps (every option on, every option off, and curations), then runs their ruff, tests and `doctor`. CI runs it.
- Run the tests after a significant change. When a test fails, find the cause and fix it before you continue.

## Notifications

- When a task takes more than a few minutes, tell the user's phone when it is done (the `PushNotification` tool).

## Git

- Never commit or push to `main`. Make a branch, push it, and open a PR (`gh pr create`). When a change has several
  parts, send them as stacked PRs, each on the one before.
- Merge with a merge commit, so that each merge reverts on its own. Branches are deleted on merge.
- Never force-push, and never move or delete a pushed tag.
