"""Convert office/PDF bytes to Markdown via firecrawl/anydoc."""

from __future__ import annotations

import logging

import anydoc

logger = logging.getLogger(__name__)

OFFICE_EXT = {
    ".pdf",
    ".doc",
    ".docx",
    ".docm",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".odt",
    ".ods",
    ".odp",
    ".rtf",
    ".epub",
    ".csv",
}


def is_anydoc_candidate(filename: str, content_type: str | None = None) -> bool:
    name = filename.lower()
    if any(name.endswith(ext) for ext in OFFICE_EXT):
        return True
    if content_type:
        ct = content_type.lower()
        if "pdf" in ct or "officedocument" in ct or "msword" in ct or "spreadsheet" in ct:
            return True
    return False


def bytes_to_markdown(data: bytes, filename: str | None = None) -> str:
    """Return Markdown or raise anydoc.ConvertError / UnsupportedError."""
    fmt = anydoc.format_from_bytes(data)
    if fmt is None and filename:
        fmt = anydoc.format_from_path(filename)
    if fmt is None:
        raise anydoc.UnsupportedError("unrecognized file content for anydoc")
    # to_markdown_bytes accepts optional format name as second arg for csv etc.
    try:
        return anydoc.to_markdown_bytes(data, fmt)
    except TypeError:
        return anydoc.to_markdown_bytes(data)
