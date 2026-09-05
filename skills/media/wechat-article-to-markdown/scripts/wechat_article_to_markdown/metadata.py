"""WeChat metadata and content-root extraction with selector fallbacks."""

from __future__ import annotations

import datetime as dt
import html as html_lib
import re

from .dom import Node
from .errors import ConversionError, ErrorCode
from .models import ArticleMetadata
from .utils import clean_text


def _meta(root: Node, *keys: str) -> str | None:
    wanted = {key.lower() for key in keys}
    for node in root.find_all("meta"):
        key = (node.attrs.get("property") or node.attrs.get("name") or "").lower()
        if key in wanted:
            value = clean_text(node.attrs.get("content"))
            if value:
                return value
    return None


def _node_text(root: Node, *, ids: tuple[str, ...] = (), classes: tuple[str, ...] = (), tags: tuple[str, ...] = ()) -> str | None:
    for node_id in ids:
        node = root.find_first(node_id=node_id)
        value = clean_text(node.text_content()) if node else None
        if value:
            return value
    for class_name in classes:
        node = root.find_first(class_name=class_name)
        value = clean_text(node.text_content()) if node else None
        if value:
            return value
    for tag in tags:
        node = root.find_first(tag=tag)
        value = clean_text(node.text_content()) if node else None
        if value:
            return value
    return None


def _script_value(html: str, *names: str) -> str | None:
    joined = "|".join(re.escape(name) for name in names)
    match = re.search(
        rf"(?:var\s+)?(?:{joined})\s*=\s*(['\"])(.*?)\1",
        html,
        flags=re.DOTALL,
    )
    return clean_text(html_lib.unescape(match.group(2))) if match else None


def _publish_time(root: Node, html: str) -> str | None:
    value = _node_text(root, ids=("publish_time",), classes=("rich_media_meta_text",))
    if value and re.search(r"\d", value):
        return value
    value = _meta(root, "article:published_time", "og:article:published_time")
    if value:
        return value
    match = re.search(r"(?:var\s+)?ct\s*=\s*['\"]?(\d{10})", html)
    if match:
        china_tz = dt.timezone(dt.timedelta(hours=8))
        return dt.datetime.fromtimestamp(int(match.group(1)), tz=china_tz).strftime("%Y-%m-%d %H:%M:%S")
    return _script_value(html, "publish_time")


def extract_metadata(root: Node, html: str) -> ArticleMetadata:
    title = (
        _node_text(root, ids=("activity-name",), classes=("rich_media_title",), tags=("h1",))
        or _meta(root, "og:title", "twitter:title")
        or _script_value(html, "msg_title")
    )
    account = (
        _node_text(root, ids=("js_name",), classes=("profile_nickname",))
        or _script_value(html, "nickname")
    )
    author = (
        _node_text(root, ids=("js_author_name", "author"))
        or _meta(root, "author", "article:author")
        or _script_value(html, "author")
    )
    return ArticleMetadata(
        title=title,
        author=author,
        account=account,
        publish_time=_publish_time(root, html),
    )


def locate_content(root: Node) -> Node:
    for finder in (
        {"node_id": "js_content"},
        {"class_name": "rich_media_content"},
        {"tag": "article"},
    ):
        node = root.find_first(**finder)
        if node and clean_text(node.text_content()):
            return node
    raise ConversionError(
        ErrorCode.ARTICLE_CONTENT_NOT_FOUND,
        "No WeChat article content node was found",
    )
