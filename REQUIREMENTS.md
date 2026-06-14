# knowledge-rag — Requirements & Context (NEW REPO)

> **Sequencing note:** full local-stack build is blocked behind the Arch migration + RTX 4080 swap + Ollama/Open WebUI setup — but the *ebook preparation phases are not blocked* and are also move-relevant (every book confidently in the RAG is a book easier to part with physically).

## Purpose
RAG knowledge base over Reggie's 20,000+ trusted nonfiction ebooks, with **proper citations**, so the books function as a queryable reference library even if never read cover-to-cover.

## The six-phase plan (already scoped in a prior session — verify/refine)
1. Filesystem inventory (note: previously skipped folders flagged in TickTick: 15000KindleBooks, AudioBooks, ComicBookPDFs)
2. Deduplication
3. Spreadsheet reconciliation (against long-maintained collections spreadsheet)
4. Clean folder structure
5. EPUB conversion (majority of collection is MOBI)
6. RAG ingestion

## Possible sibling corpora (decide later, separate planning prompt exists)
- Fiction RAG (uncertain value)
- "Untrustworthy nonfiction" RAG (e.g., apologetics — for responding to arguments)
- Premium ghostwriting RAG (client/niche reference corpus)
Design the ingestion pipeline so corpus = a first-class concept (separate collections/namespaces), making these cheap to add or skip later.

## Requirements
- **Functional:** Citation-bearing retrieval (book, chapter/location); corpus separation; incremental ingestion (add books later without full rebuild)
- **Non-functional:** Local-first (Ollama + Open WebUI stack); vector store choice informed by prior capacity research; phases 1–5 runnable on current Zorin box now
- **Constraint:** Phases 1–5 are mostly Python + Calibre CLI work — start them pre-migration

## First session objectives
1. Confirm/refine the six phases; scaffold repo with a pipeline-per-phase layout
2. Build phase 1 (inventory script) in-session — it's low-risk and unblocks everything
3. Open issues for remaining phases; label phase 2 `next`
