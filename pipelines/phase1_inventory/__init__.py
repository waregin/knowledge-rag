"""Phase 1 — Filesystem inventory.

Walk the configured roots and record every file (a complete census) into the
shared SQLite catalog, capturing the fields dedup (Phase 2) and reconciliation
(Phase 3) need: path, format, size, content hash, and a corpus hint.
"""

from .inventory import run_inventory, main  # noqa: F401
