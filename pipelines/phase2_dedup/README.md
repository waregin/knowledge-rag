# Phase 2 — Deduplication  *(next)*

**Input:** the `files` table from Phase 1 (`sha256`, `size_bytes`, format).
**Goal:** identify and resolve duplicate copies so each title appears once.

## Approach

1. **Exact duplicates** — group by `sha256` (the `duplicate_groups` view
   already does this). These are byte-identical copies; safe to collapse.
2. **Same-title, different-format** — e.g. a `.mobi` and `.epub` of the same
   book. Detected via normalized title/author (from filename and, later,
   embedded metadata). Keep a preferred format per title (EPUB > MOBI/AZW3 >
   PDF) but never delete blindly.
3. **Near-duplicates** — same content, trivially different bytes (re-DRM'd,
   re-tagged). Size-bucketed + fuzzy title match; flag for human review.

## Output

A `dedup` decision table (keep / drop / review) keyed by file id, plus a
canonical-title mapping. **No files are deleted by this phase** — it records
decisions; physical resolution happens in Phase 4 (clean folder structure).

## Notes

- Respect `corpus_hint` — a "duplicate" across corpora (nonfiction vs
  ghostwriting) may be intentional and must not be collapsed across corpora.
- Keep audiobooks/comics in scope for dedup even though they're not
  `rag_eligible`; the Trove OS still wants one copy of each.
