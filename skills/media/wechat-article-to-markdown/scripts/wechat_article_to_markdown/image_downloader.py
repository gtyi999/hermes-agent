"""MIME-checked, bounded, content-deduplicated WeChat image downloads."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .dom import Node
from .errors import ConversionError
from .fetcher import SafeFetcher
from .security import IMAGE_HOSTS


MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
}
IMAGE_SOURCE_ATTRIBUTES = ("data-src", "data-original", "src", "data-backup-src")


def image_source(node: Node) -> str | None:
    for attribute in IMAGE_SOURCE_ATTRIBUTES:
        value = node.attrs.get(attribute, "").strip()
        if value:
            return f"https:{value}" if value.startswith("//") else value
    return None


class ImageDownloader:
    def __init__(self, assets_dir: Path, fetcher: SafeFetcher) -> None:
        self.assets_dir = assets_dir
        self.fetcher = fetcher
        self._hash_paths: dict[str, Path] = {}
        self._next_index = 1
        self.warnings: list[str] = []

    def resolve(self, node: Node) -> str:
        source = image_source(node) or ""
        if not source:
            self.warnings.append("Image had no usable src/data-src attribute")
            return ""
        try:
            resource = self.fetcher.fetch(
                source,
                allowed_hosts=IMAGE_HOSTS,
                max_bytes=self.fetcher.limits.max_image_bytes,
            )
            extension = detect_image_extension(resource.body, resource.content_type)
            if extension is None:
                raise ValueError(f"Unsupported image MIME type: {resource.content_type}")
            digest = hashlib.sha256(resource.body).hexdigest()
            if digest in self._hash_paths:
                return self._relative(self._hash_paths[digest])

            self.assets_dir.mkdir(parents=True, exist_ok=True)
            path = self._next_available_path(extension)
            path.write_bytes(resource.body)
            self._hash_paths[digest] = path
            return self._relative(path)
        except (ConversionError, OSError, ValueError) as exc:
            self.warnings.append(f"Image kept remote ({source}): {exc}")
            return source

    def _next_available_path(self, extension: str) -> Path:
        while True:
            path = self.assets_dir / f"image_{self._next_index:03d}{extension}"
            self._next_index += 1
            if not path.exists():
                return path

    def _relative(self, path: Path) -> str:
        return f"assets/{path.name}"


def detect_image_extension(body: bytes, declared_type: str) -> str | None:
    """Return an extension only when bytes match a supported raster format."""
    detected: str | None = None
    if body.startswith(b"\xff\xd8\xff"):
        detected = ".jpg"
    elif body.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = ".png"
    elif body.startswith((b"GIF87a", b"GIF89a")):
        detected = ".gif"
    elif len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        detected = ".webp"
    elif len(body) >= 12 and body[4:8] == b"ftyp" and body[8:12] in {b"avif", b"avis"}:
        detected = ".avif"

    declared = MIME_EXTENSIONS.get(declared_type.lower())
    if detected is None:
        return None
    if declared is not None and declared != detected:
        return None
    return detected
