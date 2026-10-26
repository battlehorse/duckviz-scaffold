# The spec

The spec of duckviz-scaffold is what the scaffold must keep doing. Each PR keeps it, and Claude merges a PR that
leaves it unchanged or only extends it (docs/how-we-work.md). A PR that changes what it promises waits for the user.
`.claude/spec-paths` holds the same list as patterns, for `spec-diff` and CI: keep the two in step.

A release changes every app that updates to it. So the scaffold's spec is what the apps depend on: how an app is
built, the interface that apps call, and the guardrails of every app and of this repo.

| Group | What it defines | Its canonical docs and files |
|---|---|---|
| **Shape** | how an app made from the scaffold works, what duckkit and the template hold, and how apps stay current | `docs/architecture.md`, `docs/kit.md`, `docs/template.md`, `docs/skills.md`, `docs/upgrading.md` |
| **API** | what apps depend on: duckkit's public names and the `AppSpec` fields, and the Copier questions with the files that are managed or seeded | `kit/src/duckkit/__init__.py`, `kit/src/duckkit/spec.py`, `copier.yml` |
| **Guardrails** | how the work is done, in this repo and in every app, and what it must not do | this repo's CLAUDE.md, `.claude/settings.json`, `.claude/spec-paths` and this file; the template's CLAUDE.md, settings, agents, `/deliver-outcome`, spec files, PR template, CI, git hooks, `pyproject.toml` (its pytest settings and its dependencies) and guard test; `docs/how-we-work.md`, `docs/review.md`; `specdiff.py`; this repo's CI and `scripts/render.sh` |

## What is not in the spec

- **The rest of duckkit's code and the template's other files.** They change with each fix. The tests, `render.sh`
  and the reviewer check them, and the docs of the Shape group say what they must do.
- **The tests.** The scaffold has no spec tests: its rules are in the Shape docs, and the kit's tests and the
  rendered sample apps check them. A test changes with the code it tests.
- **README.md.** It introduces the scaffold. It follows the docs above and says nothing they don't.
- **This repo's tools:** `scripts/release.py` and the `/upstream` skill change with the code. The reviewer agent and
  the PR template here are links to the template's files, which are in the spec.
- **CHANGELOG.md.** Every PR adds to it. Its **Steps** (what an app must do by hand) come from a change to the API
  or the template. The PR that makes that change names them, and the user reviews them before each release.

## Outside the spec, and reported

- duckkit's dependency changes (`kit/pyproject.toml`, `kit/uv.lock`) and new release tags: the PR text and the
  outcome report list them. A change to the template's dependencies is a spec change: its `pyproject.toml` is in
  the Guardrails.
- Not files, but always the user's call (the hard stops of docs/how-we-work.md): a force-push, moving or deleting a
  pushed tag, `git clean`.
