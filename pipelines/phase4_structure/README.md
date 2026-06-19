# Phase 4 — Clean Folder Structure

**Input:** reconciled catalog with authoritative `corpus` and dedup decisions.
**Goal:** emit a clean, **corpus-partitioned** target layout and the moves to
get there.

## Target shape (illustrative)

```
Library/
  trusted-nonfiction/   <Author>/<Title>/<Title>.<ext>
  fiction/              ...
  untrusted-nonfiction/ ...
  ghostwriting/         ...
  _non_rag/             audiobooks, comics (inventoried, not text-RAG)
```

## What happens here

- Generate a move/copy plan (dry-run first; reversible manifest).
- Apply dedup decisions physically (one canonical copy per title).
- Keep the catalog in sync (paths updated, not re-scanned from scratch).

Corpus partitioning at the filesystem level mirrors the per-corpus collections
used in Phase 6, so ingestion is a straight folder→collection mapping.
