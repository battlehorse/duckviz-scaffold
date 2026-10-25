# duckviz-scaffold

The scaffold for apps that **ingest data with Python into DuckDB, offer it through a versioned SQL contract, and
show it in a Streamlit app that reads only the contract**, with optional MotherDuck publishing, Cloud Run hosting
and Tailscale serving.

It has two parts that release together:

| Part | What | How apps use it |
|---|---|---|
| [`kit/`](kit) | **duckkit**, the shared Python code: contract check, snapshots, publish, backups, privacy check, serving, the standard CLI commands, Streamlit helpers, test guards | a dependency pinned to the release tag |
| [`template/`](template) + [`copier.yml`](copier.yml) | a [Copier](https://copier.readthedocs.io) template: the repo layout, CI, Dockerfile, CLAUDE.md, docs and skills | `copier copy` once, `copier update` for each release |

## New app

```sh
uvx copier copy --trust gh:battlehorse/duckviz-scaffold my-app
cd my-app && git init -b main && uv sync && uv run pytest -q
```

Copier asks for the name, port, contract name and the features (MotherDuck, Cloud Run, tailnet, backups, the
privacy hook, demo data). The answers live in the app's `.copier-answers.yml`.

## Keeping apps current

```
discover (in an app) → upstream (here: /upstream) → release (scripts/release.py) → apply (in each app: /scaffold-update)
```

- docs/kit.md: how duckkit works, module by module.
- docs/template.md: how the template works, which files it manages, flags and deviations.
- docs/upgrading.md: the cycle in detail, and adopting the scaffold in an existing repo.
- CHANGELOG.md: what each release adds, with the steps an app must take.

## Development

```sh
cd kit && uv sync && uv run pytest -q && uv run ruff check .
scripts/render.sh          # render sample apps (every flag on, every flag off) and run their tests
```
