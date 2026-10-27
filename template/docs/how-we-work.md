# How we work

The user sets **outcomes**. Claude works on them for long sessions, with no review of each step. The **spec** says
what the app must keep doing. Each PR shows with evidence that it keeps the spec, and Claude merges it. The user
reviews only the PRs that revise what the spec promises, and reads the evidence for the rest. This doc is the
canonical description of the cycle. `/deliver-outcome` runs it.

## The spec

The spec is the set of documents and tests that describe what the app is for, its contracts and its guardrails.
It protects the app against regressions: each PR must keep it, and only the user revises what it promises. It has five
parts:
- **Purpose:** what the app is for, and the questions it answers (`docs/dashboard.md`).
- **Shape:** how the app is built (`docs/architecture.md` and its sub-docs, `docs/cli.md`).
- **Data:** the contract and the schemas.
- **Behaviour:** the browser checks, the real-data tests and the spec tests.
- **Guardrails:** CLAUDE.md, `.claude/settings.json`, CI, the review standards.

`docs/spec.md` lists the files of each part. `.claude/spec-paths` holds the same list as patterns, for the tools.

**Spec tests** are the functional tests of the key rules of the business logic, marked `@pytest.mark.spec`. The
docstring of each spec test states the rule that it enforces. A new spec test is not a spec change. A spec test that
changes, goes, or loses its mark is.

**Reported, not spec:** dependency changes and new release tags. The PR text and the outcome report list them.

`spec-diff` tells what a branch changes in the spec. It is a standard command of every app (`uv run <app>
spec-diff`). In the scaffold repo, run `uv run --project kit python -m duckkit.specdiff`. CI runs it on every PR and
adds the `spec-change` label when the PR touches a spec file.

`spec-diff` counts a spec test's code with the module-level names it uses, and `conftest.py` is spec as a whole. It
does not follow a helper imported from another module: if a spec test relies on one, add that module to
`.claude/spec-paths`.

## Each PR keeps the spec

Most work leaves the spec as it is, or only adds to it: a fix, a refactor, a new feature. Such a PR merges only when
it shows that the app still does all that the spec says. This is the one list of the checks:
1. `pytest -q`, `pytest -m spec` and `pytest -m realdata` pass.
2. The contract check (`status`), `doctor` and `privacy-check` are clean.
3. The browser checks of each page that the PR changes pass, in light and dark mode (`/app-check`). A PR that
   changes a shared part, such as the theme, the sidebar or a query that several pages use, walks all the checks.
4. The code still works as docs/architecture.md and docs/cli.md say: the browser app reads only the contract, the
   commands keep their names and options, and the data flows the same way.
5. Each question of docs/dashboard.md that the PR's pages answer still has its answer.

Claude runs checks 1 to 3 and shows each result in the PR's *Evidence* section. The reviewer checks 4 and 5 from
the diff and the docs.

A check that fails stops the merge: fix the code. If the check is wrong now, that is a revision of the spec (below),
and it waits for the user. Never weaken a check so that it passes.

A check marked ➖ (does not apply) is allowed only when it does not apply: the PR changes no page, or the app has no
real-data tests yet (`pytest -m realdata` then selects none). When a check applies but cannot run in this session
(no real data here, no browser), the PR waits until it can run. A `pytest -m realdata` run in which every test skips
cannot run.

In the scaffold repo, the checks are the kit's tests and ruff, `scripts/render.sh` and `spec-diff`, and the reviewer
checks that the code still does what the Shape docs say.

## Extensions and revisions

A PR that touches a spec file makes a **spec change** of one of two kinds.

**An extension** adds to the spec and keeps each promise that it already makes. A new feature brings one, such as:
- a new browser check, a new question in docs/dashboard.md, a new real-data test;
- a new view or column in the contract, with a minor version;
- a new command or option in docs/cli.md, a new section of docs/architecture.md for a new part;
- a new table, with its migration.

Claude merges an extension on its own, in the same PR as the feature that needs it. The report lists it. The user
can undo it later with a revert, which removes the feature too.

### The merge rule

Claude merges a PR that touches a spec file only when:
1. each file that `spec-diff` lists under "Spec changes" is marked *extends* in the PR's *Spec changes* section, and
   none of them is in the `[guardrails]` group;
2. a review of the PR's current head commit has no blocking finding, and has an `Extension agreed: <path>` line for
   each of those files;
3. the PR's *Evidence* section records each of those lines, with the commit that the review read.

Claude does not ask new reviewers until one agrees. A file that a reviewer does not agree is an extension stays a
revision, unless a later commit changes that file. The PR text then lists the finding and the fix.

