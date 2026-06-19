"""Phase 1 inventory walker.

Produces a complete filesystem census of the ebook library into the shared
SQLite catalog (and an optional CSV export). Designed to be:

* **Complete** — nothing is excluded at scan time; audiobooks and comics are
  inventoried too, just flagged ``rag_eligible = False``.
* **Incremental** — re-running only re-hashes files whose size or mtime
  changed, so adding books later is cheap (no full rebuild).
* **Dependency-free** — standard library only, so it runs on the current box.

Run via ``scripts/run_inventory.py`` or ``python -m`` after installing.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pipelines.common import corpus as corpus_mod
from pipelines.common import formats
from pipelines.common.config import load_config
from pipelines.common.db import Catalog
from pipelines.common.hashing import sha256_file


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _excluded(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def _iter_files(root: Path, exclude: list[str], follow_symlinks: bool):
    """Yield files under ``root``, pruning excluded directories in-place."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        dirnames[:] = sorted(d for d in dirnames if not _excluded(d, exclude))
        for fn in sorted(filenames):
            if _excluded(fn, exclude):
                continue
            yield Path(dirpath) / fn


def run_inventory(
    *,
    roots: list[str],
    db_path: str,
    csv_path: str | None,
    exclude_globs: list[str],
    max_hash_bytes: int,
    follow_symlinks: bool,
    do_hash: bool = True,
    rehash: bool = False,
    limit: int | None = None,
    progress_every: int = 500,
    log=print,
) -> dict:
    """Walk roots and populate the catalog. Returns a summary dict."""
    run_id = datetime.now(timezone.utc).strftime("inv-%Y%m%dT%H%M%SZ")
    started = _now_iso()

    resolved_roots = []
    for r in roots:
        p = Path(r).expanduser()
        if not p.exists():
            log(f"  [warn] root does not exist, skipping: {p}")
            continue
        resolved_roots.append(p.resolve())
    if not resolved_roots:
        raise SystemExit("No valid roots to scan. Pass --root or set 'roots' in config.")

    files_seen = files_hashed = errors = bytes_total = 0
    t0 = time.time()

    with Catalog(Path(db_path)) as cat:
        cat.start_run(run_id, started, json.dumps([str(r) for r in resolved_roots]))

        for root in resolved_roots:
            log(f"  scanning root: {root}")
            for fpath in _iter_files(root, exclude_globs, follow_symlinks):
                if limit is not None and files_seen >= limit:
                    break
                files_seen += 1
                row = _build_row(
                    cat, fpath, root, run_id,
                    do_hash=do_hash, rehash=rehash,
                    max_hash_bytes=max_hash_bytes,
                )
                if row["error"]:
                    errors += 1
                if row["sha256"] is not None and row["_hashed_now"]:
                    files_hashed += 1
                if row["size_bytes"]:
                    bytes_total += row["size_bytes"]
                row.pop("_hashed_now", None)
                cat.upsert_file(row)

                if files_seen % progress_every == 0:
                    rate = files_seen / max(time.time() - t0, 1e-6)
                    log(f"    {files_seen:,} files  ({rate:,.0f}/s)  "
                        f"{files_hashed:,} hashed  {errors} errors")
                    cat.commit()
            if limit is not None and files_seen >= limit:
                log(f"  [limit] stopping at {limit} files")
                break

        cat.commit()
        cat.finish_run(
            run_id, _now_iso(),
            files_seen=files_seen, files_hashed=files_hashed,
            bytes_total=bytes_total, errors=errors,
        )
        summary = cat.summary()
        summary["run_id"] = run_id
        summary["files_hashed_this_run"] = files_hashed
        summary["errors"] = errors
        summary["elapsed_sec"] = round(time.time() - t0, 1)

        if csv_path:
            n = cat.export_csv(Path(csv_path))
            summary["csv_rows"] = n
            summary["csv_path"] = str(csv_path)

    return summary


