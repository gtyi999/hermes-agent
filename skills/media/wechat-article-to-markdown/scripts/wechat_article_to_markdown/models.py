"""Data models shared by the converter modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class HttpLimits:
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    retries: int = 2
    max_redirects: int = 5
    max_html_bytes: int = 10 * 1024 * 1024
    max_image_bytes: int = 20 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.connect_timeout <= 0 or self.read_timeout <= 0:
            raise ValueError("Timeouts must be positive")
        if self.retries < 0 or self.max_redirects < 0:
            raise ValueError("Retry and redirect limits cannot be negative")
        if self.max_html_bytes <= 0 or self.max_image_bytes <= 0:
            raise ValueError("Response size limits must be positive")


@dataclass
class ArticleMetadata:
    title: str | None = None
    author: str | None = None
    account: str | None = None
    publish_time: str | None = None


@dataclass
class FetchedResource:
    body: bytes
    final_url: str
    content_type: str
    status: int = 200


@dataclass
class ArticleConversionResult:
    success: bool
    source_url: str
    mode: str
    title: str | None = None
    author: str | None = None
    account: str | None = None
    publish_time: str | None = None
    markdown_file: str | None = None
    assets_dir: str | None = None
    integrity_verified: bool = False
    image_warnings: list[str] = field(default_factory=list)
    error: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def failed(
        cls,
        *,
        source_url: str,
        mode: str,
        error: str,
        message: str,
    ) -> "ArticleConversionResult":
        return cls(
            success=False,
            source_url=source_url,
            mode=mode,
            error=error,
            error_message=message,
        )


@dataclass
class RenderedArticle:
    markdown: str
    visible_text: str
    integrity_verified: bool
    image_warnings: list[str] = field(default_factory=list)
    assets_dir: Path | None = None
