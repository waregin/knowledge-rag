# Phase 1 — Filesystem Inventory

Produce a **complete census** of the ebook library into the shared SQLite
catalog (`data/catalog.sqlite`), plus a CSV export for eyeballing.

## Scope decision (important)

The inventory is a *complete* census for the "Trove OS" — **nothing is excluded
at scan time**. The three folders previously skipped in TickTick
(`15000KindleBooks`, `AudioBooks`, `ComicBookPDFs`) **are** inventoried now.

We never confuse *format* with *corpus*:

- **Format / category** is decided here (text ebook, pdf, comic image, audio).
- **`rag_eligible`** flags whether a file can feed the *text* RAG as-is.
  Audiobooks and comic-image archives are inventoried but flagged
  `rag_eligible = 0` (no extractable text layer today).
- **Nonfiction-vs-fiction and corpus assignment** are *downstream* decisions
  (Phase 3), not exclusions made here. Every row carries a first-class
  `corpus` field (default `unassigned`) and a cheap `corpus_hint`.

## Run it

```bash
# Point at one or more roots (no install needed; stdlib only)
python3 scripts/run_inventory.py --root /path/to/ebooks --root /path/to/kindle

# Or use a config file (recommended once roots stabilize)
cp config/pipeline.json config/pipeline.local.json   # edit "roots"
python3 scripts/run_inventory.py --config config/pipeline.local.json
```

Useful flags: `--no-hash` (fast census first), `--rehash`, `--max-hash-mb N`
(skip hashing huge audiobooks), `--limit N` (test on a slice).

## What it captures (per file)

`path, root, rel_path, top_folder, filename, ext, fmt, category,
rag_eligible, size_bytes, mtime, sha256, corpus, corpus_hint, run_id,
first_seen, last_seen, error`

- **`sha256`** — full content hash; the basis for Phase 2 exact-dedup.
- **Incremental** — re-running only re-hashes files whose size/mtime changed,
  so adding books later never triggers a full rebuild.

## Outputs

- `data/catalog.sqlite` — authoritative; has a `duplicate_groups` view.
- `data/inventory.csv` — flat export for review / spreadsheet work.

## Inspect duplicates

```sql
SELECT copies, size_bytes, paths FROM duplicate_groups ORDER BY copies DESC;
```
