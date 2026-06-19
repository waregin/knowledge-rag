# Architecture

Pipeline-per-phase layout for turning ~20,000+ trusted-nonfiction ebooks into a
citation-bearing, local RAG. Each phase is a package under `pipelines/` that
reads/writes one shared SQLite catalog.

## The six-phase plan (confirmed + refined)

| # | Phase | Status | Runs where |
|---|-------|--------|-----------|
| 1 | **Filesystem inventory** | ✅ built this session | Zorin (now) |
| 2 | Deduplication | `next` | Zorin (now) |
| 3 | Spreadsheet reconciliation | planned | Zorin (now) |
| 4 | Clean folder structure | planned | Zorin (now) |
| 5 | EPUB conversion (Calibre CLI) | planned | Zorin (now) |
| 6 | RAG ingestion | blocked on migration | Arch + RTX 4080 |

**Refinements made vs. the original scoping:**

- **Inventory is a *complete* census.** The three previously-skipped folders
  (`15000KindleBooks`, `AudioBooks`, `ComicBookPDFs`) are inventoried now. We
  separate *format* (decided at scan) from *corpus / nonfiction-vs-fiction*
  (decided in Phase 3). Audiobooks and comics are recorded but flagged
  `rag_eligible = 0`.
- **One shared SQLite catalog**, not per-phase CSVs — this is what makes the
  whole pipeline incremental (add books later, no full rebuild).
- **Corpus is first-class from Phase 1**, so sibling RAGs are cheap (below).

## Corpus separation (designed in from the start)

`corpus` is a first-class column on every catalog row, and in Phase 6 each
corpus maps 1:1 to a vector-store collection/namespace:

- `trusted-nonfiction` — the primary citation-bearing RAG
- `fiction` — kept separate (uncertain value)
- `untrusted-nonfiction` — e.g. apologetics, for *responding to* arguments
- `ghostwriting` — premium client/niche reference corpus
- `unassigned` — default until Phase 3 reconciliation decides

Phase 1 only records a non-authoritative `corpus_hint` (from the top-level
folder name); the authoritative `corpus` stays `unassigned` until a human
confirms it in Phase 3. Because corpus is threaded through the whole pipeline,
adding or skipping a sibling RAG later is a config/collection change, not a
re-architecture.

## Data flow

```
roots ──► Phase 1 inventory ──► data/catalog.sqlite ──► Phases 2–5 ──► Phase 6
              (this session)         (files table)        (in place)    (Ollama)
                                          │
                                   data/inventory.csv  (review / spreadsheet)
```

## Layout

```
pipelines/
  common/            db, formats, corpus, hashing, config (shared)
  phase1_inventory/  ✅ complete filesystem census
  phase2_dedup/      stub + README
  phase3_reconcile/  stub + README
  phase4_structure/  stub + README
  phase5_convert/    stub + README
  phase6_ingest/     stub + README
scripts/run_inventory.py   zero-install entry point
config/pipeline.json       example config (copy to *.local.json)
data/                      catalog + exports (gitignored)
tests/                     phase 1 tests
```

## Principles

- **Local-first** — Phase 1 is stdlib-only; later local-stack deps are extras.
- **Incremental everywhere** — keyed on content `sha256`.
- **Reversible** — phases record decisions; destructive moves/deletes are
  explicit, planned, and dry-runnable.
