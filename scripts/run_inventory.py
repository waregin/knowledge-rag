#!/usr/bin/env python3
"""Entry point for Phase 1 inventory — runnable without installation.

Bootstraps the repo root onto sys.path so ``pipelines`` imports resolve, then
delegates to the phase1 CLI. Works on any Python 3.8+ with no third-party deps.

Examples
--------
    # Scan one or more folders, write catalog + CSV under data/
    python3 scripts/run_inventory.py --root /mnt/books --root /mnt/kindle

    # Use a config file (recommended once roots stabilize)
    python3 scripts/run_inventory.py --config config/pipeline.json

    # Fast census without hashing, then hash later incrementally
    python3 scripts/run_inventory.py --config config/pipeline.json --no-hash
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipelines.phase1_inventory.inventory import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
