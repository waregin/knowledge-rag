"""Corpus is a first-class concept across the whole pipeline.

Designing corpus separation in from the start makes sibling RAGs cheap to add
or skip later. Every catalog row carries a ``corpus`` column; downstream
ingestion (Phase 6) maps one corpus -> one vector-store collection/namespace,
so the trusted-nonfiction RAG and any siblings never cross-contaminate.

Known corpora
-------------
* ``trusted-nonfiction``   the primary, citation-bearing reference RAG
* ``fiction``              novels / stories (uncertain value, kept separate)
* ``untrusted-nonfiction`` e.g. apologetics — for *responding to* arguments
* ``ghostwriting``         premium client/niche reference corpus
* ``unassigned``           default until Phase 3 reconciliation decides

The inventory does NOT try to truly classify corpus from the filesystem — that
is a human/spreadsheet decision made in Phase 3. It only records a cheap
``corpus_hint`` derived from the top-level folder name, to speed that later
review. The authoritative ``corpus`` stays ``unassigned`` until reconciled.
"""

from __future__ import annotations

TRUSTED_NONFICTION = "trusted-nonfiction"
FICTION = "fiction"
UNTRUSTED_NONFICTION = "untrusted-nonfiction"
GHOSTWRITING = "ghostwriting"
UNASSIGNED = "unassigned"

KNOWN_CORPORA = (
    TRUSTED_NONFICTION,
    FICTION,
    UNTRUSTED_NONFICTION,
    GHOSTWRITING,
    UNASSIGNED,
)

# Ordered, first-match-wins keyword heuristics over the lowercased path.
# Order matters: "nonfiction" must beat the substring "fiction".
_HINT_RULES: list[tuple[tuple[str, ...], str]] = [
    (("ghostwrit", "ghost-writ", "client",), GHOSTWRITING),
    (("apologetic", "untrust", "creationism", "pseudo"), UNTRUSTED_NONFICTION),
    (("nonfiction", "non-fiction", "non fiction"), TRUSTED_NONFICTION),
    (("fiction", "novel", "sci-fi", "scifi", "fantasy", "romance"), FICTION),
]


def hint_from_path(path_lower: str) -> str:
    """Best-effort, non-authoritative corpus guess from a (lowercased) path.

    Returns ``UNASSIGNED`` when nothing matches. This is only a hint to make
    Phase 3 review faster; it never sets the authoritative ``corpus`` field.
    """
    for needles, corpus in _HINT_RULES:
        for needle in needles:
            if needle in path_lower:
                return corpus
    return UNASSIGNED
