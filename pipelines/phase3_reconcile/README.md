# Phase 3 — Spreadsheet Reconciliation

**Input:** deduped catalog (Phases 1–2) + the long-maintained collections
spreadsheet.
**Goal:** reconcile what's *on disk* against what's *recorded*, and make the
authoritative **corpus** assignment for each title.

## What happens here

- Match catalog rows to spreadsheet entries (by title/author/ISBN).
- Report: on disk but not in sheet; in sheet but missing on disk; mismatches.
- **Set the authoritative `corpus`** per title — this is the human decision
  the inventory deliberately deferred. `corpus_hint` from Phase 1 seeds it;
  this phase confirms `trusted-nonfiction` / `fiction` /
  `untrusted-nonfiction` / `ghostwriting`.
- Decide nonfiction-vs-fiction for ambiguous items (incl. the
  `15000KindleBooks` and any nonfiction `AudioBooks`).

## Output

- Updated `files.corpus` (authoritative).
- A reconciliation report (matched / unmatched / conflicts).
