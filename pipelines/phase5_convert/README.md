# Phase 5 — EPUB Conversion

**Input:** clean, corpus-partitioned library (Phase 4). Majority of the
collection is MOBI.
**Goal:** convert RAG-eligible ebooks to a uniform **EPUB** for predictable
text extraction in ingestion.

## Approach

- Use the **Calibre CLI** (`ebook-convert`) — runs fine on the current box.
- Convert `rag_eligible` non-EPUB text formats (mobi/azw3/pdf-with-text/…) →
  EPUB; leave existing EPUBs untouched.
- Idempotent + incremental: skip titles already converted (track in catalog).
- Record conversion status/errors per file; never overwrite the source.

## Out of scope

- Audiobooks and comic images (not `rag_eligible`).
- Scanned/OCR-only PDFs are flagged for a separate OCR decision.
