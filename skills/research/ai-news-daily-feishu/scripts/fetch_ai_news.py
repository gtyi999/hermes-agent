#!/usr/bin/env python3
"""Fetch and rank current AI news for the daily Feishu digest.

This script intentionally uses only the Python standard library so it can run
inside Hermes cron without extra package installation.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import email.utils
import html
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


USER_AGENT = "HermesAgentAIDailyNews/1.0 (+https://github.com/NousResearch/hermes-agent)"
DEFAULT_LIMIT = 10
DEFAULT_WINDOW_HOURS = 36
MAX_FETCH_WORKERS = 10

AI_KEYWORDS = (
    "ai",
    "artificial intelligence",
    "openai",
    "anthropic",
    "claude",
    "chatgpt",
    "gpt",
    "gemini",
    "deepmind",
    "deepseek",
    "llama",
    "llm",
    "large language model",
    "machine learning",
    "neural",
    "nvidia",
    "inference",
    "reasoning model",
    "agent",
    "agents",
    "robotics",
    "diffusion",
)

AI_KEYWORD_RE = re.compile(
    r"(?i)(?:\bai\b|artificial intelligence|openai|anthropic|claude|chatgpt|"
    r"\bgpt[-\w]*\b|gemini|deepmind|deepseek|\bllama\b|\bllm(?:s)?\b|"
    r"large language model|machine learning|neural|nvidia|inference|"
    r"reasoning model|\bagents?\b|robotics|diffusion)"
)

TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "let",
    "lets",
    "new",
    "of",
    "on",
    "or",
    "over",
    "s",
    "the",
    "this",
    "to",
    "via",
    "will",
    "with",
    "wants",
    "your",
}

RSS_FEEDS = (
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", 20.0),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", 19.0),
    ("MIT Technology Review AI", "https://www.technologyreview.com/topic/artificial-intelligence/feed", 18.0),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/", 17.0),
    ("Ars Technica AI", "https://arstechnica.com/ai/feed/", 17.0),
    ("Google News AI", "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": "artificial intelligence OR OpenAI OR Anthropic OR ChatGPT OR DeepSeek when:1d",
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }), 15.0),
)

HN_QUERIES = (
    "artificial intelligence",
    "OpenAI",
    "Anthropic",
    "ChatGPT",
    "DeepSeek",
    "Google Gemini",
    "LLM",
    "Nvidia AI",
)


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published_at: str | None = None
    summary: str = ""
    points: int = 0
    comments: int = 0
    source_weight: float = 0.0
    fetched_from: str = ""
    score: float = 0.0
    sources: set[str] = field(default_factory=set)
    reasons: list[str] = field(default_factory=list)

    def as_dict(self, rank: int, fetched_at: datetime) -> dict[str, Any]:
        published = parse_datetime(self.published_at)
        age_hours = None
        if published:
            age_hours = round(max(0.0, (fetched_at - published).total_seconds() / 3600), 1)
        return {
            "rank": rank,
            "title": self.title,
            "url": self.url,
            "source": ", ".join(sorted(self.sources or {self.source})),
            "published_at": self.published_at,
            "age_hours": age_hours,
            "score": round(self.score, 2),
            "points": self.points or None,
            "comments": self.comments or None,
            "summary": self.summary,
            "reasons": self.reasons[:5],
        }


def fetch_url(url: str, timeout: float = 12.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(text)
        except (TypeError, ValueError, IndexError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso_or_original(value: str | None) -> str | None:
    parsed = parse_datetime(value)
    if parsed:
        return parsed.isoformat()
    return value.strip() if value else None


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(elem: ET.Element, names: tuple[str, ...]) -> str:
    wanted = {name.lower() for name in names}
    for child in list(elem):
        if local_name(child.tag) in wanted and child.text:
            return strip_html(child.text)
    return ""


def link_from_entry(elem: ET.Element) -> str:
    for child in list(elem):
        if local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if href:
            return href.strip()
        if child.text:
            return child.text.strip()
    return ""


def parse_feed(source_name: str, source_weight: float, url: str, xml_text: str) -> list[NewsItem]:
    root = ET.fromstring(xml_text)
    entries = []
    for elem in root.iter():
        name = local_name(elem.tag)
        if name not in {"item", "entry"}:
            continue
        title = child_text(elem, ("title",))
        link = link_from_entry(elem)
        published = child_text(elem, ("pubDate", "published", "updated", "date"))
        summary = child_text(elem, ("description", "summary", "content", "content:encoded"))
        if not title or not link:
            continue
        entries.append(
            NewsItem(
                title=title,
                url=link,
                source=source_name,
                published_at=iso_or_original(published),
                summary=summary[:280],
                source_weight=source_weight,
                fetched_from=url,
                sources={source_name},
            )
        )
    return entries


def hn_search_url(query: str, window_hours: int) -> str:
    created_after = int(time.time() - window_hours * 3600)
    params = {
        "query": query,
        "tags": "story",
        "numericFilters": f"created_at_i>{created_after}",
        "hitsPerPage": "25",
    }
    return "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(params)


def parse_hn(query: str, raw: str) -> list[NewsItem]:
    payload = json.loads(raw)
    items = []
    for hit in payload.get("hits", []):
        title = hit.get("title") or hit.get("story_title") or ""
        url = hit.get("url") or hit.get("story_url")
        object_id = hit.get("objectID")
        if not url and object_id:
            url = f"https://news.ycombinator.com/item?id={object_id}"
        if not title or not url:
            continue
        points = int(hit.get("points") or 0)
        comments = int(hit.get("num_comments") or 0)
        created = hit.get("created_at")
        items.append(
            NewsItem(
                title=strip_html(title),
                url=url,
                source="Hacker News",
                published_at=iso_or_original(created),
                points=points,
                comments=comments,
                source_weight=12.0,
                fetched_from=f"HN query: {query}",
                sources={"Hacker News"},
            )
        )
    return items


def looks_ai_related(item: NewsItem) -> bool:
    haystack = f"{item.title} {item.summary}".lower()
    return bool(AI_KEYWORD_RE.search(haystack))


def keyword_score(item: NewsItem) -> float:
    haystack = f"{item.title} {item.summary}".lower()
    hits = 0
    for keyword in AI_KEYWORDS:
        if keyword in haystack:
            hits += 1
    return min(16.0, hits * 4.0)


def recency_score(item: NewsItem, now: datetime, window_hours: int) -> float:
    published = parse_datetime(item.published_at)
    if not published:
        return 5.0
    age = max(0.0, (now - published).total_seconds() / 3600)
    if age > window_hours * 2:
        return -20.0
    return max(0.0, 28.0 * (1.0 - age / max(window_hours * 2, 1)))


def score_item(item: NewsItem, now: datetime, window_hours: int) -> None:
    hn_popularity = 0.0
    if item.points or item.comments:
        hn_popularity = min(55.0, math.sqrt(max(item.points, 0)) * 5.0 + math.sqrt(max(item.comments, 0)) * 3.0)
    score = item.source_weight + keyword_score(item) + recency_score(item, now, window_hours) + hn_popularity
    item.score = score
    if item.points:
        item.reasons.append(f"{item.points} HN points")
    if item.comments:
        item.reasons.append(f"{item.comments} HN comments")
    if item.published_at:
        item.reasons.append(f"published {item.published_at}")
    if item.source_weight:
        item.reasons.append(f"source weight {item.source_weight:g}")


def canonical_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def canonical_title(title: str) -> str:
    text = html.unescape(title).lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_tokens(title: str) -> set[str]:
    normalized = canonical_title(title)
    return {
        token
        for token in normalized.split()
        if len(token) > 2 and token not in TITLE_STOPWORDS
    }


def same_story(left: NewsItem, right: NewsItem) -> bool:
    left_tokens = title_tokens(left.title)
    right_tokens = title_tokens(right.title)
    if not left_tokens or not right_tokens:
        return False
    overlap = left_tokens & right_tokens
    if len(overlap) >= 5:
        return True
    union = left_tokens | right_tokens
    if len(overlap) >= 4 and len(overlap) / max(len(union), 1) >= 0.36:
        return True

    high_signal = {
        token
        for token in overlap
        if token
        in {
            "openai",
            "chatgpt",
            "anthropic",
            "claude",
            "deepseek",
            "gemini",
            "llama",
            "nvidia",
            "plaid",
            "bank",
            "banks",
            "account",
            "accounts",
            "finance",
            "financial",
        }
    }
    return len(overlap) >= 3 and len(high_signal) >= 2


def merge_items(items: list[NewsItem]) -> list[NewsItem]:
    merged: dict[str, NewsItem] = {}
    canonical_items: list[NewsItem] = []
    for item in items:
        url_key = canonical_url(item.url)
        title_key = canonical_title(item.title)
        key = url_key or title_key
        if not key:
            continue
        existing = merged.get(key) or merged.get(title_key)
        if not existing:
            for candidate in canonical_items:
                if same_story(candidate, item):
                    existing = candidate
                    break
        if not existing:
            merged[key] = item
            if title_key and title_key != key:
                merged[title_key] = item
            canonical_items.append(item)
            continue
        existing.sources.update(item.sources or {item.source})
        existing.points = max(existing.points, item.points)
        existing.comments = max(existing.comments, item.comments)
        if item.score > existing.score:
            existing.title = item.title
            existing.url = item.url
            existing.published_at = item.published_at or existing.published_at
            existing.summary = item.summary or existing.summary
            existing.score = item.score
        existing.score += 6.0
        existing.reasons.append(f"also seen on {item.source}")

    unique = []
    seen = set()
    for item in merged.values():
        marker = id(item)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(item)
    return unique


def collect_items(window_hours: int) -> tuple[list[NewsItem], list[str], dict[str, int]]:
    jobs: list[tuple[str, str, str, float | None]] = []
    for source_name, url, weight in RSS_FEEDS:
        jobs.append(("feed", source_name, url, weight))
    for query in HN_QUERIES:
        jobs.append(("hn", query, hn_search_url(query, window_hours), None))

    errors: list[str] = []
    items: list[NewsItem] = []
    source_counts: dict[str, int] = {}

    def run(job: tuple[str, str, str, float | None]) -> tuple[list[NewsItem], str | None]:
        kind, label, url, weight = job
        try:
            raw = fetch_url(url)
            if kind == "feed":
                parsed = parse_feed(label, float(weight or 0), url, raw)
            else:
                parsed = parse_hn(label, raw)
            return parsed, None
        except Exception as exc:  # noqa: BLE001 - errors are surfaced in output JSON
            return [], f"{label}: {exc}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_FETCH_WORKERS) as pool:
        for parsed, error in pool.map(run, jobs):
            if error:
                errors.append(error)
                continue
            for item in parsed:
                if looks_ai_related(item):
                    items.append(item)
                    source_counts[item.source] = source_counts.get(item.source, 0) + 1

    return items, errors, source_counts


def build_digest(limit: int, window_hours: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    items, errors, source_counts = collect_items(window_hours)
    for item in items:
        score_item(item, now, window_hours)
    ranked = sorted(merge_items(items), key=lambda item: item.score, reverse=True)
    ranked = ranked[:limit]
    return {
        "fetched_at": now.isoformat(),
        "window_hours": window_hours,
        "limit": limit,
        "candidate_count": len(items),
        "source_counts": source_counts,
        "errors": errors[:20],
        "top_items": [item.as_dict(rank, now) for rank, item in enumerate(ranked, start=1)],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch the top AI news for Hermes cron.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--window-hours", type=int, default=DEFAULT_WINDOW_HOURS)
    args = parser.parse_args(argv)

    if args.limit <= 0:
        parser.error("--limit must be positive")
    if args.window_hours <= 0:
        parser.error("--window-hours must be positive")

    payload = build_digest(limit=args.limit, window_hours=args.window_hours)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
