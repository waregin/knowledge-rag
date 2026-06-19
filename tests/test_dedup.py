"""Tests for Phase 2 deduplication.

Run with: python3 -m pytest   (or: python3 tests/test_dedup.py)
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipelines.common.db import Catalog                       # noqa: E402
from pipelines.phase1_inventory.inventory import run_inventory  # noqa: E402
from pipelines.phase2_dedup.normalize import normalize        # noqa: E402
from pipelines.phase2_dedup.dedup import run_dedup            # noqa: E402


def _silent(*a, **k):
    pass


def _build_library(base: Path) -> None:
    (base / "A").mkdir(parents=True)
    (base / "B").mkdir(parents=True)
    # Two byte-identical copies of one book (exact duplicate).
    (base / "A" / "Sapiens - Yuval Noah Harari.epub").write_bytes(b"SAME-BOOK")
    (base / "B" / "sapiens.epub").write_bytes(b"SAME-BOOK")
    # A format variant of the same work: same title tokens, different bytes/fmt.
    (base / "A" / "Yuval Noah Harari - Sapiens.mobi").write_bytes(b"DIFFERENT-BYTES")
    # An unrelated, unique book.
    (base / "A" / "Guns Germs and Steel - Jared Diamond.epub").write_bytes(b"UNIQUE")


def _catalog(tmp_path: Path) -> Path:
    lib = tmp_path / "library"
    lib.mkdir()
    _build_library(lib)
    db = tmp_path / "catalog.sqlite"
    run_inventory(roots=[str(lib)], db_path=str(db), csv_path=None,
                  exclude_globs=[], max_hash_bytes=0, follow_symlinks=False,
                  log=_silent)
    return db


def test_normalize_order_independent():
    _, wk1 = normalize("Sapiens - Yuval Noah Harari.epub")
    _, wk2 = normalize("Yuval Noah Harari - Sapiens.mobi")
    assert wk1 == wk2 and wk1 != ""
    # Too few significant tokens -> no grouping key.
    assert normalize("book.epub")[1] == ""


def test_exact_duplicate_drop(tmp_path: Path):
    db = _catalog(tmp_path)
    s = run_dedup(db_path=str(db), report_dir=None, log=_silent)
    # The two identical .epub copies -> 1 exact group, 1 drop.
    assert s["exact_groups"] == 1
    assert s["drop_files"] == 1
    assert s["reclaimable_bytes"] == len(b"SAME-BOOK")

    with Catalog(db) as cat:
        rows = {r["path"].split("/")[-1]: r for r in cat.dedup_decision_rows()}
    drops = [r for r in rows.values() if r["role"] == "drop"]
    assert len(drops) == 1
    # Canonical kept is the other identical copy, and it is a real file id.
    assert drops[0]["canonical_file_id"] != drops[0]["file_id"]


def test_format_variant_is_review_not_drop(tmp_path: Path):
    db = _catalog(tmp_path)
    s = run_dedup(db_path=str(db), report_dir=None, log=_silent)
    # The .mobi + the surviving .epub of Sapiens share a work key -> review.
    assert s["work_variant_groups"] == 1
    assert s["work_review_files"] == 2
    with Catalog(db) as cat:
        reviews = [r for r in cat.dedup_decision_rows() if r["role"] == "review"]
    fmts = sorted(r["fmt"] for r in reviews)
    assert fmts == ["epub", "mobi"]  # variant flagged, neither auto-dropped


def test_no_files_deleted(tmp_path: Path):
    db = _catalog(tmp_path)
    lib = tmp_path / "library"
    before = sorted(p.name for p in lib.rglob("*") if p.is_file())
    run_dedup(db_path=str(db), report_dir=None, log=_silent)
    after = sorted(p.name for p in lib.rglob("*") if p.is_file())
    assert before == after  # Phase 2 records decisions only


def test_reports_written(tmp_path: Path):
    db = _catalog(tmp_path)
    out = tmp_path / "out"
    s = run_dedup(db_path=str(db), report_dir=str(out), log=_silent)
    assert Path(s["md_path"]).exists() and Path(s["csv_path"]).exists()


def test_rerun_is_idempotent(tmp_path: Path):
    db = _catalog(tmp_path)
    first = run_dedup(db_path=str(db), report_dir=None, log=_silent)
    second = run_dedup(db_path=str(db), report_dir=None, log=_silent)
    for k in ("exact_groups", "drop_files", "work_variant_groups", "keep_files"):
        assert first[k] == second[k]
    with Catalog(db) as cat:
        n = cat.conn.execute("SELECT COUNT(*) n FROM dedup_decisions").fetchone()["n"]
    assert n == first["total_files"]  # one decision per file, no accumulation


def _run_all():
    import tempfile
    test_normalize_order_independent()
    for fn in (test_exact_duplicate_drop, test_format_variant_is_review_not_drop,
               test_no_files_deleted, test_reports_written,
               test_rerun_is_idempotent):
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    print("All dedup tests passed.")


if __name__ == "__main__":
    _run_all()
