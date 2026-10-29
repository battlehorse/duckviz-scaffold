"""The commands every app's CLI has. The app's own `cli.py` makes the Typer app, adds its domain commands
(`ingest`, …) and calls `add_standard_commands`:

    app = typer.Typer(help="…")
    add_standard_commands(app, SPEC, connect=connect, status=status_lines)

| Command | What it does |
|---|---|
| `status` | the app's own summary lines (`status` hook), then the contract check |
| `sql "<SELECT>"` | one read-only SELECT on a snapshot of the database |
| `publish [--to] [--dry-run] [--check]` | the contract views to MotherDuck (or a file); never automatic |
| `backup`, `backups`, `restore <snapshot>` | verified Parquet snapshots (needs `connect`) |
| `app [name] [--tailnet] [--demo]` | serve a Streamlit app on localhost, optionally on the tailnet |
| `privacy-check` | fail if a committable file holds personal data (the pre-commit hook) |
| `doctor` | how this repo compares with the scaffold it was made from |
| `spec-diff [--base]` | the parts of the spec a change touches (`.claude/spec-paths`); exits 1 if any |
| `curated-check [--base]` | what a commit (or a branch) does to curated/*.csv; fails when a file loses many rows (`curations=True`) |
"""

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import duckdb
import typer

from duckkit.spec import AppSpec

if TYPE_CHECKING:
    from duckkit.hosting import Deployed


def fail(message: str) -> None:
    """Print `message` to stderr and exit with status 1."""
    typer.echo(f"✗ {message}", err=True)
    raise typer.Exit(1)


def contract_line(spec: AppSpec, problems: list[str], pad: str = "") -> None:
    """Print the contract check: one line, then one per problem. Views older than the code (a missing view or
    column, an older version) get a hint: any write connection recreates them from db/schema.sql."""
    contract = spec.contract
    stale = any(p.endswith("missing") or "expected" in p for p in problems)
    typer.echo(f"Contract:{pad} {contract.name} {contract.version}, "
               + (f"{len(problems)} problems for the app" if problems else "the app's views conform")
               + (f" → `{spec.cli} ingest` recreates the views" if stale else ""))
    for problem in problems:
        typer.echo(f"  ✗ {problem}")


def remote_lines(spec: AppSpec, publishing: bool) -> list[str]:
    """The lines of `status --remote`: whether the published copy and the hosted app are current. A check that can't
    run says why, in its line."""
    from duckkit.demo import is_demo
    from duckkit.hosting import HostingError, deployed
    from duckkit.publish import compare
    from duckkit.snapshot import ContractError

    lines = []
    if publishing:
        try:
            stale = [view for view, (_, _, same) in compare(spec).items() if not same]
            differ = "1 view differs" if len(stale) == 1 else f"{len(stale)} views differ"
            hint = "(this is the demo database)" if is_demo(spec) else f"`{spec.cli} publish` sends them"
            if stale:
                lines.append(f"Published:    {differ} from the database ({', '.join(stale)}): {hint}")
            else:
                lines.append(f"Published:    {spec.motherduck_target} is up to date")
        except (FileNotFoundError, ContractError, ValueError, duckdb.Error) as e:
            lines.append(f"Published:    can't tell: {str(e).splitlines()[0]}")
    try:
        hosted = deployed(spec)
    except HostingError as e:
        lines.append(f"Deployed:     can't tell: {e}")
    else:
        if hosted is not None:
            lines.append(f"Deployed:     {hosted.commit}, {deployed_state(hosted)}")
    return lines


def deployed_state(hosted: Deployed) -> str:
    """Where the hosted app's commit stands against origin/main, in words."""
    if not hosted.known:
        return "a commit this clone lacks: `git fetch`, then ask again"
    if not hosted.on_main:
        return "not on origin/main (a branch, or a commit not pushed, was deployed)"
    if hosted.behind == 0:
        return "the same as origin/main"
    commits = "1 commit" if hosted.behind == 1 else f"{hosted.behind} commits"
    return f"{commits} behind origin/main: `/hosting deploy`"


