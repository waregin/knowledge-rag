"""File-format classification for the inventory.

The inventory is a *complete* census of the library ("Trove OS"): we do not
exclude anything at scan time. Instead every file is tagged with:

* ``fmt``            normalized format token (e.g. ``epub``, ``mobi``, ``cbz``)
* ``category``       coarse bucket used for filtering and reporting
* ``rag_eligible``   whether the file can feed the *text* RAG as-is

Audiobooks and comic/image archives are still inventoried, but flagged
``rag_eligible = False`` because they carry no extractable text layer today.
Whether a given title is *nonfiction* — and which corpus it belongs to — is a
separate, downstream decision (Phase 3), not a format decision made here.
"""

from __future__ import annotations

from dataclasses import dataclass

# Coarse categories.
CAT_EBOOK_TEXT = "ebook_text"      # reflowable text ebooks (epub, mobi, ...)
CAT_PDF = "pdf"                    # PDFs: usually text, sometimes scanned
CAT_EBOOK_IMAGE = "ebook_image"    # comic / image archives (cbz, cbr, ...)
CAT_AUDIO = "audio"               # audiobooks
CAT_METADATA = "metadata"          # sidecars (opf, cover.jpg, ...)
CAT_OTHER = "other"               # anything unrecognized

# extension (lowercase, no dot) -> (fmt, category, rag_eligible)
_EXT_MAP: dict[str, tuple[str, str, bool]] = {}


def _register(category: str, rag_eligible: bool, exts: dict[str, str]) -> None:
    for ext, fmt in exts.items():
        _EXT_MAP[ext] = (fmt, category, rag_eligible)


# Reflowable text ebooks — the core of the trusted-nonfiction RAG.
_register(CAT_EBOOK_TEXT, True, {
    "epub": "epub",
    "mobi": "mobi",
    "azw": "azw", "azw3": "azw3", "azw4": "azw4",
    "kfx": "kfx",
    "prc": "prc", "pdb": "pdb",
    "fb2": "fb2", "fbz": "fb2",
    "lit": "lit",
    "lrf": "lrf",
    "tcr": "tcr", "pml": "pml", "rb": "rb", "snb": "snb",
    "html": "html", "htm": "html", "htmlz": "htmlz", "xhtml": "html",
    "txt": "txt", "text": "txt",
    "rtf": "rtf",
    "doc": "doc", "docx": "docx", "odt": "odt",
    "md": "md", "markdown": "md",
})

# PDFs — extractable text in most trade nonfiction, but scanned/OCR cases
# exist; eligibility is provisionally True and confirmed in a later phase.
_register(CAT_PDF, True, {"pdf": "pdf"})

# DjVu — typically scanned; treat as image-ish, not RAG-eligible as-is.
_register(CAT_EBOOK_IMAGE, False, {"djvu": "djvu", "djv": "djvu"})

# Comic / image archives.
_register(CAT_EBOOK_IMAGE, False, {
    "cbz": "cbz", "cbr": "cbr", "cb7": "cb7", "cbt": "cbt", "cba": "cba",
})

# Audiobooks.
_register(CAT_AUDIO, False, {
    "mp3": "mp3", "m4a": "m4a", "m4b": "m4b", "aac": "aac",
    "flac": "flac", "ogg": "ogg", "oga": "ogg", "opus": "opus",
    "wav": "wav", "wma": "wma",
    "aa": "aa", "aax": "aax",
})

# Sidecar / metadata files commonly found in Calibre libraries.
_register(CAT_METADATA, False, {
    "opf": "opf", "jpg": "jpg", "jpeg": "jpg", "png": "png", "gif": "gif",
    "nfo": "nfo", "json": "json", "xml": "xml", "cue": "cue",
})


@dataclass(frozen=True)
class FormatInfo:
    fmt: str
    category: str
    rag_eligible: bool


_UNKNOWN = FormatInfo(fmt="unknown", category=CAT_OTHER, rag_eligible=False)


def classify(filename: str) -> FormatInfo:
    """Classify a filename by its extension. Never raises."""
    dot = filename.rfind(".")
    if dot <= 0 or dot == len(filename) - 1:
        return _UNKNOWN
    ext = filename[dot + 1:].lower()
    hit = _EXT_MAP.get(ext)
    if hit is None:
        return _UNKNOWN
    fmt, category, rag_eligible = hit
    return FormatInfo(fmt=fmt, category=category, rag_eligible=rag_eligible)
