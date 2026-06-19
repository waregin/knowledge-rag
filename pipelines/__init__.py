"""knowledge-rag pipelines.

A pipeline-per-phase layout for the ebook RAG project. Each phase is a
self-contained package under ``pipelines/`` that reads the shared SQLite
catalog produced by Phase 1 and writes its own results back into it.

Phases:
    phase1_inventory   Filesystem census (paths, formats, sizes, hashes)
    phase2_dedup       Exact/near-duplicate detection
    phase3_reconcile   Reconcile against the collections spreadsheet
    phase4_structure   Emit a clean, corpus-aware folder layout
    phase5_convert     Convert to EPUB via Calibre CLI
    phase6_ingest      Citation-bearing RAG ingestion (Ollama / local stack)
"""
