"""Tests for Phase 1 inventory.

Run with: python3 -m pytest   (or: python3 tests/test_inventory.py)
Standard library only — no pytest required to execute the smoke checks.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipelines.common import corpus, formats          # noqa: E402
from pipelines.common.db import Catalog               # noqa: E402
from pipelines.phase1_inventory.inventory import run_inventory  # noqa: E402


def _make_library(base: Path) -> None:
    """Build a tiny fake library covering each category + a duplicate."""
    (base / "Nonfiction").mkdir(parents=True)
    (base / "Fiction").mkdir(parents=True)
    (base / "AudioBooks").mkdir(parents=True)
    (base / "ComicBookPDFs").mkdir(parents=True)

    (base / "Nonfiction" / "sapiens.mobi").write_bytes(b"IDENTICAL-CONTENT")
    # Exact duplicate of the above, different folder + name.
    (base / "Fiction" / "copy_of_sapiens.mobi").write_bytes(b"IDENTICAL-CONTENT")
    (base / "Nonfiction" / "guns.epub").write_bytes(b"unique-epub-bytes")
    (base / "AudioBooks" / "lecture.mp3").write_bytes(b"fake-audio")
    (base / "ComicBookPDFs" / "issue1.cbz").write_bytes(b"fake-comic")
    (base / "Nonfiction" / "cover.jpg").write_bytes(b"img")  # metadata sidecar


def test_classify():
    assert formats.classify("a.mobi").category == formats.CAT_EBOOK_TEXT
    assert formats.classify("a.mobi").rag_eligible is True
    assert formats.classify("a.mp3").category == formats.CAT_AUDIO
    assert formats.classify("a.mp3").rag_eligible is False
    assert formats.classify("a.cbz").category == formats.CAT_EBOOK_IMAGE
    assert formats.classify("a.cbz").rag_eligible is False
    assert formats.classify("a.pdf").category == formats.CAT_PDF
    assert formats.classify("noext").fmt == "unknown"


def test_corpus_hint_nonfiction_beats_fiction():
    # "nonfiction" contains the substring "fiction" — order must be correct.
    assert corpus.hint_from_path("/x/nonfiction/book.mobi") == corpus.TRUSTED_NONFICTION
    assert corpus.hint_from_path("/x/fiction/book.mobi") == corpus.FICTION
    assert corpus.hint_from_path("/x/ghostwriting/c.docx") == corpus.GHOSTWRITING
    assert corpus.hint_from_path("/x/random/book.mobi") == corpus.UNASSIGNED


def test_run_inventory_full(tmp_path: Path):
    lib = tmp_path / "library"
    lib.mkdir()
    _make_library(lib)
    db = tmp_path / "catalog.sqlite"
    csv = tmp_path / "inv.csv"

    summary = run_inventory(
        roots=[str(lib)],
        db_path=str(db),
        csv_path=str(csv),
        exclude_globs=[".DS_Store"],
        max_hash_bytes=0,
        follow_symlinks=False,
        log=lambda *a, **k: None,
    )

    # Complete census: every file, including audiobook + comic + sidecar.
    assert summary["total_files"] == 6
    # RAG-eligible = 2 mobi + 1 epub (audio/comic/jpg excluded).
    assert summary["rag_eligible"] == 3
    # The two identical mobis form one exact-duplicate group.
    assert summary["duplicate_groups"] == 1
    assert summary["files_in_dup_groups"] == 2
    assert summary["by_category"][formats.CAT_AUDIO] == 1
    assert summary["by_category"][formats.CAT_EBOOK_IMAGE] == 1
    assert csv.exists()


def test_incremental_rescan_is_cheap(tmp_path: Path):
    lib = tmp_path / "library"
    lib.mkdir()
    _make_library(lib)
    db = tmp_path / "catalog.sqlite"

    first = run_inventory(
        roots=[str(lib)], db_path=str(db), csv_path=None,
        exclude_globs=[], max_hash_bytes=0, follow_symlinks=False,
        log=lambda *a, **k: None,
    )
    assert first["files_hashed_this_run"] == 5  # 6 files minus the jpg sidecar

    # Second run: nothing changed -> nothing re-hashed, same totals.
    second = run_inventory(
        roots=[str(lib)], db_path=str(db), csv_path=None,
        exclude_globs=[], max_hash_bytes=0, follow_symlinks=False,
        log=lambda *a, **k: None,
    )
    assert second["files_hashed_this_run"] == 0
    assert second["total_files"] == first["total_files"]


def test_corpus_field_is_first_class(tmp_path: Path):
    lib = tmp_path / "library"
    lib.mkdir()
    _make_library(lib)
    db = tmp_path / "catalog.sqlite"
    run_inventory(
        roots=[str(lib)], db_path=str(db), csv_path=None,
        exclude_globs=[], max_hash_bytes=0, follow_symlinks=False,
        log=lambda *a, **k: None,
    )
    with Catalog(db) as cat:
        rows = list(cat.iter_rows())
    # Authoritative corpus stays 'unassigned'; hint is populated from path.
    assert all(r["corpus"] == "unassigned" for r in rows)
    assert any(r["corpus_hint"] == corpus.TRUSTED_NONFICTION for r in rows)
    assert any(r["corpus_hint"] == corpus.FICTION for r in rows)


def _run_all():
    import tempfile
    test_classify()
    test_corpus_hint_nonfiction_beats_fiction()
    for fn in (test_run_inventory_full, test_incremental_rescan_is_cheap,
               test_corpus_field_is_first_class):
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    print("All inventory smoke tests passed.")


if __name__ == "__main__":
    _run_all()
