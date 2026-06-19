"""Phase 2 — Deduplication.

Record keep/drop/review decisions over the Phase 1 catalog (exact content-hash
duplicates + filename-based same-work candidates). No files are deleted.
"""

from .dedup import run_dedup, main  # noqa: F401
