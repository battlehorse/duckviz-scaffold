# Changelog

Each release tags the template and duckkit together (`vX.Y.Z`). An app moves to a release with
`/scaffold-update` (`copier update`). **Steps** are what an app must do by hand.

## Unreleased

- Template: **`/app-check` has the browser tool's tips that every app needs**: wait for each rerun before the next
  click, the ⋮ menu that sometimes needs a second click, `browser_batch` for the steps you can predict, and the
  theme set back to System at the end. **Steps:** an app that wrote these tips in its own `docs/browser-checks.md`
  can remove them there; it keeps the tips for its own pages.

## v0.8.2

A fix, **a backup of a database with a macro that reads a view restores**. **`/rebuild-database` compares the
rebuilt database with a baseline**, and **`/catch-up` runs the app's own checks**, both from sections of
`.claude/project-rules.md`.

- Template: **`.gitignore` ignores only the root's `data/` and `backups/`.** `data/` matched `tests/data/` too, where
  CLAUDE.md asks for the tests' fixture files, so a new fixture was left out of git without a word. **Steps:** none
  (`.gitignore` is managed).
- Template: **`/catch-up` runs the app's own checks.** A "Catch-up" section in `.claude/project-rules.md` lists them
  (new source files not loaded yet, decisions that wait for a review), and `/catch-up` reports them with the rest.
  An app no longer edits the managed skill for its own lines. **Steps:** an app that added its own lines to
  `/catch-up` (a deviation) moves them to a "Catch-up" section in `.claude/project-rules.md`, takes the template's
  skill, and removes the deviation (new apps get an empty section).
- Template: **`/rebuild-database` compares the rebuilt database with a baseline.** Before the rebuild, it saves
  `status`, the row count and a fingerprint of each contract view, and the app's own baseline queries (a "Rebuild
  baseline" section in `.claude/project-rules.md`). After it, it runs them again and reports each difference, then
  runs `pytest` and `pytest -m realdata`. A difference that the rebuild was not for stops it, with the old database
  kept. **Steps:** optional: add a "Rebuild baseline" section with your own queries to `.claude/project-rules.md`
  (new apps get an empty one).
- duckkit: **a backup of a database with a macro that reads a view restores.** EXPORT DATABASE writes every macro
  before every view, so such a snapshot failed its own check (and `restore`). `backup` now writes the snapshot's
  schema.sql in an order that runs: each statement after what it reads. **Steps:** none. A snapshot made before
  this fix, which failed its check, is not repaired: make a new backup.

## v0.8.1

A fix: duckkit gives **no refresh hint for another app's database**.

- duckkit: **another app's database gets no refresh hint.** When `v_contract` names another contract, the browser
  app's snapshot refuses it and says to check `<PREFIX>_DB` (or the path given). Before, it gave `refresh_hint`,
  which tells the user to ingest or rebuild: on another app's database, a rebuild would change or delete it. A
  database with another major version of the same contract, or with no `v_contract`, keeps `refresh_hint`.
  **Steps:** none.

## v0.8.0

**One review for each PR** (on Sonnet, with no second review), a fuller **`/catch-up`** (a remote session, PR
stacks, tests after a pull), and wording fixes for the `hosted` flag.

- Template: **`/catch-up` does more.** It asks first whether the session is a long-running remote one: if yes, it
  keeps the Mac awake (`caffeinate -is`, macOS only: the process keeps running after the session) and tells the user
  to type `/remote-control`. It shows PR stacks from bottom to top, lists the remote branches already merged (for
  cleanup, never deleted), runs the tests after a pull that changed `src/` or `tests/`, and checks the health of each
  extra app. **Steps:** an app that kept its own richer `/catch-up` (a deviation) takes the template's, and keeps
  only its own lines.
- Template, how we work: **one review for each PR.** The reviewer agent reviews a PR once, when CI passes and the
  *Evidence* is complete. Claude then decides what to do with each finding: it fixes a blocking finding, fixes a
  should finding or gives the reason, and fixes a nit only in a commit that fixes something else. A blocking finding
  that Claude finds wrong makes the PR wait for the user. The fixes need no second review, and there are no rounds to
  count. The merge rule takes the one review's `Extension agreed` lines, so the reviewer writes them even when it has
  blocking findings about other things. A file marked *extends* that a commit after the review changes is a revision.
  The PR template has a *Review* section that lists each finding and what was done with it. docs/how-we-work.md,
  docs/review.md, the reviewer agent, `/deliver-outcome`, CLAUDE.md and the PR template say the same.
