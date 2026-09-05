"""Conservative WeChat DOM to Markdown conversion."""

from __future__ import annotations

import re
from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

from .dom import Node, render_safe_html
from .utils import normalize_for_comparison


BLOCK_TAGS = frozenset({
    "address", "article", "aside", "div", "figure", "figcaption", "footer",
    "header", "main", "p", "section",
})


def _visible_fragment(value: str) -> str:
    return re.sub(r"[\t\r\n ]+", " ", value)


def _escape_text(value: str) -> str:
    value = value.replace("\\", "\\\\")
    for character in ("`", "*", "_", "[", "]", "<", ">", "#"):
        value = value.replace(character, f"\\{character}")
    value = re.sub(r"(^|\n)([ \t]*)([-+>])(?=\s)", r"\1\2\\\3", value)
    value = re.sub(r"(^|\n)([ \t]*\d+)\.(?=\s)", r"\1\2\\.", value)
    return value


def _safe_link(href: str) -> str | None:
    href = href.strip()
    if not href:
        return None
    if href.startswith("//"):
        href = f"https:{href}"
    try:
        parsed = urlsplit(href)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https", "mailto"}:
        return None
    if parsed.hostname == "mp.weixin.qq.com":
        query = parse_qs(parsed.query)
        for key in ("url", "target"):
            candidate = query.get(key, [None])[0]
            if candidate:
                try:
                    target = urlsplit(candidate)
                except ValueError:
                    continue
                if target.scheme.lower() in {"http", "https"} and target.hostname:
                    return candidate
    return href


