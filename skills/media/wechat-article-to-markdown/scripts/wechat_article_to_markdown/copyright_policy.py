"""Copyright-mode selection and a bounded, non-full-text overview."""

from __future__ import annotations

import re

from .dom import Node
from .models import ArticleMetadata
from .utils import clean_text


def conversion_mode(authorized_full_text: bool) -> str:
    return "full_text" if authorized_full_text else "summary"


def build_summary(metadata: ArticleMetadata, content: Node) -> str:
    """Create a structural overview without reproducing the article body."""
    headings: list[str] = []
    paragraphs: list[str] = []
    for node in content.walk():
        value = clean_text(node.text_content())
        if not value:
            continue
        if node.tag in {"h1", "h2", "h3"} and value not in headings:
            headings.append(value[:60])
        elif node.tag == "p" and value not in paragraphs:
            paragraphs.append(value)

    source_text = clean_text(content.text_content()) or ""
    lines = [
        "## 摘要",
        "",
        "> 版权提示：未确认全文转载授权，以下仅提供元信息与有限结构化概览；请通过原文链接阅读完整内容。",
        "",
        f"- 文章主题：{metadata.title or '未识别'}",
        f"- 正文规模：约 {len(source_text)} 个字符，{len(paragraphs)} 个可识别段落",
    ]
    if headings:
        lines.append("- 可识别章节：" + "；".join(headings[:4]))

    quote_budget = min(120, len(source_text) // 10)
    if paragraphs and quote_budget >= 20:
        excerpt = paragraphs[0][:quote_budget]
        if len(paragraphs[0]) > quote_budget:
            excerpt = excerpt.rstrip("，,。.!！？?；; ") + "……"
        excerpt = re.sub(r"\s+", " ", excerpt)
        lines.extend(["", "### 短引用", "", f"> {excerpt}"])
    return "\n".join(lines).strip() + "\n"
