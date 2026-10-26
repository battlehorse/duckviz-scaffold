---
name: catch-up
description: Start-of-session briefing for duckviz-scaffold. Pulls main, lists open PRs (and which wait for the user), outcome issues and CI on main, shows the merges since the last release, syncs duckkit, and shows which scaffold release each app on this machine is on.
when_to_use: >-
  Use when the user says things like "catch up", "where were we", "what's the state", "start of session".
allowed-tools: Bash(git fetch *) Bash(git status *) Bash(git pull --ff-only) Bash(git branch --no-merged *) Bash(git worktree list) Bash(git log *) Bash(git describe *) Bash(gh pr list *) Bash(gh issue list *) Bash(gh run list *) Bash(uv sync --project kit) Bash(grep -H *)
---

# Catch up

1. **Git.** `git fetch --prune --tags`, `git status -sb`. On a clean `main` behind `origin/main`, `git pull
   --ff-only`. List the local branches that `origin/main` does not hold (`git branch --no-merged origin/main`) and
   the worktrees (`git worktree list`). Earlier work can leave an old worktree.
2. **PRs.** `gh pr list --json number,title,labels,baseRefName,isDraft,body`. For each PR, say:
   - whether it waits for the user. It waits when its *Spec changes* section marks a revision, or when a file
     marked *extends* has no `Extension agreed` line in its *Evidence* yet (docs/how-we-work.md).
   - whether another PR is its base (its base is not `main`).
3. **Issues.** `gh issue list --limit 10`, and the open outcomes (`gh issue list --label outcome`).
4. **CI on main.** `gh run list --branch main --limit 3`. Say if the last run failed.
5. **Release.** The newest tag (`git describe --tags --abbrev=0 origin/main`), and the merges since that tag
   (`git log --oneline --merges <tag>..origin/main`). Say whether CHANGELOG.md has an "Unreleased" section, and
   whether that section has **Steps**. Do not suggest a release unless the user's outcome includes one (CLAUDE.md).
6. **duckkit.** `uv sync --project kit`.
7. **The apps on this machine.** `grep -H -e '^_src_path:' -e '^_commit:' ../*/.copier-answers.yml`. For each
   folder whose `_src_path` names duckviz-scaffold, show its `_commit` against the newest tag. An app behind the
   tag can update with `/scaffold-update`. When the command finds no file, say that this machine has no apps. The
   app names stay in the chat: never write them in a file, a PR or a commit of this repo (CLAUDE.md, "This repo is
   public").

Report in a short list: what changed, what waits for the user, what needs attention, and a suggested next step.
Change nothing beyond the pull and `uv sync`.
