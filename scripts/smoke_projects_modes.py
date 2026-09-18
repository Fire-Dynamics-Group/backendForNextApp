#!/usr/bin/env python3
"""CLI entry for the Upload Canvas /projects?mode= post-deploy smoke.

Helpers live in ops/projects_smoke.py (unit-tested). This wrapper makes
`python scripts/smoke_projects_modes.py` work from any cwd.

See `python scripts/smoke_projects_modes.py --help` and
docs/projects-mode-smoke.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.projects_smoke import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