**A revision** alters or removes a promise: it edits or removes a browser check, a question, a test or a rule,
renames or removes a view or column (a major version), changes what a command does, or changes the architecture.
Any edit to the Guardrails is a revision, even one that only adds a rule: they define how Claude works. A revision
waits for the user, in a PR of its own.

When an edit does both, it is a revision. When Claude is not sure, it is a revision.

## The cycle

1. **The user opens a GitHub issue** with the label `outcome`. One or two sentences are enough.
2. **Claude posts a brief** on the issue:
   - the acceptance criteria, as scenarios: questions in `docs/dashboard.md`, browser checks, tests;
   - the extensions and revisions of the spec that it expects;
   - the guardrails the outcome touches;
   - the PRs it plans, in order;
   - the risks, and how to roll back.

   The user approves the brief in a comment. This is the one fixed point where Claude waits.
3. **Claude works.**
   - Each change is a branch and a PR. A change in parts is a stack of PRs, each on the one before.
   - Each PR passes CI, `spec-diff` and an independent review (below), and shows that it keeps the spec.
   - **Claude merges a PR that leaves the spec unchanged or extends it**, with a merge commit.
   - **A PR that revises the spec waits for the user.** It holds only the revision, and says why. Claude sends a
     push notification, and goes on building on top of it, in PRs stacked on it. This is branch prediction: when
     the user approves, the work on top is ready. When the user rejects it, Claude closes the PR and drops or redoes
     the PRs on top. `main` never held the change, so nothing needs a revert.
   - Work that doesn't depend on a waiting revision goes on from `main`.
   - The data stays safe. Before any command that changes data, Claude runs `backup` (or, in an app without
     backups, copies the database file), and it tries things on copies of the database.
   - The hard stops (below) need the user's yes.
4. **Claude posts the report** on the issue, and closes it:
   - each acceptance criterion, with its evidence;
   - "the spec holds", shown by: the same tests passing, and the new ones; `pytest -m spec` and `pytest -m
     realdata` passing; all the browser checks walked in light and dark mode, with screenshots; `doctor` and
     `privacy-check` clean;
   - the spec files that each merged PR touched (`spec-diff`), and each extension and revision, with its PR and
     the command that reverts it: `git revert -m 1 <merge commit>`.
   - the dependencies and tags that changed.

## The independent review

The reviewer agent (`.claude/agents/reviewer.md`) reviews each PR against `docs/review.md`. It starts with a fresh
context, and gets the PR and the spec, never Claude's reasoning. It looks for bugs, for code and text a reader cannot
follow, for simpler solutions, for brittle ones, for code that no longer does what the spec says, and for spec
changes the PR does not declare. Each finding is *blocking*, *should* or *nit*. Its answer names the commit that it
read. For each spec file that the PR marks *extends*, the answer has a line that agrees, or a blocking finding.

A commit after the review needs a new review, in every PR.

Claude fixes the blocking findings, and asks a new reviewer to look again. When Claude and the reviewer still do
not agree on a blocking finding after a few rounds, Claude asks the user. The PR text lists the findings Claude did
not fix, with the reason.

## What waits for the user

Two kinds of action wait for the user. They are different.

**Merging a PR that revises the spec.** Claude never does it. The user merges it, or tells Claude to. A merge can
be reverted (`git revert -m 1`), so this is a rule of CLAUDE.md. CI's `spec-change` label shows each PR that
touches a spec file. The PR's *Spec changes* section says whether each one is an extension or a revision.

**The hard stops:** actions that cannot be undone. Claude never does them without the user's yes in the chat, for
that action:
- actions with consequences outside the repo: publishing, deploying, changing who can open the hosted app, a command
  that costs money (a paid classification), anything sent to another person;
- actions that destroy data that cannot be got back: deleting `data/` or `backups/`, `git clean` (it deletes the
  ignored files, and `data/` is one of them), a force-push, deleting a pushed tag.

The exception is a small classification, with the `llm` option: a run of `classify` of at most 500 rows
(`duckkit.llm.SMALL_RUN`) that redoes no decision already made. Claude states its cost and runs it, and the spending
limit of the API key caps it. A larger run, a run that redoes decisions, or a large run split into small ones is a
hard stop.

Everything else can be undone with git, a backup or a rebuild, so Claude goes on without asking.

The rule is in CLAUDE.md. `.claude/settings.json` backs it up: its `ask` rules make Claude Code prompt the user
before the usual commands for these actions, in every permission mode. Claude Code matches each part of a compound
command (`cd x && …`) on its own. The rules match the command text, so they can miss a command written another way.
That is acceptable: they are a safety net for a mistake, not the rule itself. An app adds the commands of its own
(a large paid run, say) to the list.
