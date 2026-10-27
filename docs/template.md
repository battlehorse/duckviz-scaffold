# The template

`template/` is a [Copier](https://copier.readthedocs.io) template. Its files are Jinja templates, rendered with the
answers to the questions in `copier.yml`. Copier records the answers and the scaffold release in the app's
`.copier-answers.yml`, and `copier update` reuses them.

- [Options or capabilities](#options-or-capabilities): the rule for what may be a question
- [Answers](#answers-the-apps-names-and-values): the app's names and values
- [Options](#options-where-apps-truly-differ): where apps truly differ
- [Capabilities](#capabilities-what-every-app-has): what every app has, with no question
- [Deviations](#deviations): where one app differs on purpose
- [Three kinds of file](#three-kinds-of-file), and how an update merges
- [Writing template files](#writing-template-files), and [adding a question](#adding-a-question)

## Options or capabilities

Every question is a cost. It is one more combination to render and test, one more branch in the docs and skills,
and one more way for apps to drift apart. So the scaffold keeps three kinds of question apart, and asks as few as
it can.

| Kind | What it is | Examples |
|---|---|---|
| **Answer** | a name or value that each app must have, and that differs between apps by nature | `project_name`, `app_port`, `contract_name` |
| **Option** | a yes/no choice where each side is right for some app | `motherduck`, `cloud_run`, `backup`, `demo_data`, `curations` |
| **Capability** | something every app has. There is no question. | the contract guard, `privacy-check`, `app --tailnet`, settings in `config.toml` |

**Something is an option only when both of these hold:**
1. **Some apps should not have it,** because it brings a cost or a risk that an app may rightly refuse. Examples:
   data leaving the machine (`motherduck`), a cloud account and a bill (`cloud_run`), or code that only some apps
   have to write (`demo_data`), or a repo that must stay private (`curations`).
2. **Turning it off removes something real:** files, commands or setup. If "off" would only hide a line in the
   docs, it isn't an option.

**Otherwise it is a capability,** and every app gets it. A capability can still be unused: `app --tailnet` does
nothing until you pass it.

When a pull request adds a question, it says which kind it is and why (see [Adding a question](#adding-a-question)).

## Answers: the app's names and values

Each app needs these values. Most have a default worked out from an earlier answer. Changing one later is a
rename: see the last column.

| Answer | Default | What it determines | Changing it later |
|---|---|---|---|
| `project_name` | none | The repo and the command (`uv run <project_name> …`). It also names the Cloud Run service and the defaults below. Lowercase letters, digits and dashes. | A rename everywhere: the command, docs, skills, CI. |
| `package` | `project_name` with `_` for `-` | The Python package, `src/<package>/`. The browser guard and the imports use it. | Move `src/<package>/` and fix every import. |
| `description` | none | One line about what the app records and shows. It appears in the README, CLAUDE.md, `pyproject.toml`, the CLI's help and the skills' descriptions. | Edit freely. Managed files take the new text on the next update. |
| `title` | `project_name` | The browser app's title: the page title, the `AppEntry`, the paused page, the app skill and the browser checks. | Edit freely. |
| `author_name`, `author_email` | the scaffold owner's | The authors in `pyproject.toml`. | Edit freely. |
| `env_prefix` | `PACKAGE` in capitals | The start of every environment variable duckkit reads: `<PREFIX>_DB`, `_APP_DB`, `_CONFIG`, `_VERSION`, `_BACKUP_DIR`, `_IDLE_MINUTES`, `_PRIVACY_TERMS`. It goes in `spec.py`, the Dockerfile and the hosting docs. | Every place that sets those variables must change: your shell, Cloud Run, CI. |
| `contract_name` | none | The contract's name in `v_contract`. A reader refuses a database whose contract has another name. It is also the default MotherDuck database. | A major contract change: every database must offer the new name. |
| `db_file` | `<project_name>.duckdb` | The database file in `data/`. `<PREFIX>_DB` overrides it. | Move the file, or keep the old name. An existing app sets its current file name here. |
| `timezone` | `Europe/London` | The `TimeZone` of every connection duckkit opens (store, snapshots, backups). This decides what a "local day" is in the views. | The views' days and hours move. Check the contract's rules and tests. |
| `app_port` | 8501 | The browser app's port on localhost. On the tailnet it is the HTTPS port too. Pick one that no other app on the machine uses. | Edit freely. Bookmarks change. |
| `extra_apps` | `[]` | More Streamlit apps besides `app`, as a YAML list of `{name, port, title, hosted}`. Each one gets an `AppEntry`, a row in the app skill, `docs/cli.md` and CLAUDE.md. A `hosted: false` app (a curation tool, say) may read the whole database and never goes to Cloud Run, and the browser app may never import it. You write its code in `src/<package>/<name>/`. | Add or remove entries, then write or delete the code. |

These come with an option, and are asked only when it is on:

| Answer | Asked when | Default | What it determines |
|---|---|---|---|
| `motherduck_db` | `motherduck` | `contract_name` | Where `publish` writes (`md:<name>`) and where a hosted app reads. |
| `gcp_project` | `cloud_run` | `project_name` | The Google Cloud project that hosts the app. |
| `gcp_region` | `cloud_run` | `europe-west2` | Its Cloud Run region. |

## Options: where apps truly differ

Each option adds files, commands and skills (docs/skills.md). An update never writes seeded files, so an app that
turns `demo_data` or `curations` on later copies their seeded files from a fresh render (`/scaffold-update` does
this). To turn one on later, ask Claude in plain words, such
as `/scaffold-update turn on cloud_run`. The skill reads its arguments as text, and runs `copier update` with
`-d cloud_run=true`. Without Claude, run `uvx copier update --trust -d <option>=true`. Then review the diff like any
update, and follow the docs it adds.

### `motherduck`: publish the contract to MotherDuck (default: on)

**What it decides:** whether this app's data may leave the machine at all.

**On:**
- `publish [--to] [--dry-run] [--check]` and `/publish`. They copy only the contract's views to `md:<motherduck_db>`.
- `[motherduck] token` in `config.example.toml`.
- The MotherDuck sections of the docs, and the publish steps in `/catch-up` and `/ingest`.
- `SPEC.motherduck_target`.
- `docs/claude-chat.md` (template-managed): the instructions for a claude.ai project that asks the published copy
  through the MotherDuck connector. It follows the app's `/ask` skill, where the app's domain hints belong. The
  one-time setup of that project is in `/publish`.

A hosted app, Claude, or any DuckDB client can then read the views from anywhere. Nothing is ever sent unless
someone runs `publish`.

**Off:** there is no `publish` command, and no data ever leaves the machine. Choose off for data that must stay
local.

**Needed by:** `cloud_run`, because a hosted app reads the published copy.

### `cloud_run`: host the browser app on Cloud Run (default: off)

**What it decides:** whether the app is reachable from anywhere, behind Google sign-in, at the cost of a Google
Cloud project. **Needs** `motherduck`.

**On:**
- a `Dockerfile` and its ignore files. The image holds the code only, never `data/` or the settings.
- `docs/hosting.md`: how the hosted app works (IAP sign-in, Cloud Run, the token secret, the idle pause), the
  costs, the one-time setup step by step, updating, rolling back and sharing.
- `/hosting`: deploy, roll back, add or remove a person, status.
- `app/static/paused.html`, the page an idle tab goes to so the instance can scale to zero.
- the deployed version in `/catch-up`.

The hosted app sets `<PREFIX>_APP_DB=md:<motherduck_db>` and reads the published copy. Its code is the same as the
local app's.

**Off:** the app runs on this machine and, with `--tailnet`, on your own devices.

### `backup`: verified Parquet backups (default: on)

**What it decides:** whether this app keeps snapshots of its database. Choose it when the database holds data
that can't be fetched again, or takes long to rebuild.

**On:**
- `backup`, `backups`, `restore` and `/backup`;
- the backups line in `status`;
- `[backup] dir` and `keep` in `config.example.toml`;
- `backups/` in `.gitignore` and `.dockerignore`;
- the backup rule in CLAUDE.md.

**Off:** there are no backup commands. Use off for an app whose database can always be rebuilt from its sources.
Even then, a backup before a risky migration is cheap, so on is the default.

### `demo_data`: a synthetic demo database (default: off)

**What it decides:** whether the app has made-up data for screenshots, demos and browser checks without real data.

**On:** `SPEC.demo_file = "demo.duckdb"`, `app --demo` (which reads `data/demo.duckdb`), the demo steps in `/app`
and `/app-check`, and a guard that stops `publish` from sending the demo database. Seeded (the app's own once
written): a `demo` command in `cli.py` that calls `duckkit.demo.build_demo`, an example generator in
`src/<package>/demo.py`, its test (`tests/test_demo.py`) and a `/demo-data` skill. The app replaces the example
generator with its own; `build_demo` keeps the safety (the marker, never over another file, never half-built).

**Off:** there is no `demo` command and no `--demo`.

### `curations`: decisions kept in git (default: off)

**What it decides:** whether the app holds decisions that the sources can't give back: a category chosen by hand,
a model's classification. They cost time or money to make, so they go into `curated/*.csv`, committed to git, and
come back into a rebuilt database. Choose it when the database is otherwise rebuilt from its sources. **The repo
must then stay private**: the files are the user's decisions.

**On:**
- `duckkit.curated` in use: `src/<package>/curated.py` lists the curated tables and wraps `curating()`. Every
  command that changes a decision runs in it, so the files are exported after it. `ingest` calls `restore`, which
  loads the files into a rebuilt database;
- the git guard: the pre-commit hook runs `curated-check`, which stops a commit that empties a curated file or
  loses many of its rows, until the user confirms;
- `doctor --remote` fails if git holds `curated/` and the GitHub repo is public;
- the curated-decisions rule in CLAUDE.md, `curated/.*.tmp` in `.gitignore`, `curated/` named in the ignore files'
  comments;
- `/rebuild-database` (managed);
- seeded (the app's own once written): `curated.py`, an example curated table (`labels`, a day's label) with
  `label` and `unlabel` commands and a status line, their test (`tests/test_curated.py`), `curated/README.md`
  (the columns of each file) and a `/fix-curation` skill. The app replaces the example with its own decisions.

**Off:** no curated tables: the sources alone rebuild the database.

## Capabilities: what every app has

There is no question for these. An app that truly can't have one lists it in `opt_out` and explains why (see
[Deviations](#deviations)).

| Capability | What it is |
|---|---|
| The data contract and its guard | `contract/`, `v_contract`, `status`'s contract check, `tests/app/test_contract_only.py` |
| The standard commands | `status`, `sql`, `app [name]`, `doctor`, `spec-diff` |
| Settings in `config.toml` | One file, gitignored, with a `config.example.toml` beside it. Environment variables override it (for CI, tests and Cloud Run). |
| Keeping personal data out of git | `privacy-check`, the `.githooks/pre-commit` hook that runs it, `[privacy] terms`, and `spec.private_settings` |
| Serving on the tailnet | `app --tailnet`: `tailscale serve` to your own devices, for as long as the app runs |
| CI | lint, tests and `doctor` on every PR, and the `spec` job that labels a PR that touches the spec (an extension or a revision) (`.github/workflows/tests.yml`) |
| Scaffold updates | the weekly `scaffold-update` workflow and `/scaffold-update` |
| Claude Code | CLAUDE.md with the shared rules, and the skills of every app (docs/skills.md) |
| Docs | architecture, contract, dashboard, cli, getting-started, browser checks, scaffold, deviations |
| How we work | docs/how-we-work.md (the cycle: outcomes, the spec, merges, the report), docs/spec.md and `.claude/spec-paths` (the app's spec, seeded), docs/review.md (the standards), the `reviewer` agent, the `/deliver-outcome` skill, the PR template, and `.claude/settings.json` (Claude Code prompts before a hard stop) |

## Deviations

An app differs from the scaffold in one of three ways, and lists each one in its `docs/deviations.md`:

1. **An option off**, such as an app that isn't hosted (`cloud_run: false`).
2. **An opted-out file**, such as `opt_out: [.claude/skills/catch-up/SKILL.md]`. The paths in `opt_out` are never
   rendered: they are Copier's `_exclude`. `doctor` fails when `docs/deviations.md` doesn't name a path. Opt out only
   of template-managed files: a seeded file is the app's own, so the app can delete it, and no update brings it
   back.
3. **A local edit to a template-managed file**, such as an app skill that knows the app's two apps. The merge keeps
   it. When the scaffold changes the same lines, `docs/deviations.md` tells `/scaffold-update` which side wins.

A deviation that several apps share is a sign that the scaffold should offer it, as a hook or, if the
[rule](#options-or-capabilities) allows, as an option.

Hidden answers are never asked:
- `kit_ref`: the release, which `scripts/release.py` sets;
- `scaffold_repo`: the scaffold's URL, for links;
- `kit_path`: a local kit, used only by the scaffold's own CI.

## Three kinds of file

| Kind | Examples | On `copier update` |
|---|---|---|
| **Template-managed** | CLAUDE.md, pyproject.toml, CI, the PR template, Dockerfile, .streamlit/, .githooks/, generic skills, docs/scaffold.md, docs/cli.md, docs/hosting.md, docs/how-we-work.md, docs/review.md, .claude/settings.json, .claude/agents/, tests/app/test_contract_only.py | The template's change is merged in, and the app's edits stay. |
| **Seeded once** (`_skip_if_exists`, and excluded from updates) | src/<package>/, contract/schema.sql, README.md, config.example.toml, docs/architecture, contract, dashboard, getting-started, deviations, spec, .claude/project-rules.md, .claude/spec-paths, the ingest, ask, demo-data and fix-curation skills, the tests other than the guard | Never touched again. |
| **Shared code** | duckkit | Not in the app at all. It is a version in pyproject.toml. |

**How the merge works:** Copier renders the template twice with the same answers, once at the app's recorded
release and once at the new one. It diffs the two renders and applies that diff to the app, as a 3-way merge.
Lines the app changed and the template didn't stay as they are. Lines both changed become a conflict, and
`--conflict inline` writes the markers into the file.

CLAUDE.md is template-managed and imports `.claude/project-rules.md`, which belongs to the app. So the app's
domain rules never conflict with the scaffold's.

## Writing template files

- `.jinja` files are rendered; other files are copied as they are. A file or folder named
  `{% if option %}name{% endif %}` exists only when the option is on.
- Seeded files can use any answer. Template-managed files should change rarely and in small hunks, so that merges
  stay clean.
- Anything that is code, and the same for every app, belongs in duckkit instead.
- `scripts/render.sh` renders three sample apps (every option on, every option off, and curations), and runs their
  lint, tests and `doctor`. Run it after every template change. CI runs it on every PR.

## Adding a question

Before adding a question to `copier.yml`, or a switch to duckkit:

1. **Name its kind:** answer, option or capability. If it's a capability, add it for every app with no question.
2. **For an option,** say which apps should not have it and why: the cost or risk they avoid. Say what turning it
   off removes. New options default to off, so updating apps don't gain something by surprise.
3. **For a second way of doing something,** pick one instead, and list the migration under **Steps** in the
   CHANGELOG.
4. Add it to this page: to the answers table, or as an option section with what it decides and what on and off
   mean.
5. Make `scripts/render.sh` cover it, and add its files to `doctor`'s `EXPECTED` with the option that brings them.
