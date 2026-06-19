#!/usr/bin/env python3
"""Entry point for Phase 2 deduplication — runnable without installation.

Reads the Phase 1 catalog and records keep/drop/review decisions plus a report
under data/. No files are deleted.

Examples
--------
    python3 scripts/run_dedup.py                      # uses data/catalog.sqlite
    python3 scripts/run_dedup.py --db /path/catalog.sqlite --report-dir data
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipelines.phase2_dedup.dedup import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