- Template: **the reviewer agent runs on Sonnet** (`model: sonnet`), which costs less. In a test on two earlier PRs,
  it found each blocking finding that Opus found, but it gave one of them a lower level. So Claude judges each level
  again: a should finding that shows a bug, or a gap in a guardrail, counts as blocking.
- duckkit and template: the `hosted` flag of `extra_apps` (`AppEntry`) says what it does. With `hosted: false` (the
  default in `extra_apps`), the app may read the whole database, and the browser app may never import it. With
  `hosted: true`, the browser app may import it, and the app should read only the contract (no test checks that).
  Only the browser app (`app`) goes to Cloud Run: one hosted app for each project. spec.py, snapshot.py,
  `copier.yml`, docs/kit.md, docs/template.md, docs/architecture.md and docs/hosting.md say so.
- Template, how we work: **the label `merged-by-claude`**. Before Claude merges a PR on its own (the spec unchanged,
  or only extended), it adds the label, so the user can find the work that the user did not review
  (`is:pr label:merged-by-claude`). CI creates the label with `spec-change`. docs/how-we-work.md ("The merge rule"),
  CLAUDE.md and `/deliver-outcome` say the same.
- Template: `/hosting` rollback lists the two newest revisions with their commits and asks the user with the
  previous one's commit; docs/hosting.md's manual rollback says the same.

## v0.7.0

**Decisions made by Claude** (the `llm` option), **freshness** (`status --remote`), **hosting in full** (the
guide and the `/hosting` skill) and a guard that keeps the browser app off the whole database.

- Template: **`/hosting`** (`cloud_run`) does each task in full: the settings, the deploy checks (a clean `main`, the
  tests, the user's OK), the new version checked with `status --remote`, a rollback, adding a person (a Google
  account, all the data) and removing one (an open tab stops at its next reconnect), the people, and the status.
- duckkit: `spec-diff` counts each imported name that a spec test uses on its own. Adding another name to a shared
  `from … import a, b` line (for a new unit test) no longer shows as a change of the spec test.
- duckkit: the guard also fails a browser app that uses `snapshot.database_snapshot` (`guard.WHOLE_DATABASE`), by
  import or as an attribute: a copy of the whole database, which a hosted app cannot read. The browser app reads the
  contract through `contract_snapshot` only.
- Template: **`docs/hosting.md`** (`cloud_run`) explains how the hosted app works, with diagrams: IAP and Google
  sign-in, Cloud Run's instances and live connection, the idle pause, the token secret, Cloud Build and Artifact
  Registry. It adds the costs, a step-by-step one-time setup (the billing link, the image cleanup policy, a budget
  alert, a read-only (read-scaling) token pasted at a hidden prompt, the OAuth client for a project with no
  organisation), updating, rolling back, sharing and deleting. An app that keeps its own `docs/hosting.md` (a
  deviation) keeps its side of the conflict, or drops the deviation and takes this one.
- duckkit: **`duckkit.llm`**, behind the `llm` extra (`duckkit[llm]`): `Claude(spec).call(system, user, schema)`, one
  structured call with the system prompt cached, the server-side fallback and every failure as `LLMError`; `Usage` and
  `PRICES` for the cost of a run; `estimate_cost`; and `cost_gate`, which shows a run's cost and starts a small run
  (at most `SMALL_RUN`, 500 rows waiting) at once, and a larger one, or a full reclassification (`full=True`), only
  with `--yes`. `duckkit.testing` has `FakeAnthropic` and `claude_reply`, so no test needs the network or a key.
- Template: a new option, **`llm`** (default off, asked only with `curations`): decisions made by Claude. It adds the
  `llm` extra, `[anthropic] api_key` in `config.example.toml`, and, seeded: `classify.py` (an example that labels the
  days whose value stands out), a `classify` command that shows the estimate and needs `--yes` over 500 days waiting,
  its test with `FakeAnthropic`, and a `/classify` skill. `.claude/settings.json` makes Claude Code ask before
  `classify --yes` (a large run). A small run is not a hard stop (docs/how-we-work.md): a spend limit in the Anthropic
  Console caps it. `render.sh`'s all-on sample turns it on.
