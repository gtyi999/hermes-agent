"""Behavior contracts for the bundled WeChat article Markdown skill."""

from __future__ import annotations

import io
import subprocess
import sys
import urllib.error
from email.message import Message
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "skills" / "media" / "wechat-article-to-markdown"
SCRIPTS_DIR = SKILL_DIR / "scripts"
FIXTURE = Path(__file__).parent / "fixtures" / "wechat_article_sample.html"
sys.path.insert(0, str(SCRIPTS_DIR))

from wechat_article_to_markdown import convert_wechat_html  # noqa: E402
from wechat_article_to_markdown.dom import Node, parse_html  # noqa: E402
from wechat_article_to_markdown.errors import ConversionError, ErrorCode  # noqa: E402
from wechat_article_to_markdown.fetcher import SafeFetcher, reject_interstitial  # noqa: E402
from wechat_article_to_markdown.image_downloader import (  # noqa: E402
    ImageDownloader,
    detect_image_extension,
    image_source,
)
from wechat_article_to_markdown.metadata import extract_metadata, locate_content  # noqa: E402
from wechat_article_to_markdown.models import FetchedResource, HttpLimits  # noqa: E402
from wechat_article_to_markdown.security import ARTICLE_HOSTS, ensure_public_dns, validate_url  # noqa: E402
from wechat_article_to_markdown.utils import sanitize_filename  # noqa: E402


PUBLIC_URL = "https://mp.weixin.qq.com/s/example"


def _sample_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_skill_is_discoverable_and_documents_safe_default():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    ui = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "name: wechat-article-to-markdown" in text
    assert "Default to summary mode" in text
    assert "--authorized-full-text" in text
    assert "$wechat-article-to-markdown" in ui


def test_full_text_conversion_preserves_structures_and_metadata(tmp_path: Path):
    result = convert_wechat_html(
        _sample_html(),
        source_url=PUBLIC_URL,
        output_dir=str(tmp_path),
        download_images=False,
        authorized_full_text=True,
    )

    assert result.success is True
    assert result.mode == "full_text"
    assert result.integrity_verified is True
    assert result.title == "AI 与工程实践"
    assert result.author == "测试作者"
    assert result.account == "测试公众号"
    assert result.publish_time == "2026-08-22 12:00:00"

    markdown = Path(result.markdown_file or "").read_text(encoding="utf-8")
    assert 'content_mode: "full_text"' in markdown
    assert "# AI 与工程实践" in markdown
    assert "## 第一节" in markdown
    assert "**重点***斜体* 😀" in markdown
    assert "> 引用内容" in markdown
    assert "- 无序一" in markdown
    assert "1. 有序一" in markdown
    assert "| 字段 | 说明 |" in markdown
    assert '`x = 1`' in markdown
    assert "```python\nprint(\"hello\")\n```" in markdown
    assert "[链接](https://example.com/a)" in markdown
    assert "![原始说明](https://mmbiz.qpic.cn/preferred.jpg)" in markdown
    assert "隐藏内容" not in markdown
    assert "评论内容" not in markdown
    assert "window.secret" not in markdown


def test_summary_mode_does_not_emit_full_body_or_download_assets(tmp_path: Path):
    distinctive = "这是受版权保护的独特正文，不能在默认模式中完整复制。" * 30
    html = f"""
    <h1 id="activity-name">摘要测试</h1>
    <div id="js_content"><p>{distinctive}</p>
    <img data-src="https://mmbiz.qpic.cn/image.jpg"></div>
    """
    result = convert_wechat_html(
        html,
        source_url=PUBLIC_URL,
        output_dir=str(tmp_path),
        download_images=True,
        authorized_full_text=False,
    )

    markdown = Path(result.markdown_file or "").read_text(encoding="utf-8")
    assert result.mode == "summary"
    assert result.integrity_verified is False
    assert distinctive not in markdown
    assert "未确认全文转载授权" in markdown
    assert 'content_mode: "summary"' in markdown
    assert result.assets_dir is None
    assert not (tmp_path / "assets").exists()


def test_metadata_and_content_have_dom_fallbacks():
    html = """
    <meta property="og:title" content="Fallback 标题">
    <script>var nickname = "Fallback 公众号"; var ct = "1787356800";</script>
    <article><p>正文</p></article>
    """
    root = parse_html(html)
    metadata = extract_metadata(root, html)

    assert metadata.title == "Fallback 标题"
    assert metadata.account == "Fallback 公众号"
    assert metadata.publish_time is not None
    assert locate_content(root).tag == "article"


def test_complex_table_remains_sanitized_html(tmp_path: Path):
    html = """
    <h1 id="activity-name">复杂表格</h1>
    <div id="js_content">
      <table onclick="steal()"><tr><th colspan="2">表头</th></tr>
      <tr><td>A</td><td>B</td></tr></table>
    </div>
    """
    result = convert_wechat_html(
        html,
        source_url=PUBLIC_URL,
        output_dir=str(tmp_path),
        download_images=False,
        authorized_full_text=True,
    )
    markdown = Path(result.markdown_file or "").read_text(encoding="utf-8")

    assert result.integrity_verified is True
    assert '<table><tr><th colspan="2">表头</th></tr>' in markdown
    assert "onclick" not in markdown


