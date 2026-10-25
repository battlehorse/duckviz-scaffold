# The template

`template/` is a [Copier](https://copier.readthedocs.io) template: Jinja files rendered with the answers to
`copier.yml`'s questions. Copier records the answers and the release in the app's `.copier-answers.yml`.

## Three kinds of file

| Kind | Examples | On `copier update` |
|---|---|---|
| **Template-managed** | CLAUDE.md, pyproject.toml, CI, Dockerfile, .streamlit/, generic skills, docs/scaffold.md, docs/cli.md, docs/hosting.md, tests/app/test_contract_only.py | the template's change is merged in; the app's edits stay |
| **Seeded once** (`_skip_if_exists`) | src/<package>/, contract/schema.sql, README.md, docs/architecture, contract, dashboard, getting-started, deviations, .claude/project-rules.md, the ingest and ask skills, tests other than the guard | never touched again |
| **Shared code** | duckkit | not in the app at all: a version in pyproject.toml |

How the merge works: Copier renders the template at the app's recorded release and at the new one, with the same
answers, diffs the two, and applies that diff to the app (a 3-way merge). Lines the app changed and the template
didn't stay as they are; lines both changed become a conflict (`--conflict inline` writes markers).

CLAUDE.md is template-managed and imports `.claude/project-rules.md`, which is the app's: domain rules never
conflict with the scaffold's.

## Questions and flags

| Answer | Default | Effect |
|---|---|---|
| `project_name`, `package`, `env_prefix`, `title`, `description` | | names everywhere |
| `contract_name`, `db_file`, `timezone`, `app_port` | | spec.py, docs, skills |
| `extra_apps` | `[]` | more Streamlit apps: spec.py, the app skill, docs. `hosted: false` apps are local-only and forbidden to the browser app |
| `config_style` | `env` | `.env.example` or `config.example.toml`; messages and docs |
| `motherduck` (+ `motherduck_db`) | on | `publish`, `/publish` |
| `cloud_run` (+ `gcp_project`, `gcp_region`) | off | Dockerfile, ignore files, `/hosting`, docs/hosting.md, the idle page |
| `tailnet` | on | `--tailnet` in docs and the app skill (the command always has it) |
| `backup` | on | `backup`, `backups`, `restore`, `/backup` |
| `privacy_hook` | on | `privacy-check`, `.githooks/pre-commit` |
| `demo_data` | off | `app --demo` and `data/demo.duckdb` |
| `opt_out` | `[]` | template files this app doesn't want (excluded from every render) |

Hidden: `kit_ref` (the release, set by scripts/release.py), `scaffold_repo`, and `kit_path` (CI only: a local
kit).

## Deviations

An app differs from the scaffold in one of three ways, and lists each in its `docs/deviations.md`:

1. **A flag off** (an app that isn't hosted: `cloud_run: false`).
2. **An opted-out file** (`opt_out: [.claude/skills/catch-up/SKILL.md]`). `doctor` fails if docs/deviations.md
   doesn't name it.
3. **A local edit to a template-managed file** (an app skill that knows the app's two apps). The merge keeps
   it; when the scaffold changes the same lines, docs/deviations.md tells `/scaffold-update` which side wins.

A deviation that several apps share is a sign the scaffold should offer it: a flag or a hook.

## Writing template files

- `.jinja` files are rendered; others are copied. A file or folder named `{% if flag %}name{% endif %}` exists only
  with the flag.
- Seeded files can use any answer; template-managed files should change rarely and in small hunks, so merges stay
  clean.
- Anything that is code, and the same for every app, belongs in duckkit instead.
