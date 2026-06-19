"""Phase 2 — Deduplication.

Reads the Phase 1 catalog and records, per file, a dedup *decision*:

* ``drop``   — a byte-identical copy (same ``sha256``); safe to remove. One
               canonical copy per content hash is kept.
* ``review`` — shares a normalized title with other surviving files but differs
               in format or content (likely a format variant or a different
               edition); a human decides.
* ``keep``   — unique, or the canonical of a duplicate set.

**No files are deleted.** Decisions land in the ``dedup_decisions`` table and a
report under ``data/`` for review; physical resolution happens in Phase 4.

Only exact content hashes drive ``drop``. Title-based grouping (which relies on
messy filenames until embedded metadata exists post-conversion) is *review only*.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pipelines.common.db import Catalog
from pipelines.phase2_dedup.normalize import normalize

# Preferred format when choosing which copy to keep — EPUB first, matching the
# Phase 5 conversion target. Lower rank = more preferred.
FORMAT_RANK = {
    "epub": 0, "azw3": 1, "azw": 2, "kfx": 2, "fb2": 2,
    "mobi": 3, "prc": 3, "pdb": 3, "lit": 4, "htmlz": 4, "html": 4,
    "txt": 5, "rtf": 5, "md": 5, "doc": 6, "docx": 6, "odt": 6,
    "pdf": 7, "djvu": 8,
}
_DEFAULT_RANK = 9


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rank(fmt: str | None) -> int:
    return FORMAT_RANK.get((fmt or "").lower(), _DEFAULT_RANK)


def _canonical(rows: list) -> object:
    """Pick the copy to keep: prefer RAG-eligible, then best format, then the
    shallowest then lexicographically-smallest path (stable + deterministic)."""
    return min(rows, key=lambda r: (
        0 if r["rag_eligible"] else 1,
        _rank(r["fmt"]),
        len(r["rel_path"]),
        r["path"],
    ))


def _work_group_id(work_key: str) -> str:
    return "w-" + hashlib.blake2s(work_key.encode("utf-8")).hexdigest()[:10]


def run_dedup(*, db_path: str, report_dir: str | None = "data",
              log=print) -> dict:
    run_id = datetime.now(timezone.utc).strftime("dedup-%Y%m%dT%H%M%S-%fZ")
    now = _now_iso()
    t0 = time.time()

    with Catalog(Path(db_path)) as cat:
        files = cat.files_for_dedup()
        log(f"  loaded {len(files):,} cataloged files")

        norm = {r["id"]: normalize(r["filename"]) for r in files}
        # Effective norm: byte-identical copies are the same work, so a kept
        # canonical inherits the richest (most significant tokens) title among
        # its copies — a sparse filename on the kept copy shouldn't lose the
        # title carried by a sibling copy.
        eff = dict(norm)

        # 1) Exact duplicates by content hash.
        by_sha: dict[str, list] = {}
        for r in files:
            if r["sha256"]:
                by_sha.setdefault(r["sha256"], []).append(r)

        decisions: dict[int, dict] = {}
        dropped: set[int] = set()
        exact_groups = 0
        reclaimable = 0
        exact_canon_copies: dict[int, int] = {}

        for sha, group in by_sha.items():
            if len(group) < 2:
                continue
            exact_groups += 1
            canon = _canonical(group)
            exact_canon_copies[canon["id"]] = len(group)
            # Kept copy inherits the richest title among byte-identical copies.
            richest = max(group, key=lambda r: len(norm[r["id"]][1].split()))
            eff[canon["id"]] = norm[richest["id"]]
            gid = "x-" + sha[:12]
            for r in group:
                if r["id"] == canon["id"]:
                    continue
                dropped.add(r["id"])
                reclaimable += r["size_bytes"] or 0
                decisions[r["id"]] = _row(
                    r, eff, gid, "exact", "drop", canon["id"], run_id, now,
                    reason=f"byte-identical duplicate (sha256 {sha[:12]}); "
                           f"canonical kept = file #{canon['id']}",
                )

        # 2) Same-work grouping among *survivors* (exact canonicals + uniques).
        survivors = [r for r in files if r["id"] not in dropped]
        by_work: dict[str, list] = {}
        for r in survivors:
            wk = eff[r["id"]][1]
            if wk:
                by_work.setdefault(wk, []).append(r)

        work_groups = 0
        work_review_files = 0
        for wk, group in by_work.items():
            if len(group) < 2:
                continue
            work_groups += 1
            gid = _work_group_id(wk)
            suggest = _canonical(group)
            fmts = sorted({(r["fmt"] or "?") for r in group})
            for r in group:
                work_review_files += 1
                tag = "suggested keep" if r["id"] == suggest["id"] else "variant"
                decisions[r["id"]] = _row(
                    r, eff, gid, "work_variant", "review", suggest["id"],
                    run_id, now,
                    reason=f"same normalized title as {len(group) - 1} other "
                           f"file(s); formats {fmts} — review (format variant "
                           f"or edition) [{tag}]",
                )

        # 3) Everything else is a clean keep.
        for r in files:
            if r["id"] in decisions:
                continue
            copies = exact_canon_copies.get(r["id"])
            reason = (f"canonical of {copies} byte-identical copies"
                      if copies else "no duplicates detected")
            decisions[r["id"]] = _row(
                r, eff, None, "unique", "keep", r["id"], run_id, now,
                reason=reason,
            )

        cat.replace_dedup_decisions(list(decisions.values()))

        summary = {
            "run_id": run_id,
            "total_files": len(files),
            "exact_groups": exact_groups,
            "drop_files": len(dropped),
            "reclaimable_bytes": reclaimable,
            "work_variant_groups": work_groups,
            "work_review_files": work_review_files,
            "keep_files": sum(1 for d in decisions.values() if d["role"] == "keep"),
            "elapsed_sec": round(time.time() - t0, 2),
        }

        if report_dir:
            paths = _write_reports(cat, Path(report_dir), summary)
            summary.update(paths)

    return summary


def _row(r, norm, gid, gtype, role, canon_id, run_id, now, *, reason):
    title_norm, work_key = norm[r["id"]]
    return {
        "file_id": r["id"],
        "title_norm": title_norm,
        "work_key": work_key,
        "group_id": gid,
        "group_type": gtype,
        "role": role,
        "canonical_file_id": canon_id,
        "reason": reason,
        "run_id": run_id,
        "decided_at": now,
    }


def _human_bytes(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if f < 1024 or unit == "TB":
            return f"{f:.1f} {unit}"
        f /= 1024
    return f"{f:.1f} TB"


def _write_reports(cat: Catalog, report_dir: Path, summary: dict) -> dict:
    report_dir.mkdir(parents=True, exist_ok=True)
    rows = cat.dedup_decision_rows()

    # CSV: only the actionable rows (drop + review).
    import csv
    csv_path = report_dir / "dedup_report.csv"
    actionable = [r for r in rows if r["role"] in ("drop", "review")]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["group_id", "group_type", "role", "canonical_file_id",
                    "file_id", "path", "fmt", "size_bytes", "sha256", "reason"])
        for r in actionable:
            w.writerow([r["group_id"], r["group_type"], r["role"],
                        r["canonical_file_id"], r["file_id"], r["path"],
                        r["fmt"], r["size_bytes"], r["sha256"], r["reason"]])

    md_path = report_dir / "dedup_report.md"
    lines = [
        "# Phase 2 — Deduplication report",
        "",
        f"Run `{summary['run_id']}` · {summary['total_files']:,} files",
        "",
        "## Summary",
        f"- Exact-duplicate groups: **{summary['exact_groups']:,}**",
        f"- Redundant copies to drop: **{summary['drop_files']:,}** "
        f"(reclaims **{_human_bytes(summary['reclaimable_bytes'])}**)",
        f"- Same-work review groups: **{summary['work_variant_groups']:,}** "
        f"({summary['work_review_files']:,} files)",
        f"- Clean keeps: **{summary['keep_files']:,}**",
        "",
        "No files were deleted. `drop` rows are byte-identical (safe); "
        "`review` rows are filename-based suggestions for a human to confirm. "
        "Physical resolution happens in Phase 4.",
        "",
        "## Largest exact-duplicate groups",
        "",
        "| copies | size each | reclaims | sha256 | example path |",
        "| ---: | ---: | ---: | --- | --- |",
    ]
    top = cat.conn.execute(
        "SELECT sha256, size_bytes, COUNT(*) copies, MIN(path) ex "
        "FROM files WHERE sha256 IS NOT NULL GROUP BY sha256 "
        "HAVING COUNT(*) > 1 ORDER BY (COUNT(*)-1)*size_bytes DESC LIMIT 25"
    ).fetchall()
    for r in top:
        reclaim = (r["copies"] - 1) * (r["size_bytes"] or 0)
        lines.append(
            f"| {r['copies']} | {_human_bytes(r['size_bytes'] or 0)} | "
            f"{_human_bytes(reclaim)} | `{r['sha256'][:12]}` | {r['ex']} |"
        )
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return {"csv_path": str(csv_path), "md_path": str(md_path)}


def _print_summary(s: dict, log=print) -> None:
    log("")
    log("=" * 60)
    log(f"Dedup run: {s['run_id']}")
    log(f"  files analyzed          : {s['total_files']:,}")
    log(f"  exact-duplicate groups  : {s['exact_groups']:,}")
    log(f"  redundant copies (drop) : {s['drop_files']:,}")
    log(f"  reclaimable space       : {_human_bytes(s['reclaimable_bytes'])}")
    log(f"  same-work review groups : {s['work_variant_groups']:,} "
        f"({s['work_review_files']:,} files)")
    log(f"  clean keeps             : {s['keep_files']:,}")
    log(f"  elapsed                 : {s['elapsed_sec']}s")
    if s.get("md_path"):
        log(f"  report : {s['md_path']}")
        log(f"  csv    : {s['csv_path']}")
    log("=" * 60)
    log("No files were deleted. Review 'drop'/'review' rows before Phase 4.")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_dedup",
        description="Phase 2 — record deduplication decisions (no deletions).",
    )
    p.add_argument("--db", default="data/catalog.sqlite",
                   help="SQLite catalog path (from Phase 1).")
    p.add_argument("--report-dir", default="data",
                   help="Where to write dedup_report.{md,csv}. '' to skip.")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if not Path(args.db).exists():
        print(f"error: catalog not found: {args.db}\n"
              f"Run Phase 1 (scripts/run_inventory.py) first.", file=sys.stderr)
        return 2
    log = (lambda *a, **k: None) if args.quiet else print
    summary = run_dedup(db_path=args.db,
                        report_dir=args.report_dir or None, log=log)
    _print_summary(summary, log=print)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