def stale_demo_line(spec: AppSpec) -> str | None:
    """A warning when the demo database no longer fits the contract: built by an older version of the app, it
    would show only an error in `app --demo`. None when it fits, when there is none, or when it is the database
    `status` just checked (<PREFIX>_DB)."""
    path = spec.demo_db_path
    if path is None or not path.exists() or path.resolve() == spec.db_path.resolve():
        return None
    from duckkit.snapshot import attach

    try:  # read in place, attached read-only: no copy of the whole file
        with attach(spec, path) as con:
            con.execute("USE src")
            problems = spec.contract.check(con)
    except duckdb.Error as e:
        first = str(e).splitlines()[0] if str(e) else type(e).__name__
        return f"Demo file:    can't read {path.name}: {first}"
    if not problems:
        return None
    contract, n = spec.contract, len(problems)
    return (f"Demo file:    {path.name} doesn't fit contract {contract.name} {contract.version} "
            f"({n} {'problem' if n == 1 else 'problems'}) → rebuild it with `{spec.cli} demo`, with the options it "
            "was built with")


def backups_line(spec: AppSpec) -> str:
    """How many backup snapshots there are, and how old the newest is."""
    from datetime import UTC, datetime

    from duckkit.backup import snapshots

    found = snapshots(spec)
    if not found:
        return "Backups:      none yet (`backup`)"
    stamp = datetime.strptime(found[-1].name.removeprefix(spec.backup_prefix), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    hours = (datetime.now(UTC) - stamp).total_seconds() / 3600
    age = f"{hours:.0f} hours" if hours < 48 else f"{hours / 24:.0f} days"
    return f"Backups:      {len(found)}, the newest {age} old ({spec.backup_dir()})"


def print_spec_diff(root: Path, base: str) -> None:
    """Print `spec-diff` for the repo at `root`. Exit 1 when the spec changed, and 2 when it can't tell (CI must not
    take an error for a change)."""
    from duckkit.specdiff import spec_diff

    try:
        diff = spec_diff(root, base)
    except ValueError as e:
        typer.echo(f"✗ {e}", err=True)
        raise typer.Exit(2) from e
    for line in diff.lines():
        typer.echo(line)
    if diff.changed:
        raise typer.Exit(1)


def add_standard_commands(
    app: typer.Typer,
    spec: AppSpec,
    *,
    connect: Callable[[], duckdb.DuckDBPyConnection] | None = None,
    status: Callable[[duckdb.DuckDBPyConnection], list[str]] | None = None,
    privacy_terms: Callable[[AppSpec], dict[str, str]] | None = None,
    backups: bool = True,
    publishing: bool = True,
    curations: bool = False,
) -> None:
    """Add the standard commands to `app`.

    - `connect`: opens the database for writing (the app's db/store.py), for `backup`.
    - `status`: the app's own summary lines for `status`, from a snapshot of the whole database.
    - `privacy_terms`: the app's own personal terms for `privacy-check` (names in its database, say).
    - `backups`, `publishing`: False leaves those commands out (the scaffold's `backup` and `motherduck` options).
    - `curations`: True adds `curated-check` (the scaffold's `curations` option).
    """

    @app.command("status")
    def status_command(
        remote: bool = typer.Option(False, "--remote", help="Also say whether the published copy and the hosted app "
                                    "are current (reads MotherDuck and Cloud Run; changes nothing)."),
    ) -> None:
        """What the database holds (the app's summary), and the contract check."""
        from duckkit.snapshot import database_snapshot

        try:
            con = database_snapshot(spec)
        except FileNotFoundError as e:
            typer.echo(str(e))
            if demo_line := stale_demo_line(spec):  # a fresh clone may have only the demo
                typer.echo(demo_line)
            if remote:  # the hosted app can be checked without a local database
                for line in remote_lines(spec, publishing=False):
                    typer.echo(line)
            return
        from duckkit.demo import has_marker

        lines = status(con) if status else [f"Database:     {spec.db_path}"]
        if has_marker(con):
            lines.append(f"Demo:         made-up data (`{spec.cli} demo`), not your own")
        for line in lines:
            typer.echo(line)
        if backups and connect:
            typer.echo(backups_line(spec))
        contract_line(spec, spec.contract.check(con), pad="    ")
        if demo_line := stale_demo_line(spec):
            typer.echo(demo_line)
        if remote:
            for line in remote_lines(spec, publishing):
                typer.echo(line)

    @app.command("sql")
    def sql_command(query: str, limit: int = typer.Option(200, help="Maximum rows to print.")) -> None:
        """Run one read-only SELECT on a snapshot of the database. Prefer the contract views (docs/contract.md)."""
        import pandas as pd

        from duckkit.snapshot import database_snapshot

        try:
            con = database_snapshot(spec)
            statements = con.extract_statements(query)
        except (FileNotFoundError, duckdb.Error) as e:
            fail(str(e))
        if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
            fail("only a single SELECT (or WITH … SELECT) query is allowed")
        try:
            df = con.execute(query).df()
        except duckdb.Error as e:
            fail(str(e))
        with pd.option_context("display.max_columns", None, "display.width", 200, "display.max_colwidth", 80):
            typer.echo(df.head(limit).to_string(index=False) if len(df) else "(no rows)")
        if len(df) > limit:
            typer.echo(f"… {len(df) - limit} more rows (use --limit)")

    if publishing:
        @app.command("publish")
        def publish_command(
            to: Annotated[str | None, typer.Option(
                help=f"MotherDuck database (md:<name>) or a DuckDB file to write. Default: {spec.motherduck_target}."
            )] = None,
            dry_run: bool = typer.Option(False, "--dry-run", help="Only show what would be sent."),
            check: bool = typer.Option(False, "--check", help="Only compare the published copy with the database."),
        ) -> None:
            """Publish the contract views to MotherDuck. Never automatic: only this command (or /publish) does."""
            from duckkit.demo import is_demo
            from duckkit.publish import compare, plan
            from duckkit.publish import publish as publish_contract
            from duckkit.snapshot import ContractError

            if is_demo(spec):
                fail(f"{spec.db_path} is a demo database: publish sends your own database only")
            target = to or spec.motherduck_target
            try:
                if dry_run:
                    for view, (rows, columns) in plan(spec).items():
                        typer.echo(f"  {view}: {rows:,} rows, {len(columns)} columns")
                    typer.echo(f"Nothing sent. `{spec.cli} publish` sends these to {target}.")
                    return
                result = compare(spec, to) if check else publish_contract(spec, to)
            except (FileNotFoundError, ContractError, ValueError, duckdb.Error) as e:
                fail(str(e))
            if not check:
                typer.echo(f"Published to {target}: " + ", ".join(f"{view} {n:,} rows" for view, n in result.items()))
                return
            stale = {view: r for view, r in result.items() if not r[2]}
            if not stale:
                typer.echo(f"✓ {target} is up to date: "
                           + ", ".join(f"{view} {n:,} rows" for view, (n, _, _) in result.items()))
                return
            typer.echo(f"✗ {target} differs from this database (run `{spec.cli} publish` or /publish):")
            for view, (here, there, _) in stale.items():
                typer.echo(f"  {view}: " + ("missing there" if there is None else
                                            f"{here:,} rows here, {there:,} published" if here != there else
                                            f"{here:,} rows on both sides, with different contents"))
            raise typer.Exit(1)

    if backups and connect:
        @app.command("backup")
        def backup_command() -> None:
            """Export the database to a new verified Parquet snapshot in the backup folder; keep the newest ones."""
            from duckkit.backup import backup

            if not spec.db_path.exists():
                fail(f"no database at {spec.db_path}")
            with connect() as con:
                typer.echo(f"Backed up to {backup(spec, con)} (verified)")

        @app.command("backups")
        def backups_command() -> None:
            """List the backup snapshots, oldest first."""
            from duckkit.backup import snapshots

            found = snapshots(spec)
            for path in found:
                size = sum(f.stat().st_size for f in path.iterdir())
                typer.echo(f"{path}  {size / 1024:,.0f} KB")
            typer.echo(f"{len(found)} snapshots in {spec.backup_dir()}")

        @app.command("restore")
        def restore_command(
            snapshot: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="A snapshot folder.")],
            to: Annotated[Path | None, typer.Option(help="The database file to create (never overwritten).")] = None,
        ) -> None:
            """Rebuild a database from a backup snapshot, into a new file (default: data/restored.duckdb)."""
            from duckkit.backup import restore

            target = to or spec.data_dir / "restored.duckdb"
            try:
                counts = restore(spec, snapshot, target)
            except FileExistsError as e:
                fail(str(e))
            typer.echo(f"Restored {target}: " + ", ".join(f"{t} {n:,}" for t, (n, _) in counts.items()))
            typer.echo(f"To use it: move {spec.db_path} away, then move {target} to {spec.db_path}")

    names = ", ".join(f"{a.name} (:{a.port})" for a in spec.apps)

    @app.command("app")
    def app_command(
        name: Annotated[str | None, typer.Argument(help=f"Which app: {names}. Default: {spec.apps[0].name}.")] = None,
        tailnet: bool = typer.Option(False, "--tailnet",
                                     help="Also serve it to your Tailscale devices (`tailscale serve`), while it runs."),
        demo: bool = typer.Option(False, "--demo", help="Read the demo database instead of the real one."),
    ) -> None:
        """Serve an app on localhost until Ctrl+C.

        With --tailnet, `tailscale serve` also forwards https://<this machine's tailnet name>:<port> to it, in the
        foreground: the forwarding ends when the app does, and the app itself still listens on localhost only.
        """
        from duckkit.serve import ServeError, run_app

        try:
            code = run_app(spec, name, tailnet=tailnet, demo=demo, echo=typer.echo)
        except (ServeError, KeyError) as e:
            fail(str(e).strip("'\""))
        raise typer.Exit(code)

    @app.command("privacy-check")
    def privacy_command() -> None:
        """Fail if any file git would commit contains personal data (the pre-commit hook runs this)."""
        from duckkit.privacy import check

        findings = check(spec, privacy_terms)
        for f in findings:
            typer.echo(f"  ✗ {f.path}:{f.line}: {f.what}", err=True)  # never print the value itself
        if findings:
            fail(f"{len(findings)} lines with personal data: remove them before committing")
        typer.echo("✓ no personal data in the files git would commit")

    if curations:
        @app.command("curated-check")
        def curated_check_command(
            base: str = typer.Option(None, help="Compare the working tree with this branch, instead of the commit."),
        ) -> None:
            """Show what the next commit (or, with --base, this branch) does to the curated decisions. Fail when a file
            is emptied or loses many rows, unless ALLOW_CURATED_LOSS=1: the pre-commit hook runs it."""
            import os

            from duckkit.curated import file_changes

            try:
                changes = file_changes(spec, base)
            except ValueError as e:
                fail(str(e))
            for change in changes:
                typer.echo(f"  {'✗' if change.loses_many else '·'} {change.line()}")
            many = ", ".join(c.name for c in changes if c.loses_many)
            if many and base:
                fail(f"{many} lose many decisions on this branch. Check `git diff {base} -- curated/`")
            if many and os.environ.get("ALLOW_CURATED_LOSS") != "1":
                fail(f"{many} would lose many decisions. Check `git diff --cached curated/`. If you meant it, commit"
                     " again with ALLOW_CURATED_LOSS=1. If not, unstage them: `git restore --staged curated/`")
            typer.echo("✓ curated decisions: " + (f"{len(changes)} files change" if changes else "no change"))

    @app.command("doctor")
    def doctor_command(
        remote: bool = typer.Option(False, "--remote", help="Also ask the scaffold's repo for its newest release."),
    ) -> None:
        """Compare this repo with the scaffold it was made from: versions, expected files, declared deviations."""
        from duckkit.doctor import diagnose

        report = diagnose(spec, remote=remote)
        for line in report.lines():
            typer.echo(line)
        if report.problems:
            raise typer.Exit(1)

    @app.command("spec-diff")
    def spec_diff_command(
        base: str = typer.Option("origin/main", help="The branch to compare with (from its merge base)."),
    ) -> None:
        """List the parts of the spec that this branch changes, committed or not. Exit 1 if it changes any."""
        print_spec_diff(spec.root, base)
