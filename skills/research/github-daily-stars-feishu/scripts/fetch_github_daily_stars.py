#!/usr/bin/env python3
"""Fetch GitHub repositories with the most stars gained yesterday.

The ranking source is GH Archive WatchEvent records. Metadata is enriched via
the GitHub REST API. The script uses only the Python standard library so it can
run inside Hermes cron without extra package installation.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from typing import Any, Callable, Iterable

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.8+ includes zoneinfo
    ZoneInfo = None  # type: ignore[assignment]


USER_AGENT = "HermesAgentGitHubDailyStars/1.0 (+https://github.com/gtyi999/hermes-agent)"
RUNTIME_SOURCE = "GH Archive WatchEvent data plus GitHub REST API metadata"
DEFAULT_LIMIT = 10
DEFAULT_CANDIDATES = 20
MAX_FETCH_WORKERS = 8
UTC = timezone.utc


def default_timezone_name() -> str:
    return os.getenv("HERMES_TIMEZONE") or os.getenv("TZ") or "Asia/Shanghai"


def resolve_timezone(name: str):
    if not name:
        name = "Asia/Shanghai"
    if name.upper() in {"UTC", "Z"}:
        return UTC
    if ZoneInfo is None:
        if name in {"Asia/Shanghai", "Asia/Chongqing", "Asia/Harbin"}:
            return timezone(timedelta(hours=8), name)
        raise ValueError("named timezones require Python zoneinfo support")
    try:
        return ZoneInfo(name)
    except Exception as exc:  # noqa: BLE001 - argparse reports the message
        raise ValueError(f"unknown timezone: {name}") from exc


def target_day_window(day_text: str | None = None, timezone_name: str | None = None) -> tuple[datetime, datetime]:
    tz_name = timezone_name or default_timezone_name()
    tz = resolve_timezone(tz_name)
    if day_text:
        target_day = date.fromisoformat(day_text)
    else:
        target_day = datetime.now(tz).date() - timedelta(days=1)
    start = datetime.combine(target_day, datetime_time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end


def iter_utc_hours(start_local: datetime, end_local: datetime) -> Iterable[datetime]:
    current = start_local.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    end_utc = end_local.astimezone(UTC)
    while current < end_utc:
        yield current
        current += timedelta(hours=1)


def gharchive_url(hour_utc: datetime) -> str:
    hour = hour_utc.astimezone(UTC)
    return f"https://data.gharchive.org/{hour:%Y-%m-%d}-{hour.hour}.json.gz"


def parse_event_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def count_watch_events_from_lines(
    lines: Iterable[bytes | str],
    start_utc: datetime,
    end_utc: datetime,
) -> tuple[Counter[str], int]:
    counts: Counter[str] = Counter()
    malformed = 0
    for raw_line in lines:
        if isinstance(raw_line, bytes):
            line = raw_line.decode("utf-8", errors="replace")
        else:
            line = raw_line
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if event.get("type") != "WatchEvent":
            continue
        payload = event.get("payload") or {}
        if payload.get("action") not in (None, "started"):
            continue
        created_at = parse_event_time(event.get("created_at"))
        if created_at is None or created_at < start_utc or created_at >= end_utc:
            continue
        repo = event.get("repo") or {}
        repo_name = str(repo.get("name") or "").strip()
        if "/" not in repo_name:
            continue
        counts[repo_name] += 1
    return counts, malformed


def fetch_hour_counts(
    hour_utc: datetime,
    start_utc: datetime,
    end_utc: datetime,
    *,
    timeout: int = 45,
    retries: int = 2,
) -> tuple[Counter[str], list[str]]:
    url = gharchive_url(hour_utc)
    headers = {"User-Agent": USER_AGENT}
    errors: list[str] = []
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                with gzip.GzipFile(fileobj=response) as gz:
                    counts, malformed = count_watch_events_from_lines(gz, start_utc, end_utc)
            if malformed:
                errors.append(f"{url}: ignored {malformed} malformed line(s)")
            return counts, errors
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return Counter(), [f"{url}: not available yet (404)"]
            errors.append(f"{url}: HTTP {exc.code}")
        except Exception as exc:  # noqa: BLE001 - returned as crawler diagnostics
            errors.append(f"{url}: {exc}")
        if attempt < retries:
            time.sleep(0.5 * (attempt + 1))
    return Counter(), errors


def github_api_headers() -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_json_url(url: str, *, headers: dict[str, str] | None = None, timeout: int = 15, retries: int = 2) -> dict[str, Any]:
    last_error: Exception | None = None
    request_headers = headers or {"User-Agent": USER_AGENT}
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return json.loads(response.read().decode(charset, errors="replace"))
        except Exception as exc:  # noqa: BLE001 - caller returns diagnostics
            last_error = exc
            if attempt < retries:
                time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_error}") from last_error


def repo_api_url(repo_full_name: str) -> str:
    owner, repo = repo_full_name.split("/", 1)
    return (
        "https://api.github.com/repos/"
        f"{urllib.parse.quote(owner, safe='')}/"
        f"{urllib.parse.quote(repo, safe='')}"
    )


def truncate_text(value: Any, limit: int = 280) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def fallback_repo_item(repo_full_name: str, stars_yesterday: int, rank: int, error: str | None = None) -> dict[str, Any]:
    item = {
        "rank": rank,
        "repo": repo_full_name,
        "repo_url": f"https://github.com/{repo_full_name}",
        "stars_yesterday": stars_yesterday,
        "total_stars": None,
        "language": None,
        "description": "",
        "metadata_source": "gharchive_only",
    }
    if error:
        item["metadata_error"] = error
    return item


def enrich_repo(repo_full_name: str, stars_yesterday: int, rank: int, *, timeout: int = 15) -> dict[str, Any]:
    try:
        payload = fetch_json_url(repo_api_url(repo_full_name), headers=github_api_headers(), timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - keep the ranking even if enrichment fails
        return fallback_repo_item(repo_full_name, stars_yesterday, rank, str(exc))

    license_payload = payload.get("license") or {}
    return {
        "rank": rank,
        "repo": repo_full_name,
        "repo_url": payload.get("html_url") or f"https://github.com/{repo_full_name}",
        "stars_yesterday": stars_yesterday,
        "total_stars": payload.get("stargazers_count"),
        "forks": payload.get("forks_count"),
        "open_issues": payload.get("open_issues_count"),
        "language": payload.get("language"),
        "description": truncate_text(payload.get("description")),
        "homepage": payload.get("homepage") or None,
        "topics": (payload.get("topics") or [])[:10],
        "license": license_payload.get("spdx_id") or license_payload.get("name"),
        "owner": (payload.get("owner") or {}).get("login"),
        "created_at": payload.get("created_at"),
        "pushed_at": payload.get("pushed_at"),
        "archived": payload.get("archived"),
        "fork": payload.get("fork"),
        "metadata_source": "github_rest_api",
    }


def collect_star_counts(
    hours: list[datetime],
    start_utc: datetime,
    end_utc: datetime,
    workers: int,
    fetch_hour_counts_fn: Callable[[datetime, datetime, datetime], tuple[Counter[str], list[str]]] = fetch_hour_counts,
) -> tuple[Counter[str], list[str]]:
    total: Counter[str] = Counter()
    errors: list[str] = []
    if workers <= 1 or len(hours) <= 1:
        for hour in hours:
            counts, hour_errors = fetch_hour_counts_fn(hour, start_utc, end_utc)
            total.update(counts)
            errors.extend(hour_errors)
        return total, errors

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, MAX_FETCH_WORKERS, len(hours))) as executor:
        future_by_hour = {
            executor.submit(fetch_hour_counts_fn, hour, start_utc, end_utc): hour
            for hour in hours
        }
        for future in concurrent.futures.as_completed(future_by_hour):
            hour = future_by_hour[future]
            try:
                counts, hour_errors = future.result()
                total.update(counts)
                errors.extend(hour_errors)
            except Exception as exc:  # noqa: BLE001 - returned as crawler diagnostics
                errors.append(f"{gharchive_url(hour)}: {exc}")
    return total, errors


def build_report(
    limit: int,
    *,
    day: str | None = None,
    timezone_name: str | None = None,
    candidates: int = DEFAULT_CANDIDATES,
    workers: int = MAX_FETCH_WORKERS,
    fetch_hour_counts_fn: Callable[[datetime, datetime, datetime], tuple[Counter[str], list[str]]] = fetch_hour_counts,
    enrich_repo_fn: Callable[[str, int, int], dict[str, Any]] = enrich_repo,
) -> dict[str, Any]:
    tz_name = timezone_name or default_timezone_name()
    start_local, end_local = target_day_window(day, tz_name)
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)
    hours = list(iter_utc_hours(start_local, end_local))

    star_counts, errors = collect_star_counts(hours, start_utc, end_utc, workers, fetch_hour_counts_fn)
    candidate_count = max(candidates, limit)
    top_counts = star_counts.most_common(candidate_count)

    items = []
    for rank, (repo, stars_yesterday) in enumerate(top_counts[:limit], start=1):
        items.append(enrich_repo_fn(repo, stars_yesterday, rank))

    fetched_at = datetime.now(resolve_timezone(tz_name)).isoformat()
    warnings = []
    if errors:
        warnings.append("Partial data: one or more GH Archive hourly files or metadata requests failed.")
    if not items:
        warnings.append("No repositories were ranked from the fetched WatchEvent data.")
    if not (os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")):
        warnings.append("GITHUB_TOKEN/GH_TOKEN is not set; GitHub REST API metadata uses the anonymous rate limit.")

    return {
        "fetched_at": fetched_at,
        "source": RUNTIME_SOURCE,
        "target_date": start_local.date().isoformat(),
        "timezone": tz_name,
        "window": {
            "local_start": start_local.isoformat(),
            "local_end": end_local.isoformat(),
            "utc_start": start_utc.isoformat(),
            "utc_end": end_utc.isoformat(),
        },
        "ranking_rule": "Count GitHub WatchEvent records per repository during the target local-date window, descending.",
        "gharchive_hours": [gharchive_url(hour) for hour in hours],
        "hour_count": len(hours),
        "total_watch_events": sum(star_counts.values()),
        "unique_repositories": len(star_counts),
        "limit": limit,
        "candidate_count": candidate_count,
        "partial_data": bool(errors),
        "items": items,
        "warnings": warnings,
        "errors": errors[:30],
        "source_urls": {
            "gharchive": "https://data.gharchive.org/{YYYY-MM-DD-H}.json.gz",
            "github_api": "https://api.github.com/repos/{owner}/{repo}",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch GitHub repositories with the most stars gained yesterday.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--date", help="Target local date in YYYY-MM-DD format. Defaults to yesterday.")
    parser.add_argument("--timezone", default=default_timezone_name(), help="IANA timezone for the target day.")
    parser.add_argument("--candidates", type=int, default=DEFAULT_CANDIDATES, help="How many ranked repos to consider before limiting output.")
    parser.add_argument("--workers", type=int, default=MAX_FETCH_WORKERS, help="Concurrent GH Archive hourly downloads.")
    args = parser.parse_args(argv)

    if args.limit <= 0:
        parser.error("--limit must be positive")
    if args.candidates <= 0:
        parser.error("--candidates must be positive")
    if args.workers <= 0:
        parser.error("--workers must be positive")

    payload = build_report(
        args.limit,
        day=args.date,
        timezone_name=args.timezone,
        candidates=args.candidates,
        workers=args.workers,
    )
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
