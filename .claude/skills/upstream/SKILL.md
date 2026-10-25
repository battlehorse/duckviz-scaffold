---
name: upstream
description: Bring a capability built in one app into the scaffold, so every app can get it with /scaffold-update. Splits the change into duckkit code and template files, generalises it, tests it, and drafts the CHANGELOG entry.
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
     app should have it, make it an option, but only when docs/template.md's rule allows ("Options or
     capabilities"): some apps should refuse it for a real cost or risk, and turning it off removes something real.
     Otherwise it is a capability that every app gets. An option is a question in `copier.yml`, off by default, with
     `{% if option %}…{% endif %}` file names; say in the PR why it is an option. Prefer seeded files (`_skip_if_exists`) for anything an app will rewrite.
   - **Docs** → docs/kit.md or docs/template.md.
4. **Draft the CHANGELOG entry** under the next version, with **Steps**: what an app's code must change by hand
   (a renamed function, a new hook to fill in, an option to turn on). An app that has its own copy of the capability
   should delete it: say so in the steps.
5. **Check**: `cd kit && uv run ruff check . && uv run pytest -q`, then `scripts/render.sh`. Both must pass.
6. **Show the user** the split (what went to duckkit, what to the template, what stays in the app) and the
   CHANGELOG entry. Ask before you commit. Commit on a branch and open a PR, never on main. A release is a
   separate step (`scripts/release.py`, docs/upgrading.md), on the user's word.
7. **The originating app** then moves to the release with `/scaffold-update` and deletes its own copy.
