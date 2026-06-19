"""The shared catalog: a single SQLite database used by every phase.

Phase 1 populates the ``files`` table; later phases add columns/tables and
read back. Keeping one catalog (rather than per-phase CSVs) is what makes the
pipeline *incremental* — re-scanning only touches changed rows, and dedup /
reconciliation / ingestion all query the same source of truth.

A CSV export is provided for eyeballing and spreadsheet reconciliation, but
SQLite is authoritative.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Iterable, Iterator

SCHEMA_VERSION = 2

# Columns that make up a file row, in stable order (also the CSV header).
FILE_COLUMNS = [
    "id",
    "path",          # absolute path, unique key
    "root",          # configured scan root this file came from
    "rel_path",      # path relative to root
    "top_folder",    # first path component under root (for hints/reporting)
    "filename",
    "ext",
    "fmt",           # normalized format token
    "category",      # ebook_text | pdf | ebook_image | audio | archive | metadata | other
    "rag_eligible",  # 0/1 — text-extractable for the RAG as-is
    "size_bytes",
    "mtime",         # source file mtime (epoch seconds)
    "sha256",        # NULL if skipped (e.g. over max_hash_bytes) or errored
    "corpus",        # authoritative corpus; 'unassigned' until Phase 3
    "corpus_hint",   # cheap path-derived guess, non-authoritative
    "run_id",        # last inventory run that touched this row
    "first_seen",    # ISO timestamp first inventoried
    "last_seen",     # ISO timestamp last inventoried
    "missing_since", # ISO timestamp the file stopped appearing in scans; NULL=present
    "error",         # per-file error message, if any
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    roots       TEXT,           -- JSON array of scanned roots
    files_seen  INTEGER DEFAULT 0,
    files_hashed INTEGER DEFAULT 0,
    bytes_total INTEGER DEFAULT 0,
    errors      INTEGER DEFAULT 0,
    note        TEXT
);

CREATE TABLE IF NOT EXISTS files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    path         TEXT UNIQUE NOT NULL,
    root         TEXT NOT NULL,
    rel_path     TEXT NOT NULL,
    top_folder   TEXT,
    filename     TEXT NOT NULL,
    ext          TEXT,
    fmt          TEXT,
    category     TEXT,
    rag_eligible INTEGER DEFAULT 0,
    size_bytes   INTEGER,
    mtime        REAL,
    sha256       TEXT,
    corpus       TEXT DEFAULT 'unassigned',
    corpus_hint  TEXT DEFAULT 'unassigned',
    run_id       TEXT,
    first_seen   TEXT,
    last_seen    TEXT,
    missing_since TEXT,
    error        TEXT
);

CREATE INDEX IF NOT EXISTS idx_files_sha256   ON files(sha256);
CREATE INDEX IF NOT EXISTS idx_files_size     ON files(size_bytes);
CREATE INDEX IF NOT EXISTS idx_files_fmt      ON files(fmt);
CREATE INDEX IF NOT EXISTS idx_files_category ON files(category);
CREATE INDEX IF NOT EXISTS idx_files_corpus   ON files(corpus);

-- Exact-duplicate groups (size + content hash). Phase 2 builds on this.
CREATE VIEW IF NOT EXISTS duplicate_groups AS
    SELECT sha256, size_bytes, COUNT(*) AS copies,
           GROUP_CONCAT(path, char(10)) AS paths
    FROM files
    WHERE sha256 IS NOT NULL
    GROUP BY sha256
    HAVING COUNT(*) > 1;
"""


