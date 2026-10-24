"""Serve an app with Streamlit on this machine, and optionally on the tailnet.

Streamlit always listens on localhost only, with nothing sent to Streamlit and no Deploy button. `--tailnet`
starts `tailscale serve` in the foreground, forwarding https://<this machine's tailnet name>:<tailnet port> to it:
only devices on the user's tailnet can open it, and the forwarding ends when the app does. `tailscale funnel`
(the public internet) is never used.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from duckkit.spec import TAILSCALE_APP, AppSpec


class ServeError(RuntimeError):
    """The app can't start as asked (no Tailscale, no demo database)."""


def streamlit_args(spec: AppSpec, name: str | None = None) -> list[str]:
    """The command that runs app `name` on localhost."""
    entry = spec.app(name)
    return [
        sys.executable, "-m", "streamlit", "run", str(spec.main_script(name)),
        "--server.address", "localhost",  # this machine only (`--tailnet` forwards to it)
        "--server.port", str(entry.port),
        "--server.headless", "true",  # no first-run email prompt, and Streamlit opens no browser
        "--browser.gatherUsageStats", "false",
        "--client.toolbarMode", "viewer",  # no Deploy button: this data shouldn't be hosted by Streamlit
    ]


def run_app(spec: AppSpec, name: str | None = None, tailnet: bool = False, demo: bool = False, echo=print) -> int:
    """Run app `name` until Ctrl+C; returns Streamlit's exit code. `demo` reads the demo database instead."""
    entry = spec.app(name)
    env = dict(os.environ)
    if demo:
        if not spec.demo_db_path or not spec.demo_db_path.exists():
            raise ServeError(f"no demo database at {spec.demo_db_path}: run `{spec.cli} demo` first")
        env[f"{spec.env_prefix}_DB"] = str(spec.demo_db_path)
    forward = tailnet_forward(entry.port, entry.tailnet_port, echo) if tailnet else None
    echo(f"Serving http://localhost:{entry.port} (Ctrl+C to stop)")
    try:
        return subprocess.call(streamlit_args(spec, name), env=env)
    finally:
        if forward:
            stop(forward)


def tailscale() -> str | None:
    """The tailscale CLI: on PATH, or inside the macOS app."""
    return shutil.which("tailscale") or (TAILSCALE_APP if Path(TAILSCALE_APP).exists() else None)


def tailnet_name() -> str:
    """This machine's tailnet name (e.g. mac.tail1234.ts.net). ServeError when Tailscale is missing or down."""
    cli = tailscale()
    if not cli:
        raise ServeError("--tailnet needs Tailscale: no `tailscale` command found")
    status = subprocess.run([cli, "status", "--json"], capture_output=True, text=True, check=False)
    me = json.loads(status.stdout or "{}") if status.returncode == 0 else {}
    if me.get("BackendState") != "Running":
        raise ServeError("--tailnet: Tailscale isn't connected on this machine")
    return me["Self"]["DNSName"].rstrip(".")


def tailnet_forward(port: int, tailnet_port: int, echo=print) -> subprocess.Popen:
    """Start `tailscale serve` from https://<tailnet name>:<tailnet_port> to localhost:<port>; returns its process."""
    name = tailnet_name()
    # Its own output goes through: the first time, it prints the link that turns Serve on for the tailnet
    forward = subprocess.Popen([tailscale(), "serve", f"--https={tailnet_port}", str(port)])
    echo(f"Serving on your tailnet at https://{name}:{tailnet_port}")
    return forward


def stop(process) -> None:
    """End a foreground `tailscale serve` as Ctrl+C would, so it removes its forwarding."""
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
