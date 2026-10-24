---
name: upstream
description: Bring a capability built in one app (heatmiserviz, amex-parser, sainsburysviz, …) into the scaffold, so every app can get it with /scaffold-update. Splits the change into duckkit code and template files, generalises it, tests it, and drafts the CHANGELOG entry.
when_to_use: >-
  Use when the user says things like "upstream this", "move this into the scaffold", "make this available to the other apps", "this should be common".
argument-hint: "<app folder> [branch | commit | files] [what it is]"
---

# Upstream a capability

Arguments: $ARGUMENTS

Read docs/kit.md, docs/template.md and docs/upgrading.md first.

1. **Read the change** in the app: `git -C <app> diff main...<branch>`, a commit, or the files named. Say in two
   lines what the capability is, and which parts are domain-specific.
2. **Check it is common.** It must make sense for an app with a different domain. If part of it is domain-specific,
   that part stays in the app, and duckkit gets a hook for it (a spec field, a callback, a rule list).
3. **Split it:**
   - **Code that would be the same in every app** → `kit/src/duckkit/`. Take the spec (`AppSpec`) instead of the
     app's config; no app name, path or domain word in duckkit. Mind the sides: the browser app may import only
     `spec`, `contract`, `snapshot`, `app.*`. Add tests in `kit/tests/` with the sample contract.
   - **Files** (a skill, a doc, CI, Dockerfile) → `template/`, with the answers in place of names. If not every
     app wants it, put it behind a flag: a new question in `copier.yml` (default off for something new), and
     `{% if flag %}…{% endif %}` file names. Prefer seeded files (`_skip_if_exists`) for anything an app will rewrite.
   - **Docs** → docs/kit.md or docs/template.md.
4. **Draft the CHANGELOG entry** under the next version, with **Steps**: what an app's code must change by hand
   (a renamed function, a new hook to fill in, a flag to turn on). An app that has its own copy of the capability
   should delete it: say so in the steps.
5. **Check**: `cd kit && uv run ruff check . && uv run pytest -q`, then `scripts/render.sh`. Both must pass.
6. **Show the user** the split (what went to duckkit, what to the template, what stays in the app) and the
   CHANGELOG entry. Ask before you commit. A release is a separate step (`scripts/release.py`), on the user's word.
7. **The originating app** then moves to the release with `/scaffold-update` and deletes its own copy.