class Catalog:
    """Thin wrapper around the SQLite catalog."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    def _migrate(self) -> None:
        """Bring an older catalog up to the current schema, idempotently."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(files)")}
        if "missing_since" not in cols:  # schema v1 -> v2
            self.conn.execute("ALTER TABLE files ADD COLUMN missing_since TEXT")

    # -- run bookkeeping ---------------------------------------------------
    def start_run(self, run_id: str, started_at: str, roots_json: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO runs(run_id, started_at, roots) VALUES(?,?,?)",
            (run_id, started_at, roots_json),
        )
        self.conn.commit()

    def finish_run(self, run_id: str, finished_at: str, *, files_seen: int,
                   files_hashed: int, bytes_total: int, errors: int) -> None:
        self.conn.execute(
            """UPDATE runs SET finished_at=?, files_seen=?, files_hashed=?,
                   bytes_total=?, errors=? WHERE run_id=?""",
            (finished_at, files_seen, files_hashed, bytes_total, errors, run_id),
        )
        self.conn.commit()

    # -- missing / prune (deletes & moves) --------------------------------
    @staticmethod
    def _roots_clause(roots: list[str]) -> tuple[str, list[str]]:
        placeholders = ",".join("?" for _ in roots)
        return placeholders, list(roots)

    def count_missing(self, run_id: str, roots: list[str]) -> int:
        """Rows under the scanned roots that this run did NOT see."""
        if not roots:
            return 0
        ph, params = self._roots_clause(roots)
        row = self.conn.execute(
            f"SELECT COUNT(*) n FROM files "
            f"WHERE run_id != ? AND root IN ({ph})",
            [run_id, *params],
        ).fetchone()
        return row["n"]

    def mark_missing(self, run_id: str, roots: list[str], now: str) -> int:
        """Stamp ``missing_since`` on rows not seen this run. Returns count newly
        marked. Files seen this run already had ``missing_since`` cleared on
        upsert, so a file that reappears is automatically un-marked."""
        if not roots:
            return 0
        ph, params = self._roots_clause(roots)
        cur = self.conn.execute(
            f"UPDATE files SET missing_since=? "
            f"WHERE run_id != ? AND missing_since IS NULL AND root IN ({ph})",
            [now, run_id, *params],
        )
        self.conn.commit()
        return cur.rowcount

    def prune_missing(self, run_id: str, roots: list[str]) -> int:
        """Hard-delete rows under the scanned roots not seen this run."""
        if not roots:
            return 0
        ph, params = self._roots_clause(roots)
        cur = self.conn.execute(
            f"DELETE FROM files WHERE run_id != ? AND root IN ({ph})",
            [run_id, *params],
        )
        self.conn.commit()
        return cur.rowcount

    # -- incremental lookups ----------------------------------------------
    def existing_signature(self, path: str) -> tuple[int, float, str | None] | None:
        """Return (size_bytes, mtime, sha256) for a known path, or None."""
        row = self.conn.execute(
            "SELECT size_bytes, mtime, sha256, first_seen FROM files WHERE path=?",
            (path,),
        ).fetchone()
        if row is None:
            return None
        return row["size_bytes"], row["mtime"], row["sha256"]

    def first_seen_for(self, path: str) -> str | None:
        row = self.conn.execute(
            "SELECT first_seen FROM files WHERE path=?", (path,)
        ).fetchone()
        return row["first_seen"] if row else None

    # -- writes ------------------------------------------------------------
    def upsert_file(self, row: dict) -> None:
        cols = [c for c in FILE_COLUMNS if c != "id"]
        placeholders = ",".join("?" for _ in cols)
        assignments = ",".join(f"{c}=excluded.{c}" for c in cols if c != "path"
                               and c != "first_seen")
        sql = (
            f"INSERT INTO files ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(path) DO UPDATE SET {assignments}"
        )
        self.conn.execute(sql, [row.get(c) for c in cols])

    def commit(self) -> None:
        self.conn.commit()

    # -- reporting ---------------------------------------------------------
    def summary(self) -> dict:
        cur = self.conn
        total = cur.execute("SELECT COUNT(*) n FROM files").fetchone()["n"]
        by_cat = {
            r["category"]: r["n"]
            for r in cur.execute(
                "SELECT category, COUNT(*) n FROM files GROUP BY category"
            )
        }
        by_corpus = {
            r["corpus_hint"]: r["n"]
            for r in cur.execute(
                "SELECT corpus_hint, COUNT(*) n FROM files GROUP BY corpus_hint"
            )
        }
        rag = cur.execute(
            "SELECT COUNT(*) n FROM files WHERE rag_eligible=1"
        ).fetchone()["n"]
        dupes = cur.execute(
            "SELECT COUNT(*) n FROM duplicate_groups"
        ).fetchone()["n"]
        dup_files = cur.execute(
            "SELECT COALESCE(SUM(copies),0) n FROM duplicate_groups"
        ).fetchone()["n"]
        size = cur.execute(
            "SELECT COALESCE(SUM(size_bytes),0) n FROM files"
        ).fetchone()["n"]
        return {
            "total_files": total,
            "rag_eligible": rag,
            "by_category": by_cat,
            "by_corpus_hint": by_corpus,
            "duplicate_groups": dupes,
            "files_in_dup_groups": dup_files,
            "total_bytes": size,
        }

    def iter_rows(self) -> Iterator[sqlite3.Row]:
        yield from self.conn.execute(
            f"SELECT {','.join(FILE_COLUMNS)} FROM files ORDER BY path"
        )

    def export_csv(self, csv_path: Path) -> int:
        csv_path = Path(csv_path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(FILE_COLUMNS)
            for row in self.iter_rows():
                writer.writerow([row[c] for c in FILE_COLUMNS])
                n += 1
        return n

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Catalog":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
