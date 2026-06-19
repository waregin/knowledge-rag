# knowledge-rag

A citation-bearing, **local** RAG over ~20,000+ trusted-nonfiction ebooks
(majority MOBI). Built as a **pipeline-per-phase** so the corpus can be
prepared on the current box now, with RAG ingestion turned on after the
hardware migration.

See **[REQUIREMENTS.md](REQUIREMENTS.md)** for context and
**[ARCHITECTURE.md](ARCHITECTURE.md)** for the design.

## Phases

1. **Filesystem inventory** — ✅ built. Complete census → SQLite + CSV.
2. **Deduplication** — `next`.
3. **Spreadsheet reconciliation** — sets authoritative corpus.
4. **Clean folder structure** — corpus-partitioned layout.
5. **EPUB conversion** — Calibre CLI.
6. **RAG ingestion** — Ollama / Open WebUI (blocked on Arch + RTX 4080).

Each phase lives in `pipelines/phaseN_*/` with its own README.

## Quick start (Phase 1)

No installation required — standard library only.

```bash
# Scan one or more folders of ebooks
python3 scripts/run_inventory.py --root /path/to/ebooks --root /path/to/kindle

# Or copy the example config, set your roots, and run
cp config/pipeline.json config/pipeline.local.json
python3 scripts/run_inventory.py --config config/pipeline.local.json
```

Outputs land in `data/` (gitignored): `catalog.sqlite` (authoritative, with a
`duplicate_groups` view) and `inventory.csv` (flat export for review).

Run tests:

```bash
python3 tests/test_inventory.py     # stdlib smoke run
python3 -m pytest                   # if pytest installed
```

## Corpus separation

`corpus` is a first-class concept throughout (`trusted-nonfiction`, `fiction`,
`untrusted-nonfiction`, `ghostwriting`), so each maps to its own RAG collection
later and sibling RAGs are cheap to add or skip. The inventory records a
`corpus_hint`; the authoritative assignment is made in Phase 3.
