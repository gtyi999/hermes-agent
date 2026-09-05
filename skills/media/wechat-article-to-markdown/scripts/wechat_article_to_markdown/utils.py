"""Small deterministic helpers for filenames, text, and front matter."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path


_INVALID_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"[\t\r\n ]+", " ", value).strip()
    return cleaned or None


def normalize_for_comparison(value: str) -> str:
    """Ignore HTML layout whitespace while preserving all visible characters."""
    return re.sub(r"\s+", " ", value).strip()


def sanitize_filename(title: str | None, *, max_length: int = 120) -> str:
    value = unicodedata.normalize("NFKC", title or "article")
    value = _INVALID_FILENAME.sub("_", value)
    value = re.sub(r"\s+", "_", value).strip(" ._")
    value = value.replace("..", "_")
    value = value[:max_length].rstrip(" ._") or "article"
    if value.upper() in _WINDOWS_RESERVED:
        value = f"_{value}"
    return value


def unique_markdown_path(output_dir: Path, title: str | None) -> Path:
    stem = sanitize_filename(title)
    candidate = output_dir / f"{stem}.md"
    index = 2
    while candidate.exists():
        candidate = output_dir / f"{stem}_{index}.md"
        index += 1
    return candidate


def yaml_string(value: str | None) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def front_matter(
    *,
    title: str | None,
    author: str | None,
    account: str | None,
    publish_time: str | None,
    source: str,
    mode: str,
) -> str:
    return "\n".join([
        "---",
        f"title: {yaml_string(title)}",
        f"author: {yaml_string(author)}",
        f"account: {yaml_string(account)}",
        f"publish_time: {yaml_string(publish_time)}",
        f"source: {yaml_string(source)}",
        f"content_mode: {yaml_string(mode)}",
        "---",
    ])
