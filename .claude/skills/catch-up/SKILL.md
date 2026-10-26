---
name: catch-up
description: Start-of-session briefing for duckviz-scaffold. Pulls main, lists open PRs (and which wait for the user), outcome issues and CI on main, shows what is merged since the last release, syncs duckkit, and shows which scaffold release each app on this machine is on.
when_to_use: >-
  Use when the user says things like "catch up", "where were we", "what's the state", "start of session".
allowed-tools: Bash(git fetch *) Bash(git status *) Bash(git pull --ff-only) Bash(git branch *) Bash(git worktree list) Bash(git log *) Bash(git describe *) Bash(git rev-list *) Bash(git tag *) Bash(gh pr list *) Bash(gh issue list *) Bash(gh run list *) Bash(uv sync --project kit) Bash(grep *)
---

# Catch up

1. **Git.** `git fetch --prune --tags`, `git status -sb`. On a clean `main` behind `origin/main`, `git pull
   --ff-only`. List the local branches that are not merged (`git branch --no-merged main`) and the worktrees
   (`git worktree list`): an old one may be left from earlier work.
2. **PRs.** `gh pr list --json number,title,labels,baseRefName,isDraft`. For each, say:
   - whether it waits for the user (the `spec-change` label, and its *Spec changes* section marks a change);
   - whether it is stacked on another PR (its base is not `main`).
3. **Issues.** `gh issue list --limit 10`, and the open outcomes (`--label outcome`).
4. **CI on main.** `gh run list --branch main --limit 3`. Say if the last run failed.
5. **Release.** The newest tag (`git tag --sort=-v:refname | head -1`), and the merges since it
   (`git log --oneline --merges <tag>..origin/main`). Say whether CHANGELOG.md has an "Unreleased" section, and
   whether it has **Steps**. Do not suggest a release unless the user's outcome includes one (CLAUDE.md).
6. **duckkit.** `uv sync --project kit`.
7. **The apps on this machine.** For each folder next to this repo with a `.copier-answers.yml` whose `_src_path`
   names duckviz-scaffold (`grep -l duckviz-scaffold ../*/.copier-answers.yml`), show its `_commit` against the
   newest tag. An app behind it can update with `/scaffold-update`. The app names stay in the chat: never write
   them in a file, a PR or a commit of this repo (CLAUDE.md, "This repo is public").

Report in a short list: what changed, what waits for the user, what needs attention, and a suggested next step.
Change nothing beyond the pull and `uv sync`.
