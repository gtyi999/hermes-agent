"""Minimal dependency-free HTML tree used by the skill."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from typing import TypeAlias
from urllib.parse import urlsplit


VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Child"] = field(default_factory=list)

    def text_content(self) -> str:
        return "".join(
            child if isinstance(child, str) else child.text_content()
            for child in self.children
        )

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def has_class(self, class_name: str) -> bool:
        return class_name in self.attrs.get("class", "").split()

    def find_first(self, *, tag: str | None = None, node_id: str | None = None, class_name: str | None = None):
        for node in self.walk():
            if tag is not None and node.tag != tag:
                continue
            if node_id is not None and node.attrs.get("id") != node_id:
                continue
            if class_name is not None and not node.has_class(class_name):
                continue
            return node
        return None

    def find_all(self, tag: str | None = None) -> list["Node"]:
        return [node for node in self.walk() if tag is None or node.tag == tag]


Child: TypeAlias = str | Node


class TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag.lower(), {key.lower(): value or "" for key, value in attrs})
        self._stack[-1].children.append(node)
        if node.tag not in VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        wanted = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == wanted:
                del self._stack[index:]
                break

    def handle_data(self, data: str) -> None:
        self._stack[-1].children.append(data)


def parse_html(html: str) -> Node:
    parser = TreeBuilder()
    parser.feed(html)
    parser.close()
    return parser.root


def render_safe_html(node: Node, image_resolver=None) -> str:  # noqa: ANN001
    """Serialize a sanitized subtree, retaining only structural attributes."""
    safe_attrs: dict[str, str] = {}
    for key in ("rowspan", "colspan"):
        if node.attrs.get(key):
            safe_attrs[key] = node.attrs[key]
    if node.tag == "a" and _safe_embedded_url(node.attrs.get("href", "")):
        safe_attrs["href"] = node.attrs["href"]
    if node.tag == "img":
        source = image_resolver(node) if image_resolver else _image_source(node)
        if _safe_embedded_url(source):
            safe_attrs["src"] = source
        if node.attrs.get("alt"):
            safe_attrs["alt"] = node.attrs["alt"]
    attrs = "".join(
        f' {key}="{escape(value, quote=True)}"'
        for key, value in safe_attrs.items()
    )
    if node.tag in VOID_TAGS:
        return f"<{node.tag}{attrs}>"
    inner = "".join(
        escape(child, quote=False)
        if isinstance(child, str)
        else render_safe_html(child, image_resolver=image_resolver)
        for child in node.children
    )
    return f"<{node.tag}{attrs}>{inner}</{node.tag}>"


def _image_source(node: Node) -> str:
    for key in ("data-src", "data-original", "src", "data-backup-src"):
        value = node.attrs.get(key, "").strip()
        if value:
            return f"https:{value}" if value.startswith("//") else value
    return ""


def _safe_embedded_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if not parsed.scheme and not parsed.netloc:
        return bool(parsed.path) and not parsed.path.startswith(("/", "\\")) and ".." not in parsed.path.split("/")
    return parsed.scheme.lower() in {"http", "https", "mailto"} and bool(
        parsed.hostname or parsed.scheme.lower() == "mailto"
    )