class MarkdownConverter:
    def __init__(self, image_resolver: Callable[[Node], str] | None = None) -> None:
        self.image_resolver = image_resolver or (lambda node: _default_image_source(node))
        self._seen_text: list[str] = []
        self._protected: dict[str, str] = {}
        self._suppress_recording = 0

    def convert(self, root: Node) -> tuple[str, str, bool]:
        self._seen_text = []
        self._protected = {}
        self._suppress_recording = 0
        markdown = self._render_children(root)
        markdown = self._normalize_blocks(markdown)
        for token, value in self._protected.items():
            markdown = markdown.replace(token, value)
        source_text = root.text_content()
        visible_text = "".join(self._seen_text)
        verified = normalize_for_comparison(source_text) == normalize_for_comparison(visible_text)
        return markdown.strip() + "\n", visible_text, verified

    def _remember(self, value: str) -> None:
        if self._suppress_recording == 0:
            self._seen_text.append(value)

    def _render_children(self, node: Node) -> str:
        return "".join(self._render(child) for child in node.children)

    def _render(self, child: str | Node) -> str:
        if isinstance(child, str):
            value = _visible_fragment(child)
            self._remember(value)
            return _escape_text(value)

        tag = child.tag
        if tag in {"strong", "b"}:
            return f"**{self._render_children(child).strip()}**"
        if tag in {"em", "i"}:
            return f"*{self._render_children(child).strip()}*"
        if tag in {"s", "del", "strike"}:
            return f"~~{self._render_children(child).strip()}~~"
        if tag in {f"h{level}" for level in range(1, 7)}:
            level = int(tag[1])
            return f"\n\n{'#' * level} {self._render_children(child).strip()}\n\n"
        if tag == "blockquote":
            value = self._render_children(child).strip()
            return "\n\n" + "\n".join(f"> {line}" if line else ">" for line in value.splitlines()) + "\n\n"
        if tag in {"ul", "ol"}:
            return self._render_list(child, ordered=tag == "ol")
        if tag == "li":
            return self._render_children(child)
        if tag == "table":
            return self._render_table(child)
        if tag == "pre":
            return self._render_pre(child)
        if tag == "code":
            value = child.text_content()
            self._remember(value)
            longest = max((len(run) for run in re.findall(r"`+", value)), default=0)
            delimiter = "`" * max(1, longest + 1)
            pad = " " if value.startswith("`") or value.endswith("`") else ""
            return f"{delimiter}{pad}{value}{pad}{delimiter}"
        if tag == "a":
            label = self._render_children(child).strip()
            href = _safe_link(child.attrs.get("href", ""))
            return f"[{label}]({href.replace(')', '%29')})" if href and label else label
        if tag == "img":
            source = self.image_resolver(child)
            alt = _escape_text(child.attrs.get("alt", ""))
            return f"\n\n![{alt}]({source.replace(')', '%29')})\n\n" if source else ""
        if tag == "br":
            return "  \n"
        if tag == "hr":
            return "\n\n---\n\n"
        if tag in BLOCK_TAGS:
            value = self._render_children(child).strip()
            return f"\n\n{value}\n\n" if value else ""
        return self._render_children(child)

    def _render_list(self, node: Node, *, ordered: bool) -> str:
        lines: list[str] = []
        index = 1
        for child in node.children:
            if not isinstance(child, Node) or child.tag != "li":
                if isinstance(child, str) and child.strip():
                    self._remember(_visible_fragment(child))
                continue
            value = self._render_children(child).strip()
            prefix = f"{index}. " if ordered else "- "
            rendered_lines = value.splitlines() or [""]
            lines.append(prefix + rendered_lines[0])
            lines.extend("   " + line for line in rendered_lines[1:])
            index += 1
        return "\n\n" + "\n".join(lines) + "\n\n"

    def _render_pre(self, node: Node) -> str:
        code_node = next(
            (item for item in node.children if isinstance(item, Node) and item.tag == "code"),
            None,
        )
        text = code_node.text_content() if code_node else node.text_content()
        self._remember(text)
        attrs = {**node.attrs, **(code_node.attrs if code_node else {})}
        language = "text"
        for class_name in attrs.get("class", "").split():
            if class_name.startswith("language-"):
                candidate = class_name.removeprefix("language-")
                if re.fullmatch(r"[A-Za-z0-9_+-]+", candidate):
                    language = candidate
                    break
        candidate = attrs.get("data-language", "")
        if candidate and re.fullmatch(r"[A-Za-z0-9_+-]+", candidate):
            language = candidate
        longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
        fence = "`" * max(3, longest + 1)
        block = f"\n\n{fence}{language}\n{text}\n{fence}\n\n"
        return self._protect(block)

    def _render_table(self, node: Node) -> str:
        if _table_is_complex(node):
            self._remember(node.text_content())
            return self._protect(
                f"\n\n{render_safe_html(node, image_resolver=self.image_resolver)}\n\n"
            )

        self._remember(node.text_content())
        rows: list[list[str]] = []
        self._suppress_recording += 1
        try:
            for row in node.find_all("tr"):
                cells = [item for item in row.children if isinstance(item, Node) and item.tag in {"th", "td"}]
                if not cells:
                    continue
                rendered_cells = []
                for cell in cells:
                    value = self._render_children(cell).strip()
                    value = re.sub(r"\s*\n\s*", "<br>", value).replace("|", "\\|")
                    rendered_cells.append(value)
                rows.append(rendered_cells)
        finally:
            self._suppress_recording -= 1
        if not rows:
            return ""
        width = max(len(row) for row in rows)
        rows = [row + [""] * (width - len(row)) for row in rows]
        lines = [
            "| " + " | ".join(rows[0]) + " |",
            "| " + " | ".join("---" for _ in range(width)) + " |",
            *("| " + " | ".join(row) + " |" for row in rows[1:]),
        ]
        return "\n\n" + "\n".join(lines) + "\n\n"

    def _protect(self, value: str) -> str:
        token = f"\n\nWECHATMDPROTECTED{len(self._protected)}TOKEN\n\n"
        self._protected[token.strip()] = value.strip("\n")
        return token

    @staticmethod
    def _normalize_blocks(markdown: str) -> str:
        markdown = re.sub(r"[ \t]+\n", "\n", markdown)
        markdown = re.sub(r"\n{3,}", "\n\n", markdown)
        return markdown


def _default_image_source(node: Node) -> str:
    for attribute in ("data-src", "data-original", "src", "data-backup-src"):
        value = node.attrs.get(attribute, "").strip()
        if value:
            return f"https:{value}" if value.startswith("//") else value
    return ""


def _table_is_complex(table: Node) -> bool:
    for node in table.walk():
        if node is not table and node.tag == "table":
            return True
        if node.tag in {"td", "th"}:
            for attribute in ("rowspan", "colspan"):
                value = node.attrs.get(attribute, "")
                if value and value != "1":
                    return True
    return False