- duckkit: `[anthropic] api_key` (`ANTHROPIC_API_KEY`) is a standard private setting: `spec.anthropic_api_key()`,
  `privacy-check` refuses its value in git, and `testing.isolate` unsets it. The guard keeps `duckkit.llm` out of
  the browser app.
- duckkit: **`status --remote`** says whether the published copy is current ("Published:", from `publish.compare`)
  and, with `cloud_run`, whether the hosted app runs the latest commit ("Deployed:", from the service's `commit`
  label against `origin/main`). A check that can't run says why in its line. `duckkit.hosting` reads the label.
- Template: `/catch-up` runs `status --remote` in place of `publish --check` and its own `gcloud` lines.
- duckkit: the guard (`testing.guard.KIT_SERVICE`) also keeps `duckkit.curated`, `duckkit.specdiff` and
  `duckkit.hosting` out of the browser app, as docs/kit.md already says (they are ingestion-side).
- Template: `/app-check` and the seeded browser checks switch the theme with the Light and Dark buttons of the ⋮
  menu (Streamlit no longer has them under Settings). An app's own `docs/browser-checks.md` is seeded: see Steps.

**Steps:**
- The guard now fails when the browser app's code (`app_code`: `app/`, `query/`, `analysis.py` by default) or its
  tests (`tests/app/`) use `snapshot.database_snapshot`. A helper that wraps `database_snapshot` for a local-only
  app or a command (in `query/`, say) moves out of `app_code`, for example next to the local-only app. A test in
  `tests/app/` that uses it moves out, or reads the contract with `contract_snapshot`.
- The guard also fails a browser app, or a test in `tests/app/`, that imports `duckkit.curated`, `duckkit.specdiff`
  or `duckkit.hosting`: move that code to the ingestion side.
- `docs/browser-checks.md` is seeded, so an update does not change it. Edit its theme check by hand to "⋮, then
  Light or Dark" (Streamlit no longer has the theme under Settings). In the app, that edit revises a browser check,
  so its PR declares it *revises* (docs/how-we-work.md).

## v0.6.1

- Template, how we work: **each PR keeps the spec, and Claude merges an extension with its feature when the
  reviewer agrees.**
  - docs/how-we-work.md, "Each PR keeps the spec": the one list of checks. A PR merges only when it shows that the
    app still does all that the spec says: the tests with `-m spec` and `-m realdata`, the contract check,
    `doctor`, `privacy-check`, the browser checks of the pages it changes, and (the reviewer) the architecture and
    the dashboard questions. ➖ only when a check does not apply. A check that cannot run in the session waits.
  - "Extensions and revisions": an extension adds to the spec and keeps each promise (a new browser check, a new
    view with a minor version). Claude merges it with its feature when the reviewer's answer agrees
    (`Extension agreed: <path>`). A revision alters or removes a promise, or edits the Guardrails, and waits for
    the user as before.
  - "The merge rule": every spec file is marked *extends*, none is in the Guardrails, and a review of the head
    commit agrees with each, with no blocking finding. Every review names the commit it read, and a later commit
    needs a new review.
  - CLAUDE.md, `/deliver-outcome`, the reviewer agent, the PR template (*extends* or *revises*, and more evidence),
    docs/review.md and docs/spec.md say the same. The `spec-change` label marks each PR that touches the spec.
  - The PR template and `/deliver-outcome` join the Guardrails of the seeded `.claude/spec-paths`.

**Steps:**
- `docs/spec.md` and `.claude/spec-paths` are seeded. Change their first sentence by hand, as the template's do, and
  add `.claude/skills/deliver-outcome/**` and `.github/pull_request_template.md` to the `[guardrails]` of
  `.claude/spec-paths` and to the Guardrails row of `docs/spec.md`.

## v0.6.0

**A new way of working** (docs/how-we-work.md): the user sets outcomes, Claude works on its own inside the app's spec,
and the user reviews only the changes to the spec.
- duckkit: `spec-diff [--base]`, a standard command, lists what a branch changes in the spec, and exits 1 if
  anything (`duckkit.specdiff`). It reads `.claude/spec-paths`. It counts a spec test (`@pytest.mark.spec`) that
  changed, went, or lost its mark, and reports dependency changes without counting them.