def test_existing_main_title_is_not_duplicated(tmp_path: Path):
    html = """
    <meta property="og:title" content="唯一主标题">
    <div id="js_content"><h1>唯一主标题</h1><p>正文。</p></div>
    """
    result = convert_wechat_html(
        html,
        source_url=PUBLIC_URL,
        output_dir=str(tmp_path),
        download_images=False,
        authorized_full_text=True,
    )
    markdown = Path(result.markdown_file or "").read_text(encoding="utf-8")
    body = markdown.split("---", maxsplit=2)[-1]

    assert body.count("# 唯一主标题") == 1


def test_lazy_image_source_priority_and_sha256_deduplication(tmp_path: Path):
    node = Node("img", {
        "src": "https://mmbiz.qpic.cn/src.jpg",
        "data-original": "https://mmbiz.qpic.cn/original.jpg",
        "data-src": "https://mmbiz.qpic.cn/preferred.jpg",
    })
    assert image_source(node) == "https://mmbiz.qpic.cn/preferred.jpg"

    class FakeFetcher:
        limits = HttpLimits()

        def fetch(self, url, **kwargs):  # noqa: ANN001, ANN003
            return FetchedResource(b"\x89PNG\r\n\x1a\n" + b"same-image", url, "image/png")

    downloader = ImageDownloader(tmp_path / "assets", FakeFetcher())  # type: ignore[arg-type]
    first = downloader.resolve(node)
    second = downloader.resolve(Node("img", {"data-src": "https://mmbiz.qpic.cn/other.jpg"}))

    assert first == "assets/image_001.png"
    assert second == first
    assert len(list((tmp_path / "assets").iterdir())) == 1


def test_image_type_comes_from_bytes_and_rejects_header_mismatch():
    png = b"\x89PNG\r\n\x1a\nrest"
    assert detect_image_extension(png, "application/octet-stream") == ".png"
    assert detect_image_extension(png, "image/jpeg") is None
    assert detect_image_extension(b"not-an-image", "image/png") is None


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://mp.weixin.qq.com/s/x", ErrorCode.INVALID_URL),
        ("file:///etc/passwd", ErrorCode.INVALID_URL),
        ("https://127.0.0.1/s/x", ErrorCode.UNSUPPORTED_DOMAIN),
        ("https://mp.weixin.qq.com.evil.invalid/s/x", ErrorCode.UNSUPPORTED_DOMAIN),
        ("https://user:pass@mp.weixin.qq.com/s/x", ErrorCode.INVALID_URL),
        ("https://mp.weixin.qq.com:8443/s/x", ErrorCode.INVALID_URL),
    ],
)
def test_url_validation_rejects_ssrf_shapes(url: str, code: ErrorCode):
    with pytest.raises(ConversionError) as caught:
        validate_url(url, allowed_hosts=ARTICLE_HOSTS, resolve_dns=False)
    assert caught.value.code == code


def test_dns_validation_rejects_private_resolution(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "wechat_article_to_markdown.security.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(ConversionError) as caught:
        ensure_public_dns("mp.weixin.qq.com")
    assert caught.value.code == ErrorCode.INVALID_URL


def test_redirect_target_is_revalidated(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "wechat_article_to_markdown.security.ensure_public_dns",
        lambda host: None,
    )
    headers = Message()
    headers["Location"] = "http://127.0.0.1/private"
    redirect = urllib.error.HTTPError(PUBLIC_URL, 302, "Found", headers, io.BytesIO())

    class FakeOpener:
        def open(self, request, timeout):  # noqa: ANN001
            raise redirect

    fetcher = SafeFetcher(HttpLimits(retries=0))
    fetcher._opener = FakeOpener()  # type: ignore[assignment]
    with pytest.raises(ConversionError) as caught:
        fetcher.fetch_article(PUBLIC_URL)
    assert caught.value.code == ErrorCode.INVALID_URL


def test_declared_oversized_response_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "wechat_article_to_markdown.security.ensure_public_dns",
        lambda host: None,
    )
    headers = Message()
    headers["Content-Type"] = "text/html; charset=utf-8"
    headers["Content-Length"] = "100"

    class FakeResponse:
        status = 200

        def __init__(self):
            self.headers = headers

        def getcode(self):
            return 200

        def read(self, size):  # noqa: ANN001
            return b""

        def close(self):
            pass

    class FakeOpener:
        def open(self, request, timeout):  # noqa: ANN001
            return FakeResponse()

    fetcher = SafeFetcher(HttpLimits(retries=0, max_html_bytes=10))
    fetcher._opener = FakeOpener()  # type: ignore[assignment]
    with pytest.raises(ConversionError) as caught:
        fetcher.fetch_article(PUBLIC_URL)
    assert caught.value.code == ErrorCode.RESPONSE_TOO_LARGE


def test_interstitial_is_not_treated_as_an_article():
    with pytest.raises(ConversionError) as caught:
        reject_interstitial('<html><div id="js_verify">请输入验证码</div></html>')
    assert caught.value.code == ErrorCode.ARTICLE_NOT_PUBLICLY_ACCESSIBLE


def test_filename_sanitization_blocks_path_traversal_and_reserved_names():
    sanitized = sanitize_filename('../../坏:标题?*<>|\\name')
    assert ".." not in sanitized
    assert "/" not in sanitized
    assert "\\" not in sanitized
    assert sanitize_filename("CON") == "_CON"


def test_module_cli_is_runnable():
    completed = subprocess.run(
        [sys.executable, "-m", "wechat_article_to_markdown", "--help"],
        cwd=SCRIPTS_DIR,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "--authorized-full-text" in completed.stdout
