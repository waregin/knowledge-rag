"""Minimal, dependency-free config loading.

Supports JSON (any Python 3) and TOML (Python 3.11+ via ``tomllib``), chosen by
file extension. JSON is the shipped default so the pipeline runs on whatever
Python the current Zorin box has, with no third-party installs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = {
    # Directories to scan. Override with --root on the CLI.
    "roots": [],
    # Folders flagged in TickTick as previously skipped. They are NOT excluded
    # — they are inventoried like everything else (complete census for the
    # Trove OS). Listed here only so reports can call them out explicitly.
    "previously_skipped_folders": [
        "15000KindleBooks",
        "AudioBooks",
        "ComicBookPDFs",
    ],
    # Directory/file name fragments to skip outright (junk, not library data).
    "exclude_globs": [
        ".git", ".Trash-*", "@eaDir", "lost+found", "__MACOSX",
        ".DS_Store", "Thumbs.db", "*.tmp", "*.part",
    ],
    # Skip hashing files larger than this (bytes); they are still inventoried
    # with sha256=None. 0 or null = always hash. Default 0 (hash everything).
    "max_hash_bytes": 0,
    # Follow symlinks while walking (off by default to avoid loops/dupes).
    "follow_symlinks": False,
    "db_path": "data/catalog.sqlite",
    "csv_path": "data/inventory.csv",
}


def load_config(path: Path | None) -> dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    if path is None:
        return cfg
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    if path.suffix.lower() == ".toml":
        import tomllib  # 3.11+
        loaded = tomllib.loads(path.read_text(encoding="utf-8"))
    else:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    cfg.update(loaded)
    return cfg
