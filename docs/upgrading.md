# The cycle: discover, upstream, release, apply

## 1. Discover

While working in one app, you build something every app of this kind could use: a "data freshness" badge, a new
publish check, a skill. The app's CLAUDE.md (template-managed) tells Claude to stop and propose upstreaming it
instead of keeping it local. Signs that something is common: it doesn't mention the domain; another app already
has a copy; it is infrastructure (CI, hosting, serving, backups).

## 2. Upstream

In this repo, run `/upstream <app path> <what>` (the skill in `.claude/skills/upstream`). It:
1. reads the change in the app (a diff, a branch, or files);
2. splits it: **code** → duckkit, generalised through the spec or a hook, with tests in `kit/tests`; **files** →
   `template/`, behind a flag if not every app wants it; **docs** → docs/kit.md, docs/template.md;
3. writes a CHANGELOG entry under a new version, with **Steps** for anything an app must do by hand (rename a call,
   add a hook);
4. runs the kit's tests and `scripts/render.sh`.

## 3. Release

```sh
uv run --project kit scripts/release.py 0.2.0   # sets the versions, commits, tags v0.2.0
git push origin main v0.2.0
```

## 4. Apply

In each app, either:
- wait for the weekly `scaffold-update` workflow: it runs `copier update` and opens a PR, with conflict markers if any;
- or run `/scaffold-update` (in Claude Code). It updates, resolves conflicts using docs/deviations.md, follows the
  CHANGELOG's steps, runs ruff, the tests and `doctor`, and opens a PR.

To turn on a feature an app lacks: `/scaffold-update -d cloud_run=true`, then the feature's docs (docs/hosting.md).

## Adopting the scaffold in an existing repo

For a repo that predates the scaffold (heatmiserviz, amex-parser, sainsburysviz):

1. **Move the shared code to duckkit first**, on a branch: add `spec.py`; replace the app's copies of the snapshot,
   contract check, publish, backup, privacy, serving and standard commands with duckkit calls; keep the domain
   parts as hooks; delete the copies. The tests must pass unchanged in behaviour.
2. **Apply the template over it**: `uvx copier copy --trust --vcs-ref vX.Y.Z gh:battlehorse/duckviz-scaffold .`
   with the app's answers (`-d project_name=… -d app_port=…`, the flags). Copier asks before overwriting each
   existing file: say **no** to the app's own files (seeded ones are skipped anyway) and **yes** to template-managed
   ones, then review the diff file by file with `git diff`, putting back what the app needs.
3. Move CLAUDE.md's domain rules to `.claude/project-rules.md`; list the deviations in docs/deviations.md.
4. `uv run <cli> doctor` must pass. From now on, `copier update` works.
