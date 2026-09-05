#!/usr/bin/env python3
"""Fetch latest-trading-day innovative-drug concept leader-stock quotes.

The script uses Eastmoney public quote endpoints and emits JSON for a Hermes
cron prompt. H5 data is preferred; the regular quote API and curl are fallbacks
for intermittent TLS/endpoint failures.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


USER_AGENT = "Mozilla/5.0 (compatible; HermesAgentInnovativeDrugLeaders/1.0)"
REFERER = "https://quote.eastmoney.com/"
H5_REFERER = "https://emdatah5.eastmoney.com/dc/zjlx/block"
QUOTE_TOKEN = "bd1d9ddb04089700cf9c27f6f7426281"
RUNTIME_SOURCE = "Eastmoney public quote and H5 data APIs"
SHANGHAI_TZ = timezone(timedelta(hours=8))

DEFAULT_BOARD = {"keyword": "创新药", "code": "BK1106", "name": "创新药"}
QUOTE_HOSTS = (
    "https://push2.eastmoney.com",
    "https://1.push2.eastmoney.com",
    "https://79.push2.eastmoney.com",
)
QUOTE_FIELDS = (
    "f12,f13,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,f15,f16,f17,f18,"
    "f20,f21,f23,f24,f25,f62,f124,f184"
)


def fetch_text(url: str, *, timeout: int = 12, retries: int = 3, referer: str = REFERER) -> str:
    last_error: Exception | None = None
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "close",
    }
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                text = response.read().decode(charset, errors="replace")
                if text.strip():
                    return text
        except Exception as exc:  # noqa: BLE001 - retained for fallback diagnostics
            last_error = exc
            time.sleep(0.25 * (attempt + 1))

    curl = shutil.which("curl")
    if curl:
        command = [
            curl,
            "-L",
            "-sS",
            "--max-time",
            str(timeout),
            "-A",
            USER_AGENT,
            "-e",
            referer,
            "-H",
            "Accept: application/json, text/plain, */*",
            "-H",
            "Connection: close",
            url,
        ]
        try:
            result = subprocess.run(command, text=True, capture_output=True, timeout=timeout + 5)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"curl timed out for {url}") from exc
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
        if result.stderr.strip():
            raise RuntimeError(f"curl failed for {url}: {result.stderr.strip()}") from last_error

    raise RuntimeError(f"failed to fetch {url}: {last_error}") from last_error


def parse_json_payload(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise ValueError("empty response")
    if stripped.startswith("{"):
        return json.loads(stripped)
    match = re.search(r"\((\{.*\})\)\s*;?\s*$", stripped, re.S)
    if match:
        return json.loads(match.group(1))
    raise ValueError(f"unexpected response prefix: {stripped[:80]!r}")


def fetch_json(url: str, *, timeout: int = 12, retries: int = 3, referer: str = REFERER) -> dict[str, Any]:
    return parse_json_payload(fetch_text(url, timeout=timeout, retries=retries, referer=referer))


def to_float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_integer_encoded(value: Any) -> bool:
    if isinstance(value, bool) or value in (None, "", "-"):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, str) and bool(re.fullmatch(r"[-+]?\d+", value.strip()))


def scale_quote_number(value: Any) -> float | None:
    number = to_float(value)
    if number is None:
        return None
    if is_integer_encoded(value):
        number /= 100.0
    return round(number, 4)


def money_yuan_text(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return "-"
    if abs(number) >= 1e8:
        return f"{number / 1e8:.2f}亿"
    if abs(number) >= 1e4:
        return f"{number / 1e4:.2f}万"
    return f"{number:.0f}"


def volume_hands_text(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return "-"
    if abs(number) >= 1e8:
        return f"{number / 1e8:.2f}亿手"
    if abs(number) >= 1e4:
        return f"{number / 1e4:.2f}万手"
    return f"{number:.0f}手"


def market_label(market: Any, code: Any = None) -> str:
    if str(market) == "1":
        return "SH"
    if str(code or "").startswith(("4", "8", "9")):
        return "BJ"
    return "SZ"


def timestamp_to_datetime(value: Any) -> datetime | None:
    number = to_float(value)
    if number is None or number <= 0:
        return None
    if number > 10_000_000_000:
        number /= 1000.0
    try:
        return datetime.fromtimestamp(number, tz=SHANGHAI_TZ)
    except (OSError, OverflowError, ValueError):
        return None


def timestamp_to_iso(value: Any) -> str | None:
    parsed = timestamp_to_datetime(value)
    return parsed.isoformat() if parsed else None


def timestamp_to_date(value: Any) -> str | None:
    parsed = timestamp_to_datetime(value)
    return parsed.date().isoformat() if parsed else None


def parse_board_spec(raw_value: str | None = None) -> dict[str, str]:
    value = (raw_value or os.getenv("A_SHARE_INNOVATIVE_DRUG_LEADER_CONCEPT", "")).strip()
    if not value:
        return dict(DEFAULT_BOARD)
    parts = [part.strip() for part in value.split(":")]
    result = {"keyword": parts[0] or DEFAULT_BOARD["keyword"]}
    if len(parts) >= 2 and parts[1]:
        result["code"] = parts[1]
    if len(parts) >= 3 and parts[2]:
        result["name"] = parts[2]
    return result


def search_board_code(spec: dict[str, str]) -> dict[str, str]:
    keyword = spec["keyword"]
    query = urllib.parse.urlencode({"input": keyword, "type": "14", "token": "0", "count": "20"})
    url = f"https://searchapi.eastmoney.com/api/suggest/get?{query}"

    def normalized(row: dict[str, Any]) -> dict[str, str]:
        code = str(row.get("Code") or spec.get("code") or DEFAULT_BOARD["code"])
        name = str(row.get("Name") or spec.get("name") or keyword)
        return {
            "keyword": keyword,
            "code": code,
            "name": name,
            "quote_id": str(row.get("QuoteID") or f"90.{code}"),
        }

    try:
        payload = fetch_json(url, timeout=10, retries=2)
        rows = ((payload.get("QuotationCodeTable") or {}).get("Data") or [])
        boards = [row for row in rows if row.get("Classify") == "BK"]
        for row in boards:
            if str(row.get("Name") or "") == keyword:
                return normalized(row)
        for row in boards:
            name = str(row.get("Name") or "")
            if keyword in name or name in keyword:
                return normalized(row)
    except Exception:
        pass

    code = spec.get("code") or DEFAULT_BOARD["code"]
    return {
        "keyword": keyword,
        "code": code,
        "name": spec.get("name") or keyword,
        "quote_id": f"90.{code}",
    }


def quote_clist_url(host: str, board_code: str, page: int, page_size: int = 100) -> str:
    params = {
        "np": "1",
        "fltt": "1",
        "invt": "2",
        "fs": f"b:{board_code}",
        "fields": QUOTE_FIELDS,
        "fid": "f20",
        "pn": str(page),
        "pz": str(page_size),
        "po": "1",
        "ut": QUOTE_TOKEN,
        "dect": "1",
    }
    return f"{host}/api/qt/clist/get?{urllib.parse.urlencode(params)}"


def h5_clist_url(board_code: str, page: int, page_size: int = 100) -> str:
    params = {
        "fields": QUOTE_FIELDS,
        "pn": str(page),
        "pz": str(page_size),
        "fid": "f20",
        "po": "1",
        "fs": f"b:{board_code}",
        "ut": QUOTE_TOKEN,
    }
    return f"https://emdatah5.eastmoney.com/dc/ZJLX/getZDYLBData?{urllib.parse.urlencode(params)}"


def normalize_constituent(item: dict[str, Any]) -> dict[str, Any]:
    code = str(item.get("f12") or "")
    volume_hands = to_float(item.get("f5"))
    quote_timestamp = item.get("f124")
    return {
        "code": code,
        "market": item.get("f13"),
        "market_label": market_label(item.get("f13"), code),
        "name": str(item.get("f14") or ""),
        "last_price": scale_quote_number(item.get("f2")),
        "change_pct": scale_quote_number(item.get("f3")),
        "change_amount": scale_quote_number(item.get("f4")),
        "volume_hands": volume_hands,
        "volume_shares": volume_hands * 100 if volume_hands is not None else None,
        "volume_hands_text": volume_hands_text(item.get("f5")),
        "turnover": to_float(item.get("f6")),
        "turnover_text": money_yuan_text(item.get("f6")),
        "amplitude_pct": scale_quote_number(item.get("f7")),
        "turnover_rate": scale_quote_number(item.get("f8")),
        "pe_dynamic": scale_quote_number(item.get("f9")),
        "volume_ratio": scale_quote_number(item.get("f10")),
        "high": scale_quote_number(item.get("f15")),
        "low": scale_quote_number(item.get("f16")),
        "open": scale_quote_number(item.get("f17")),
        "previous_close": scale_quote_number(item.get("f18")),
        "total_market_value": to_float(item.get("f20")),
        "total_market_value_text": money_yuan_text(item.get("f20")),
        "float_market_value": to_float(item.get("f21")),
        "float_market_value_text": money_yuan_text(item.get("f21")),
        "pb": scale_quote_number(item.get("f23")),
        "change_60d_pct": scale_quote_number(item.get("f24")),
        "change_ytd_pct": scale_quote_number(item.get("f25")),
        "main_net_inflow": to_float(item.get("f62")),
        "main_net_inflow_text": money_yuan_text(item.get("f62")),
        "main_net_inflow_pct": scale_quote_number(item.get("f184")),
        "quote_timestamp": quote_timestamp,
        "quote_time": timestamp_to_iso(quote_timestamp),
        "quote_date": timestamp_to_date(quote_timestamp),
    }


def fetch_paginated(
    board_code: str,
    fetch_page: Callable[[str, int, int], dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_size = 100
    for page in range(1, 21):
        payload = fetch_page(board_code, page, page_size)
        data = payload.get("data") or {}
        diff = data.get("diff") or []
        if page == 1 and not diff:
            raise RuntimeError("empty board constituent response")
        rows.extend(normalize_constituent(item) for item in diff)
        total = int(data.get("total") or len(rows))
        if len(rows) >= total or not diff:
            break
    return rows


def fetch_board_constituents_from_h5(board_code: str) -> list[dict[str, Any]]:
    def fetch_page(code: str, page: int, size: int) -> dict[str, Any]:
        return fetch_json(h5_clist_url(code, page, size), timeout=12, retries=3, referer=H5_REFERER)

    return fetch_paginated(board_code, fetch_page)


def fetch_board_constituents_from_quote(board_code: str) -> list[dict[str, Any]]:
    def fetch_page(code: str, page: int, size: int) -> dict[str, Any]:
        errors: list[str] = []
        for host in QUOTE_HOSTS:
            try:
                payload = fetch_json(quote_clist_url(host, code, page, size), timeout=12, retries=2)
                if ((payload.get("data") or {}).get("diff") or []):
                    return payload
                errors.append(f"{host}: empty diff")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{host}: {exc}")
        raise RuntimeError("; ".join(errors) or "all quote hosts failed")

    return fetch_paginated(board_code, fetch_page)


def fetch_board_constituents(board_code: str) -> list[dict[str, Any]]:
    errors: list[str] = []
    for fetcher in (fetch_board_constituents_from_h5, fetch_board_constituents_from_quote):
        try:
            rows = fetcher(board_code)
            if rows:
                return rows
            errors.append(f"{fetcher.__name__}: empty rows")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{fetcher.__name__}: {exc}")
    raise RuntimeError("failed to fetch board constituents: " + "; ".join(errors))


def sortable_number(value: Any) -> float:
    return to_float(value) or 0.0


def stock_sort_key(item: dict[str, Any]) -> tuple[float, float, float, float, str]:
    return (
        -sortable_number(item.get("total_market_value")),
        -sortable_number(item.get("turnover")),
        -sortable_number(item.get("main_net_inflow")),
        -sortable_number(item.get("change_pct")),
        str(item.get("code") or ""),
    )


def latest_quote_date(items: list[dict[str, Any]]) -> str | None:
    dates = [str(item["quote_date"]) for item in items if item.get("quote_date")]
    return max(dates) if dates else None


def latest_quote_datetime(items: list[dict[str, Any]]) -> datetime | None:
    parsed = [timestamp_to_datetime(item.get("quote_timestamp")) for item in items]
    valid = [item for item in parsed if item is not None]
    return max(valid) if valid else None


def build_report(limit: int, board_spec: dict[str, str]) -> dict[str, Any]:
    fetched_at_dt = datetime.now(SHANGHAI_TZ)
    board = search_board_code(board_spec)
    errors: list[str] = []
    try:
        constituents = fetch_board_constituents(board["code"])
    except Exception as exc:  # noqa: BLE001
        constituents = []
        errors.append(f"{board.get('name') or board_spec.get('keyword')}: {exc}")

    quoted = [row for row in constituents if row.get("code") and row.get("last_price") is not None]
    trade_date = latest_quote_date(quoted)
    if trade_date:
        current_rows = [row for row in quoted if row.get("quote_date") == trade_date]
    else:
        current_rows = quoted

    current_rows.sort(key=stock_sort_key)
    for row in current_rows:
        row["concept"] = board["name"]
    top = current_rows[:limit]
    quote_dt = latest_quote_datetime(current_rows)

    warnings: list[str] = []
    stale_count = max(0, len(quoted) - len(current_rows))
    if stale_count:
        warnings.append(f"Excluded {stale_count} stale quote row(s) older than {trade_date}.")
    if len(current_rows) < limit:
        warnings.append(f"Only {len(current_rows)} current-trading-day quote(s) were available.")
    if trade_date is None and constituents:
        warnings.append("Quote timestamps were unavailable; the trading date could not be verified.")
    elif trade_date != fetched_at_dt.date().isoformat():
        warnings.append(
            f"Latest available quote date is {trade_date}; fetch calendar date is "
            f"{fetched_at_dt.date().isoformat()}."
        )
    if errors:
        warnings.append("Concept data failed to load: " + "; ".join(errors))

    return {
        "fetched_at": fetched_at_dt.isoformat(),
        "fetched_calendar_date": fetched_at_dt.date().isoformat(),
        "source": RUNTIME_SOURCE,
        "board": {
            "keyword": board["keyword"],
            "code": board["code"],
            "name": board["name"],
            "quote_id": board["quote_id"],
            "constituent_count": len(constituents),
        },
        "errors": errors,
        "trade_date": trade_date,
        "quote_time": quote_dt.isoformat() if quote_dt else None,
        "schedule_note": "Daily at 23:18 Asia/Shanghai; trade_date comes from the latest Eastmoney quote timestamp.",
        "current_trading_day_quote_count": len(current_rows),
        "stale_quote_count": stale_count,
        "ranked_count": len(current_rows),
        "limit": limit,
        "ranking_rule": "total_market_value desc, turnover desc, main_net_inflow desc, change_pct desc",
        "items": top,
        "warnings": warnings,
        "source_urls": {
            "board_search": "https://searchapi.eastmoney.com/api/suggest/get",
            "board_constituents_h5": "https://emdatah5.eastmoney.com/dc/ZJLX/getZDYLBData",
            "board_constituents": "https://push2.eastmoney.com/api/qt/clist/get",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch A-share innovative-drug concept leader-stock quotes")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--concept",
        help="Concept spec: keyword, keyword:BK0000, or keyword:BK0000:DisplayName; default 创新药:BK1106:创新药",
    )
    args = parser.parse_args(argv)
    if args.limit <= 0:
        parser.error("--limit must be positive")
    payload = build_report(args.limit, parse_board_spec(args.concept))
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
