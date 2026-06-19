"""Content hashing for deduplication prep (Phase 2).

We compute a full SHA-256 over file contents — the gold standard for *exact*
duplicate detection, which is what an ebook library overwhelmingly contains
(the same MOBI copied into several folders). Ebooks are small, so full hashing
of 20k+ files is cheap; large outliers (audiobooks) can be capped via
``max_bytes`` to keep a scan fast, in which case the hash is skipped and the
file is still inventoried with ``sha256 = None``.

A cheap ``size_bytes`` pre-filter is recorded alongside every hash so Phase 2
can group by size first and only compare hashes within size-collisions.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1 << 20  # 1 MiB


def sha256_file(path: Path, max_bytes: int | None = None) -> str | None:
    """Return the hex SHA-256 of ``path``.

    Returns ``None`` if ``max_bytes`` is set and the file is larger than it
    (the caller records the file without a hash). Raises ``OSError`` on read
    failure — the caller is expected to catch and record it per-file.
    """
    if max_bytes is not None:
        try:
            if path.stat().st_size > max_bytes:
                return None
        except OSError:
            raise

    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
