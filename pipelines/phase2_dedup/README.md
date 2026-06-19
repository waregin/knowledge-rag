# Phase 2 — Deduplication

Record a per-file dedup **decision** over the Phase 1 catalog. **No files are
deleted** — decisions land in the `dedup_decisions` table plus a report under
`data/`; physical resolution happens in Phase 4.

## Run it

```bash
python3 scripts/run_dedup.py                 # uses data/catalog.sqlite
# writes data/dedup_report.md + data/dedup_report.csv
```

Idempotent: re-running rebuilds decisions from the current catalog.

## Decisions

| role | meaning | basis | safe to auto-act? |
|------|---------|-------|-------------------|
| `drop` | redundant byte-identical copy | **`sha256`** match | yes (identical bytes) |
| `review` | same normalized title, different format/content (variant or edition) | filename tokens | **no — human decides** |
| `keep` | unique, or the canonical of a duplicate set | — | yes |

**Canonical choice** (which copy to keep): prefer RAG-eligible, then best format
(EPUB > AZW3 > MOBI > … > PDF, matching the Phase 5 target), then the shallowest
/ lexicographically-smallest path. A kept copy inherits the *richest* filename
among its byte-identical siblings, so a sparsely-named copy doesn't lose the
title another copy carried.

## What's exact vs. heuristic

- **Exact (`drop`)** is driven only by content hash — reliable, and the bulk of
  the win (the first real scan showed ~2,460 groups / ~5,000 files).
- **Same-work (`review`)** uses an order-independent key of significant filename
  tokens (so `"Sapiens - Harari.epub"` and `"Harari - Sapiens.mobi"` match). It
  requires ≥3 significant tokens to avoid false merges, and it never drops.

**Deferred:** fuzzy near-duplicate matching (edit-distance on titles) is left for
after Phase 5, when EPUB conversion gives us reliable *embedded* metadata —
filename-only fuzzy matching is too noisy to trust. See issue #7 (edition-aware
ingestion) for the related runtime check.

## Outputs

- `dedup_decisions` table (`file_id, work_key, group_id, group_type, role,
  canonical_file_id, reason`). Phase 4 consumes the `drop` set to physically
  collapse duplicates.
- `data/dedup_report.md` — human summary + largest groups.
- `data/dedup_report.csv` — every actionable (`drop`/`review`) row.

## Inspect

```sql
-- biggest space wins
SELECT role, COUNT(*), printf('%.1f GB', SUM(size_bytes)/1e9)
FROM dedup_decisions d JOIN files f ON f.id=d.file_id
WHERE role='drop';

-- format variants to review
SELECT group_id, GROUP_CONCAT(f.fmt) FROM dedup_decisions d
JOIN files f ON f.id=d.file_id WHERE role='review' GROUP BY group_id;
```

## Notes

- Corpus-aware by construction: grouping keys never cross corpora once Phase 3
  assigns them. (Today corpus is mostly `unassigned`, so exact-hash collapsing —
  always safe for identical bytes — is the active behavior.)
- Audiobooks/comics are still deduped (the Trove OS wants one copy of each) even
  though they aren't `rag_eligible`.
