"""Remove executable, hidden, and standard WeChat UI nodes from article DOM."""

from __future__ import annotations

import re

from .dom import Node


DROP_TAGS = frozenset({
    "script", "style", "noscript", "template", "form", "button", "input",
    "textarea", "select", "option", "iframe",
})
DROP_IDS = frozenset({
    "js_article_comment", "js_cmt_area", "js_pc_qr_code", "js_read_area",
    "js_like_area", "js_share_appmsg",
})
DROP_CLASS_PARTS = frozenset({
    "rich_media_tool", "rich_media_extra", "reward_area", "comment_area",
    "article_ad", "js_ad_link", "share_notice", "weui-wa-hotarea",
})
HIDDEN_STYLE = re.compile(r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", re.I)


def clean_content(node: Node) -> Node:
    node.attrs = {
        key: value
        for key, value in node.attrs.items()
        if not key.startswith("on") and key not in {"srcdoc"}
    }
    cleaned: list[str | Node] = []
    for child in node.children:
        if isinstance(child, str):
            cleaned.append(child)
            continue
        classes = set(child.attrs.get("class", "").split())
        hidden = (
            child.tag in DROP_TAGS
            or child.attrs.get("id") in DROP_IDS
            or bool(classes & DROP_CLASS_PARTS)
            or "hidden" in child.attrs
            or child.attrs.get("aria-hidden", "").lower() == "true"
            or bool(HIDDEN_STYLE.search(child.attrs.get("style", "")))
        )
        if hidden:
            continue
        clean_content(child)
        if child.tag not in {"br", "hr", "img"} and not child.children:
            continue
        cleaned.append(child)
    node.children = cleaned
    return node