def _build_row(cat: Catalog, fpath: Path, root: Path, run_id: str, *,
               do_hash: bool, rehash: bool, max_hash_bytes: int) -> dict:
    now = _now_iso()
    error = None
    sha = None
    hashed_now = False
    try:
        st = fpath.stat()
        size = st.st_size
        mtime = st.st_mtime
    except OSError as exc:
        # Record the path even if we can't stat it, so it isn't silently lost.
        size = None
        mtime = None
        error = f"stat: {exc}"

    rel = fpath.relative_to(root)
    top_folder = rel.parts[0] if len(rel.parts) > 1 else ""
    info = formats.classify(fpath.name)
    ext = fpath.suffix.lstrip(".").lower()
    path_str = str(fpath)

    prior = cat.existing_signature(path_str)
    first_seen = cat.first_seen_for(path_str) or now

    # Decide whether to (re)hash.
    if error is None and do_hash and info.category != formats.CAT_METADATA:
        unchanged = (
            prior is not None
            and prior[0] == size
            and prior[1] == mtime
            and prior[2] is not None
        )
        if unchanged and not rehash:
            sha = prior[2]  # reuse stored hash; cheap incremental path
        else:
            try:
                cap = max_hash_bytes if max_hash_bytes and max_hash_bytes > 0 else None
                sha = sha256_file(fpath, max_bytes=cap)
                hashed_now = sha is not None
            except OSError as exc:
                error = f"hash: {exc}"
                sha = None

    corpus_hint = corpus_mod.hint_from_path(path_str.lower())

    return {
        "path": path_str,
        "root": str(root),
        "rel_path": str(rel),
        "top_folder": top_folder,
        "filename": fpath.name,
        "ext": ext,
        "fmt": info.fmt,
        "category": info.category,
        "rag_eligible": 1 if info.rag_eligible else 0,
        "size_bytes": size,
        "mtime": mtime,
        "sha256": sha,
        "corpus": "unassigned",            # authoritative; set in Phase 3
        "corpus_hint": corpus_hint,
        "run_id": run_id,
        "first_seen": first_seen,
        "last_seen": now,
        "error": error,
        "_hashed_now": hashed_now,
    }


def _human_bytes(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or unit == "TB":
            return f"{f:.1f} {unit}"
        f /= 1024
    return f"{f:.1f} TB"


def _print_summary(summary: dict, log=print) -> None:
    log("")
    log("=" * 60)
    log(f"Inventory run: {summary['run_id']}")
    log(f"  total files inventoried : {summary['total_files']:,}")
    log(f"  RAG-eligible (text)     : {summary['rag_eligible']:,}")
    log(f"  hashed this run         : {summary['files_hashed_this_run']:,}")
    log(f"  total size              : {_human_bytes(summary['total_bytes'])}")
    log(f"  exact-duplicate groups  : {summary['duplicate_groups']:,} "
        f"({summary['files_in_dup_groups']:,} files)")
    log(f"  errors                  : {summary['errors']:,}")
    log(f"  elapsed                 : {summary['elapsed_sec']}s")
    log("  by category:")
    for cat, n in sorted(summary["by_category"].items()):
        log(f"    {cat:<14} {n:,}")
    log("  by corpus hint:")
    for c, n in sorted(summary["by_corpus_hint"].items()):
        log(f"    {c:<22} {n:,}")
    if summary.get("csv_path"):
        log(f"  CSV export: {summary['csv_path']} ({summary['csv_rows']:,} rows)")
    log("=" * 60)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_inventory",
        description="Phase 1 — complete filesystem inventory of the ebook library.",
    )
    p.add_argument("--config", type=Path, help="JSON or TOML config file.")
    p.add_argument("--root", action="append", default=[],
                   help="Directory to scan (repeatable). Overrides config roots.")
    p.add_argument("--db", help="SQLite catalog path (overrides config).")
    p.add_argument("--csv", help="CSV export path (overrides config). "
                                 "Pass '' to skip CSV.")
    p.add_argument("--no-hash", action="store_true",
                   help="Skip content hashing (fast path census only).")
    p.add_argument("--rehash", action="store_true",
                   help="Re-hash every file even if size/mtime are unchanged.")
    p.add_argument("--max-hash-mb", type=float, default=None,
                   help="Skip hashing files larger than N MB (still inventoried).")
    p.add_argument("--limit", type=int, default=None,
                   help="Stop after N files (for testing).")
    p.add_argument("--quiet", action="store_true", help="Suppress progress.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    cfg = load_config(args.config)

    roots = args.root or cfg.get("roots", [])
    db_path = args.db or cfg["db_path"]
    if args.csv is not None:
        csv_path = args.csv or None
    else:
        csv_path = cfg.get("csv_path")
    max_hash_bytes = cfg.get("max_hash_bytes", 0)
    if args.max_hash_mb is not None:
        max_hash_bytes = int(args.max_hash_mb * 1024 * 1024)

    log = (lambda *a, **k: None) if args.quiet else print

    if not roots:
        print("error: no roots configured. Use --root PATH or set 'roots' in a "
              "--config file.", file=sys.stderr)
        return 2

    summary = run_inventory(
        roots=roots,
        db_path=db_path,
        csv_path=csv_path,
        exclude_globs=cfg.get("exclude_globs", []),
        max_hash_bytes=max_hash_bytes,
        follow_symlinks=cfg.get("follow_symlinks", False),
        do_hash=not args.no_hash,
        rehash=args.rehash,
        limit=args.limit,
        log=log,
    )
    _print_summary(summary, log=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
