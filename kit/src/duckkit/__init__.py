"""duckkit: the code every app made from duckviz-scaffold shares.

An app describes itself once, in `<package>/spec.py`, as an `AppSpec` (its paths, ports, contract and settings).
Every function here takes that spec, so nothing in duckkit knows which app it serves.

Which side may import what (docs/design/architecture.md of each app):
- the browser app: `duckkit.spec`, `duckkit.contract`, `duckkit.snapshot`, `duckkit.app.*`
- the ingestion service and the CLI: everything
"""

from duckkit.contract import Contract
from duckkit.spec import AppEntry, AppSpec

__all__ = ["AppEntry", "AppSpec", "Contract"]
