# Phase 6 — RAG Ingestion  *(blocked on migration)*

**Blocked behind** the Arch migration + RTX 4080 swap + Ollama / Open WebUI
setup. Phases 1–5 run now; this phase waits.

**Goal:** citation-bearing retrieval over the EPUB corpus — answers cite
**book + chapter/location**.

## Design (decided up front)

- **Corpus = collection.** Each corpus (`trusted-nonfiction`, `fiction`,
  `untrusted-nonfiction`, `ghostwriting`) maps to its own vector-store
  collection/namespace. Sibling RAGs are therefore cheap to add or skip — no
  cross-contamination, query one or many corpora explicitly.
- **Local-first:** Ollama for embeddings + generation; Open WebUI front end.
- **Citations:** chunk metadata carries `{corpus, book, author, chapter/loc,
  source_path, sha256}` so every answer is traceable to a file in the catalog.
- **Incremental ingestion:** add books later without a full rebuild (keyed on
  `sha256`; only new/changed chunks are embedded).

## Inputs

- Converted EPUBs (Phase 5), partitioned by corpus (Phase 4).
- Catalog metadata (Phases 1–3) for citation fields.
