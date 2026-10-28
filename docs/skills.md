# The skills of an app

Each app made from the scaffold gets a set of Claude Code skills in `.claude/skills/`. A skill turns the app's
commands into a task that Claude does in the chat. The user starts one by name (`/ingest`), or Claude starts it when
the request matches its description. The words after the name are the skill's arguments, in plain English or in the
form that its `argument-hint` shows. Claude reads them: they are not parsed like a command line.

This page lists the skills that the template writes. docs/template.md describes the options, and
docs/architecture.md how the skills fit in an app.

## Every app

| Skill | Kind | What it does |
|---|---|---|
| `/ingest` | seeded | bring in new data with `ingest`, report what was added, and check the contract |
| `/ask` | seeded | answer a question with read-only SQL on the contract views (`sql`) |
| `/app` | managed | start, stop or restart a Streamlit app, on localhost or on the tailnet |
| `/app-check` | managed | walk the browser checks of docs/browser-checks.md in light mode, dark mode or both, with screenshots of failures |
| `/catch-up` | managed | brief the start of a session: a remote session (the Mac kept awake, Remote Control) on request, git and the merged branches, PRs and their stacks, issues, the tests after a pull, the database status, the published copy, the hosted app, each app's health, and a newer scaffold release (`doctor --remote`) |
| `/deliver-outcome` | managed | work on an outcome issue, from the brief to the report, as docs/how-we-work.md describes |
| `/scaffold-update` | managed | move the repo to a newer scaffold release, or turn an option on, and open a PR |

## With an option

| Skill | Option | Kind | What it does |
|---|---|---|---|
| `/publish` | `motherduck` | managed, the user starts it | show what will leave this machine, ask, then send the contract views to MotherDuck |
| `/backup` | `backup` | managed | make, list, verify or restore the Parquet backups |
| `/hosting` | `cloud_run` | managed | deploy to Cloud Run or roll back, add or remove a person, list who has access, show the status. It asks before each deploy and each change of access. |
| `/demo-data` | `demo_data` | seeded | build the demo database with `demo` |
| `/fix-curation` | `curations` | seeded | correct one curated decision with the app's commands, which write `curated/` too |
| `/rebuild-database` | `curations` | managed, the user starts it | rebuild the database from its sources, restore the curated decisions from `curated/`, then compare with a baseline taken before |
| `/classify` | `llm` | seeded | let Claude make the decisions that have none yet: it states the estimate and runs a small run at once; a run with over 500 days waiting, only after the user's yes |

## Kinds

- **Managed** and **seeded** are two of the kinds of file in docs/template.md ("Three kinds of file"). A seeded
  skill is an example: the app fills in its domain, such as its sources, its questions or its decisions.
- A seeded skill of an option arrives only in a new app. An app that turns the option on later copies it from a
  fresh render, as `/scaffold-update` does.
- **The user starts it:** the skill sets `disable-model-invocation`, so Claude never starts it on its own. These
  skills send data out or rebuild the database.

An app adds its own skills beside these, and can opt out of a managed one (docs/template.md, "Deviations").

The template also writes one agent, `.claude/agents/reviewer.md`: the independent reviewer of each PR
(docs/how-we-work.md, docs/review.md).
