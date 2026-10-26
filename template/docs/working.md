# How we work

The user sets **outcomes**. Claude works on them for long sessions, with no review of each step. The user reviews
only changes to the **spec**, and reads the evidence for the rest. This doc is the canonical description of the
cycle. `/outcome` runs it.

## The spec

The spec is what changes only with the user's approval: what the app is for (`docs/dashboard.md`), how it is built
(`docs/architecture.md` and its sub-docs), the shape of its data (the contract and the schemas), how it behaves (the
browser checks, the real-data tests and the spec tests), and the guardrails (CLAUDE.md, the hooks, CI, the review
standards). `docs/spec.md` lists it, and explains each part. `.claude/spec-paths` holds the same list as patterns,
for the tools.

**Spec tests** are the functional tests of the key rules of the business logic, marked `@pytest.mark.spec`. A new
spec test is not a spec change. A spec test that changes, goes, or loses its mark is.

**Reported, not spec:** dependency changes and new release tags. The PR text and the outcome report list them.

`spec-diff` tells what a branch changes in the spec. It is a standard command of every app (`uv run <app>
spec-diff`). In the scaffold repo, run `uv run --project kit python -m duckkit.specdiff`. CI runs it on every PR and
adds the `spec-change` label when the spec changes.

## The cycle

1. **The user opens a GitHub issue** with the label `outcome`. One or two sentences are enough.
2. **Claude posts a brief** on the issue:
   - the acceptance criteria, as scenarios: questions in `docs/dashboard.md`, browser checks, tests;
   - the spec changes it expects;
   - the guardrails the outcome touches;
   - the PRs it plans, in order;
   - the risks, and how to roll back.

   The user approves the brief in a comment. This is the one fixed point where Claude waits.
3. **Claude works.**
   - Each change is a branch and a PR. A change in parts is a stack of PRs, each on the one before.
   - Each PR passes CI, `spec-diff` and an independent review (below).
   - **Claude merges a PR that leaves the spec unchanged**, with a merge commit.
   - **A PR that changes the spec waits for the user.** It holds only the spec change, and says why. Claude sends a
     push notification, and goes on building on top of it, in PRs stacked on it. This is branch prediction: when
     the user approves, the work on top is ready. When the user rejects it, Claude closes the PR and drops or redoes
     the PRs on top. `main` never held the change, so nothing needs a revert.
   - Work that doesn't depend on a waiting spec change goes on from `main`.
   - The data stays safe. Before any command that changes data, Claude runs `backup` (or, in an app without
     backups, copies the database file), and it tries things on copies of the database. The hard stops (below) need
     the user's yes.
4. **Claude posts the report** on the issue, and closes it:
   - each acceptance criterion, with its evidence;
   - "the spec is unchanged", shown by: `spec-diff` with no changes over the merged PRs; the same tests passing,
     and the new ones; `pytest -m spec` and `pytest -m realdata` passing; the browser checks walked in light and
     dark mode, with screenshots; `doctor` and `privacy-check` clean;
   - or each spec change, with its PR and the command that reverts it: `git revert -m 1 <merge commit>`.
   - the dependencies and tags that changed.

The user can also approve a spec change after it merged. Each merge is a merge commit, so it reverts on its own.

## The independent review

The reviewer agent (`.claude/agents/reviewer.md`) reviews each PR against `docs/review.md`. It starts with a fresh
context, and gets the PR and the spec, never Claude's reasoning. It looks for bugs, for code and text a reader cannot
follow, for simpler solutions, for brittle ones, and for spec changes the PR does not declare. Each finding is
*blocking*, *should* or *nit*.

Claude fixes the blocking findings, and asks a new reviewer to look again. After three rounds with blocking findings
left, Claude stops and asks the user. The PR text lists the findings Claude did not fix, with the reason.

## The hard stops

A Claude Code hook (`.claude/hooks/hard_stops.py`) checks each shell command:
- **refused in every mode:** pushing to `main` (`--all` too), force-pushing, moving or deleting a tag, a hard reset
  on `main`, and a merge that is not a merge commit;
- **the user confirms in a prompt:** publishing, deploying, changing who can open the hosted app, a paid
  classification, deleting or moving `data/`, `backups/`, `curated/` or a database file, and merging a PR that
  changes the spec (or whose spec check has not passed yet).

`uv add`, `uv remove` and new tags need no prompt: the PR and the report list them.

The hook reads each command as a shell would, closely enough for a command written in good faith. It follows `cd`,
`git -C`, `gh -R`, `bash -c`, `env`, `xargs`, `eval` and `uv run`. It does not catch a command hidden on purpose:
backticks or `$(…)`, a git alias, `python -c` with `subprocess`, or `gh api` to merge. Those break the rules, not
the hook.

`spec-diff` counts a spec test's code with the module-level names it uses, and `conftest.py` is spec as a whole. It
does not follow a helper imported from another module: if a spec test relies on one, add that module to
`.claude/spec-paths`.
