"""High-level WeChat article conversion API."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path

from .cleaner import clean_content
from .converter import MarkdownConverter
from .copyright_policy import build_summary, conversion_mode
from .dom import parse_html
from .errors import ConversionError, ErrorCode
from .fetcher import SafeFetcher, decode_html, reject_interstitial
from .image_downloader import ImageDownloader
from .metadata import extract_metadata, locate_content
from .models import ArticleConversionResult, HttpLimits
from .security import ARTICLE_HOSTS, validate_url
from .utils import front_matter, unique_markdown_path


LOGGER = logging.getLogger(__name__)


async def convert_wechat_article(
    url: str,
    output_dir: str = "./output",
    download_images: bool = True,
    authorized_full_text: bool = False,
    *,
    limits: HttpLimits | None = None,
) -> ArticleConversionResult:
    """Fetch a public WeChat article and write a Markdown result."""
    return await asyncio.to_thread(
        _convert_remote,
        url,
        output_dir,
        download_images,
        authorized_full_text,
        limits or HttpLimits(),
    )


def _convert_remote(
    url: str,
    output_dir: str,
    download_images: bool,
    authorized_full_text: bool,
    limits: HttpLimits,
) -> ArticleConversionResult:
    mode = conversion_mode(authorized_full_text)
    try:
        LOGGER.info("Fetching article")
        fetcher = SafeFetcher(limits)
        resource = fetcher.fetch_article(url)
        html = decode_html(resource)
        reject_interstitial(html)
        return convert_wechat_html(
            html,
            source_url=resource.final_url,
            output_dir=output_dir,
            download_images=download_images,
            authorized_full_text=authorized_full_text,
            fetcher=fetcher,
        )
    except ConversionError as exc:
        return ArticleConversionResult.failed(
            source_url=url,
            mode=mode,
            error=exc.code.value,
            message=str(exc),
        )
    except OSError as exc:
        return ArticleConversionResult.failed(
            source_url=url,
            mode=mode,
            error=ErrorCode.OUTPUT_WRITE_FAILED.value,
            message=str(exc),
        )
    except Exception as exc:  # defensive JSON contract for CLI callers
        LOGGER.exception("Unexpected Markdown conversion failure")
        return ArticleConversionResult.failed(
            source_url=url,
            mode=mode,
            error=ErrorCode.MARKDOWN_CONVERSION_FAILED.value,
            message=str(exc),
        )


def convert_wechat_html(
    html: str,
    *,
    source_url: str,
    output_dir: str,
    download_images: bool,
    authorized_full_text: bool,
    fetcher: SafeFetcher | None = None,
) -> ArticleConversionResult:
    """Convert already-fetched HTML; intended for tests and authorized callers."""
    normalized_url = validate_url(source_url, allowed_hosts=ARTICLE_HOSTS, resolve_dns=False)
    mode = conversion_mode(authorized_full_text)
    root = parse_html(html)
    metadata = extract_metadata(root, html)
    LOGGER.info("Article title detected: %s", metadata.title or "<unknown>")
    content = clean_content(locate_content(root))
    LOGGER.info("Content node detected")

    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    assets_dir = destination / "assets"
    image_downloader: ImageDownloader | None = None

    if authorized_full_text:
        if download_images:
            image_downloader = ImageDownloader(assets_dir, fetcher or SafeFetcher())
        converter = MarkdownConverter(image_downloader.resolve if image_downloader else None)
        body, _visible_text, verified = converter.convert(content)
        if not verified:
            raise ConversionError(
                ErrorCode.MARKDOWN_CONVERSION_FAILED,
                "Full-text integrity comparison failed",
            )
        has_same_h1 = False
        for child in content.children:
            if isinstance(child, str) and not child.strip():
                continue
            has_same_h1 = (
                not isinstance(child, str)
                and child.tag == "h1"
                and " ".join(child.text_content().split()) == " ".join((metadata.title or "").split())
            )
            break
        if metadata.title and not has_same_h1:
            body = f"# {metadata.title}\n\n{body}"
        integrity_verified = True
    else:
        body = build_summary(metadata, content)
        integrity_verified = False

    header = front_matter(
        title=metadata.title,
        author=metadata.author,
        account=metadata.account,
        publish_time=metadata.publish_time,
        source=normalized_url,
        mode=mode,
    )
    markdown = f"{header}\n\n{body.rstrip()}\n"
    markdown_path = unique_markdown_path(destination, metadata.title)
    _atomic_write(markdown_path, markdown)
    LOGGER.info("Markdown generated: %s", markdown_path)

    warnings = image_downloader.warnings if image_downloader else []
    return ArticleConversionResult(
        success=True,
        source_url=normalized_url,
        mode=mode,
        title=metadata.title,
        author=metadata.author,
        account=metadata.account,
        publish_time=metadata.publish_time,
        markdown_file=str(markdown_path),
        assets_dir=str(assets_dir) if assets_dir.exists() else None,
        integrity_verified=integrity_verified,
        image_warnings=warnings,
    )


def _atomic_write(path: Path, content: str) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    except OSError:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