- Template, managed:
  - `docs/how-we-work.md` (the cycle) and `docs/review.md` (the review standards);
  - the `reviewer` agent (`.claude/agents/reviewer.md`) and the `/deliver-outcome` skill;
  - the hard stops: actions that cannot be undone (a publish, a deploy, an access change, deleting `data/` or
    `backups/`, `git clean`, a force-push, deleting a pushed tag) need the user's yes. CLAUDE.md has the rule.
    `.claude/settings.json` has Claude Code `ask` rules that prompt before the usual commands, in every mode;
  - the PR template, and a `spec` CI job that labels a PR that changes the spec (`spec-change`);
  - CLAUDE.md: a "How we work" section. Claude merges a PR that leaves the spec unchanged. Dependencies are reported,
    not asked for;
  - the `spec` pytest marker, and the template's guard test (`test_contract_only.py`) marked as spec.
- Template, seeded: `docs/spec.md` and `.claude/spec-paths` (the app's spec), and the example's key tests marked
  `@pytest.mark.spec`, each with a docstring that states its rule.
- duckkit: `doctor` expects the new managed files, `docs/spec.md` and `.claude/spec-paths`.
- duckkit: `spec-diff` exits 2 (can't tell) when a test file doesn't parse or git fails, instead of 1 (the spec
  changed).
- Fixes, `curations`:
  - `restore` keeps an empty text apart from a NULL. Before, a decision with an empty text came back as NULL.
  - `/rebuild-database` names the ingest command of `/ingest`, with the source files only when it takes them.
- Template: `/scaffold-update` takes the options to turn on in plain words (`/scaffold-update turn on cloud_run`),
  and docs/scaffold.md says so. It asks for an option's own answers (`gcp_project`, `gcp_region`, `motherduck_db`),
  and brings the seeded files of `demo_data` and `curations` from a fresh render.

**Steps:**
- Seeded files don't arrive with an update. Write `docs/spec.md` and `.claude/spec-paths` (the template's show
  how), with this app's own sub-docs and files. Mark this app's key functional tests `@pytest.mark.spec`, each
  with a docstring that states its rule.
- `.claude/settings.json` is now managed. Settings of your own move to `.claude/settings.local.json`. Add the
  app's own hard stops (a paid command, say) to its `ask` list, and list them in `docs/deviations.md`.
- Create the `spec-change` label, or let the first PR's CI create it. The CI job needs `pull-requests: write`.

## v0.5.2

- duckkit: **a git guard for the curated files.** `curated-check`, a standard command with
  `add_standard_commands(..., curations=True)`, lists what the next commit does to each curated file (rows before
  and after, added and removed). It fails when a file is emptied or loses more than 5 rows and a tenth of them,
  unless `ALLOW_CURATED_LOSS=1`. With `--base <branch>` it reports what a branch does, from where it left that
  branch. `curated.file_changes` is the function behind it.
- duckkit: `curating` refuses a demo database with `curated.Refused` (a `ValueError`), which names the `demo`
  command.
- Template, `curations`: the pre-commit hook runs `curated-check`. CLAUDE.md says that a commit that removes curated
  rows needs the user's yes. `ingest` catches only `Refused`, so any other error keeps its traceback.
  `/rebuild-database` is for the user to start only (`disable-model-invocation`), and its ingest step says not to
  run the other steps of `/ingest`, such as a paid classification.
- Docs: docs/architecture.md has a "Curated decisions" section: the source of truth (the database), the backup (the
  files), the write path (`curating()`), the read path (a rebuild), matching by key, and the guardrails.

**Steps:**
- With `curations` on: `cli.py` is seeded, so add `curations=True` to its `add_standard_commands(...)` call. The
  managed pre-commit hook runs `curated-check`, and fails without it.

## v0.5.1

- Template, `curations`: the seeded `/fix` skill is now `/fix-curation`, and says it corrects a curated decision in
  the database (not source data or code).

**Steps:**
- With `curations` on: seeded skills don't arrive with an update. Rename the app's `/fix` skill (or its own skill
  for correcting decisions) to `.claude/skills/fix-curation/`, and its `name:`.

## v0.5.0

- duckkit: `curated` keeps curated decisions in `curated/*.csv`, committed to git. `CuratedTable` describes a table
  (its own rows, or decisions on the ingestion's rows by `key`). `curating(spec, connect, tables)` is the connection
  for a command that changes decisions: it exports after the command, and after a failure, and refuses a demo
  database. `export` never lets a database without decisions replace files that hold some. `restore` loads the files
  into a rebuilt database in one transaction. `not_manual()` is the SQL for decisions a model may redo.
- duckkit: `spec.curated_dir` (`<root>/curated`); `testing.isolate` points it into the test's folder.
- duckkit: `doctor --remote` fails when git holds `curated/` and the GitHub repo is public. With `curations` on,
  `doctor` expects `curated/README.md` and `/rebuild-database`.
- Template: a new option, **`curations`** (default off): decisions kept in `curated/*.csv`, committed, restored into
  a rebuilt database; the repo must stay private.
  - Managed: the curated-decisions rule in CLAUDE.md, `curated/.*.tmp` in `.gitignore`, the `/rebuild-database`
    skill.
  - Seeded (new apps only): `src/<package>/curated.py` (the tables, `curating()`, `restore`), an example curated
    table `labels` with `label` / `unlabel` commands and a status line, `ingest` restoring curated/,
    `tests/test_curated.py`, `curated/README.md` and a `/fix` skill.
- Template: the ignore files' comments name `config.toml` (all apps) and `curated/` (with `curations`).

**Steps:**
- To adopt curations in an app that already keeps decisions in `curated/`: answer `curations: true`
  (`uvx copier update --trust -d curations=true`). Seeded files don't arrive with an update: write
  `src/<package>/curated.py` with the app's `CuratedTable`s (the template's shows how), run every command that
  changes a decision in its `curating()`, and call its `restore` at the end of `ingest`. Delete the app's own
  export and restore code. Keep (or write) `curated/README.md`: `doctor` expects it.

## v0.4.0

- duckkit: `demo.build_demo(spec, connect, fill, params, path=None)` builds a demo database. The app's `connect`
  makes the schema, its `fill` writes the made-up data, and the parameters go into the `demo_params` marker table.
  It refuses the real database, replaces an existing file only if that is a demo database, and deletes a half-built
  file. `demo.params(con)` reads the parameters back.
- duckkit: **the marker is the only test of a demo database.** A file at `spec.demo_db_path` without the
  `demo_params` table is no longer one, for `is_demo`, `publish` or `build_demo`.
- duckkit: `status` prints a "Demo: made-up data" line for a demo database.
- Template, `demo_data`: a new app gets a `demo` command, an example generator (`src/<package>/demo.py`), its test
  and a `/demo-data` skill. All four are seeded: the app's own once written.
- Template, `motherduck`: `docs/claude-chat.md` (template-managed), the instructions for a claude.ai project that
  asks the published copy through the MotherDuck connector. `/publish` gains the first-time setup of that project,
  and a reminder to press Sync in it when its files change.
- Template: `docs/deviations.md` says "Options", not "Feature flags" (new apps only: the file is seeded).

**Steps:**
- With `demo_data` on: seeded files never arrive with an update, so an existing app gets no `demo` command from
  it. Write one that calls `duckkit.demo.build_demo` (the template's `cli.py` and `demo.py` show how), or move the
  app's own builder onto it. Make sure every demo database the app builds holds the `demo_params` table: without
  it, `publish` no longer refuses the file.
- If the app's `status` hook printed its own demo line, remove it: `status` prints one now.
- With `motherduck` on: if the app had its own claude.ai instructions, move what only this app needs into its
  `/ask` skill, delete the old file, and point the claude.ai project's files at `docs/claude-chat.md`.

## v0.3.4

- duckkit: `AppSpec.page_modules` names the browser app's modules that run only inside a Streamlit session (a
  helper that declares a component when imported), beyond `views/` and `main.py`. The guard's loading check skips
  them, as it does the pages.

**Steps:** none.

## v0.3.3

- duckkit: clearer messages.
  - `status`: "N problems for the app", and for views older than the code, "→ `<cli> ingest` recreates the views".
  - `publish --check`: an up-to-date copy lists its rows per view. A stale copy gets a header that says how to fix it,
    and "N rows on both sides, with different contents" when only values changed.
  - A missing MotherDuck token names both `[motherduck] token` in config.toml and the `MOTHERDUCK_TOKEN` variable.

**Steps:** none.

## v0.3.2

- duckkit: `demo.is_demo(spec, path)` tells a demo database by its marker table `demo_params`, wherever its file is,
  or by being `spec.demo_db_path`. `publish` refuses one ("… is a demo database"); before, it only compared paths.
- CI and the template's workflows: `actions/checkout@v7` and `astral-sh/setup-uv@v10.3.2`, which run on Node 24
  (GitHub is retiring Node 20 for actions).

## v0.3.1

- Template: the landing page is `app/views/dashboard.py` (was the example `overview.py`), as in the apps; its spec
  is docs/dashboard.md. An app keeps the conventional file names (`views/dashboard.py`, `tests/test_cli.py`), so the
  seeded examples it replaces are its own files, with nothing to opt out of.
- Seeded files are written by `copier copy` only: an update never changes one, and never brings back one the app
  deleted (Copier's `_copier_operation` in `_exclude`; needs Copier 9.19). An app no longer opts out of the seeded
  examples it deleted.
- Template: CLAUDE.md says what its `@.claude/project-rules.md` line does; docs/scaffold.md says "options", not
  "feature flags".

**Steps:** an app that opted out of seeded files it deleted (its `src/` examples, `tests/test_*.py`, …) can drop
them from `opt_out` (`copier update -d 'opt_out=[…]'`) and from docs/deviations.md.

## v0.3.0

- **Options vs capabilities** (docs/template.md). A question is an answer (a name or value), an option (where apps
  truly differ) or nothing: a capability every app has.
  - Settings are in `config.toml` only. The `config_style` question and `.env` support are gone; environment
    variables still override the file.
  - `tailnet` and `privacy_hook` are no longer questions: every app has `app --tailnet`, `privacy-check` and the
    pre-commit hook.
  - `github_owner` is gone (nothing used it).
  - The options are `motherduck`, `cloud_run`, `backup` and `demo_data`.
- duckkit: `AppSpec.config_style`, `AppSpec.env_file`, `AppSpec.dotenv()` and `add_standard_commands(privacy=…)` are
  removed. `doctor` expects `.githooks/pre-commit` and `config.example.toml` in every app.
- Template: CLAUDE.md asks for a branch and a PR for every change (never `main`), stacked PRs for a change in
  parts, a phone notification after a long task, test data in files, and a talk before a new language or library.
- `/scaffold-update` and docs/upgrading.md: a seeded file an app deleted comes back on update unless opted out.
- Docs: docs/architecture.md (how an app made from the scaffold works), docs/kit.md module by module,
  docs/template.md (every answer and option, and what it decides), a longer README.
- `scripts/release.py` works through a PR: it commits the release on a branch; `--tag` tags it on main after the
  merge.

**Steps:**
- An app with a `.env`: move each setting to `config.toml` under its `[section] key`, then delete `.env`:
  `MOTHERDUCK_TOKEN` → `[motherduck] token`, `<PREFIX>_BACKUP_DIR` → `[backup] dir`, `<PREFIX>_PRIVACY_TERMS` →
  `[privacy] terms`, and the app's own `private_settings`. The update brings `config.example.toml`.
- `spec.py`: remove `config_style=…`. `cli.py`: remove `privacy=…` from `add_standard_commands`.
- An app that had `privacy_hook: false`: run `git config core.hooksPath .githooks`.

## v0.2.0

- duckkit: `status` reports the backups (how many, how old the newest is) in apps with backups.
- Template: CLAUDE.md's data rule mentions it, and wraps cleanly.

**Steps:** none.

## v0.1.0

The first release, drawn from several existing apps of this kind.

- duckkit: `AppSpec`, `Contract` (rules, `enum_rule`, `relation_rule`, custom checks), `snapshot`
  (`contract_snapshot`, `contract_copy`, `database_snapshot`, MotherDuck sign-in), `store` (schema version and
  migrations), `publish` (`plan`, `publish`, `compare`), `backup`, `privacy`, `serve` (localhost, `--tailnet`, several
  apps, `--demo`), `cli.add_standard_commands`, `doctor`, `app.common` (snapshot cache, sidebar, theme watcher,
  idle pause, tables), `app.theme`, `testing` (`isolate`, `contract_db`, `guard`).
- Template: flags `motherduck`, `cloud_run`, `tailnet`, `backup`, `privacy_hook`, `demo_data`, `extra_apps`,
  `config_style`, `opt_out`; skills `app`, `app-check`, `catch-up`, `scaffold-update`, `publish`, `backup`,
  `hosting`; the weekly `scaffold-update` workflow.
