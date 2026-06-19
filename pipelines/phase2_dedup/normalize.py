"""Filename normalization for grouping likely-same works (Phase 2).

Real titles/authors only become reliable once books carry embedded metadata
(after EPUB conversion in Phase 5). Until then we derive a best-effort key from
the *filename* to surface format-variants and probable editions of the same
work for human review. These keys never drive automatic deletion — only exact
content hashes (sha256) do.

``work_key`` is an order-independent set of significant tokens, so
``"Sapiens - Yuval Noah Harari.epub"`` and
``"Yuval Noah Harari - Sapiens.mobi"`` collapse to the same key.
"""

from __future__ import annotations

import re

# Tokens that say nothing about *which* work this is — formats, sources, etc.
_NOISE = {
    "epub", "mobi", "azw", "azw3", "kfx", "pdf", "prc", "pdb", "fb2", "djvu",
    "retail", "ebook", "ebooks", "book", "zlib", "lib", "libgen", "calibre",
    "kindle", "scan", "scanned", "ocr", "copy", "final", "the", "a", "an",
    "of", "and", "in", "to", "for",
}

# Edition / version noise: "3rd edition", "v5", "2e", "revised", "reprint".
_EDITION = re.compile(
    r"\b(\d+\s*(st|nd|rd|th)\s*ed(ition)?|v\d+(\.\d+)*|\d+e|revised|reprint|"
    r"unabridged|illustrated)\b"
)
_BRACKETS = re.compile(r"[\[\(\{][^\]\)\}]*[\]\)\}]")
_NONWORD = re.compile(r"[^a-z0-9 ]+")

# Minimum significant tokens before a work_key is trustworthy enough to group
# on (avoids merging on one or two generic words).
MIN_KEY_TOKENS = 3


def normalize(filename: str) -> tuple[str, str]:
    """Return ``(title_norm, work_key)`` for a filename.

    ``title_norm`` keeps token order (human-readable); ``work_key`` is the
    sorted, de-duplicated significant tokens (order-independent grouping key).
    ``work_key`` is empty when there aren't enough significant tokens.
    """
    name = filename.rsplit(".", 1)[0] if "." in filename else filename
    s = name.lower()
    s = _BRACKETS.sub(" ", s)
    s = s.replace("_", " ").replace(".", " ").replace("-", " ")
    s = _EDITION.sub(" ", s)
    s = _NONWORD.sub(" ", s)

    tokens = [t for t in s.split() if len(t) > 1 and t not in _NOISE]
    title_norm = " ".join(tokens)

    significant = sorted(set(tokens))
    work_key = " ".join(significant) if len(significant) >= MIN_KEY_TOKENS else ""
    return title_norm, work_key
