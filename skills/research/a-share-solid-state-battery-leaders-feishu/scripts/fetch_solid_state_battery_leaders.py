#!/usr/bin/env python3
"""Fetch current-trading-day solid-state battery concept leader stocks.

The script uses Eastmoney public quote endpoints and emits JSON for Hermes
cron. It prefers Python stdlib fetching and falls back to curl because some
Eastmoney quote hosts intermittently close Python TLS connections.
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
from typing import Any


USER_AGENT = "Mozilla/5.0 (compatible; HermesAgentSolidBatteryLeaders/1.0)"
REFERER = "https://quote.eastmoney.com/"
H5_REFERER = "https://emdatah5.eastmoney.com/dc/zjlx/block"
QUOTE_TOKEN = "bd1d9ddb04089700cf9c27f6f7426281"
RUNTIME_SOURCE = "Eastmoney public quote and H5 data APIs"
SHANGHAI_TZ = timezone(timedelta(hours=8))

DEFAULT_BOARD = {"keyword": "固态电池", "code": "BK0968", "name": "固态电池"}

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
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                text = response.read().decode(charset, errors="replace")
                if text.strip():
                    return text
        except Exception as exc:  # noqa: BLE001 - fallback below includes diagnostics
            last_error = exc
            time.sleep(0.25 * (attempt + 1))

    curl = shutil.which("curl")
    if curl:
        cmd = [
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
            "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
            "-H",
            "Connection: close",
            url,
        ]
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout + 5)
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
    if value in (None, "-", ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_integer_encoded(value: Any) -> bool:
    if isinstance(value, bool) or value in (None, "-", ""):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, str):
        text = value.strip()
        return bool(re.fullmatch(r"[-+]?\d+", text))
    return False


def scale_quote_price(value: Any) -> float | None:
    number = to_float(value)
    if number is None:
        return None
    if is_integer_encoded(value):
        number = number / 100.0
    return round(number, 4)


def scale_quote_percent(value: Any) -> float | None:
    number = to_float(value)
    if number is None:
        return None
    if is_integer_encoded(value):
        number = number / 100.0
    return round(number, 4)


def money_yuan_text(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return "-"
    abs_number = abs(number)
    if abs_number >= 1e8:
        return f"{number / 1e8:.2f}亿"
    if abs_number >= 1e4:
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
    code_text = str(code or "")
    if str(market) == "1":
        return "SH"
    if code_text.startswith(("4", "8", "9")):
        return "BJ"
    return "SZ"


def timestamp_to_datetime(value: Any) -> datetime | None:
    number = to_float(value)
    if number is None or number <= 0:
        return None
    if number > 10_000_000_000:
        number = number / 1000.0
    try:
        return datetime.fromtimestamp(number, tz=SHANGHAI_TZ)
    except (OSError, OverflowError, ValueError):
        return None


def timestamp_to_iso(value: Any) -> str | None:
    dt = timestamp_to_datetime(value)
    return dt.isoformat() if dt else None


def timestamp_to_date(value: Any) -> str | None:
    dt = timestamp_to_datetime(value)
    return dt.date().isoformat() if dt else None


def parse_board_spec(raw_value: str | None = None) -> dict[str, str]:
    value = (raw_value or os.getenv("A_SHARE_SOLID_STATE_BATTERY_LEADER_CONCEPT", "")).strip()
    if not value:
        return dict(DEFAULT_BOARD)

    parts = [part.strip() for part in value.split(":")]
    spec = {"keyword": parts[0] or DEFAULT_BOARD["keyword"]}
    if len(parts) >= 2 and parts[1]:
        spec["code"] = parts[1]
    if len(parts) >= 3 and parts[2]:
        spec["name"] = parts[2]
    return spec


def search_board_code(spec: dict[str, str]) -> dict[str, str]:
    keyword = spec["keyword"]
    query = urllib.parse.urlencode({"input": keyword, "type": "14", "token": "0", "count": "20"})
    url = f"https://searchapi.eastmoney.com/api/suggest/get?{query}"

    def payload_from_row(row: dict[str, Any]) -> dict[str, str]:
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
        board_rows = [row for row in rows if row.get("Classify") == "BK"]
        for row in board_rows:
            if str(row.get("Name") or "") == keyword:
                return payload_from_row(row)
        for row in board_rows:
            name = str(row.get("Name") or "")
            if keyword in name or name in keyword:
                return payload_from_row(row)
        if board_rows:
            return payload_from_row(board_rows[0])
    except Exception:
        pass

    fallback_code = spec.get("code") or DEFAULT_BOARD["code"]
    fallback_name = spec.get("name") or keyword or DEFAULT_BOARD["name"]
    return {
        "keyword": keyword,
        "code": fallback_code,
        "name": fallback_name,
        "quote_id": f"90.{fallback_code}",
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
    code = str(item.get("f12", ""))
    quote_timestamp = item.get("f124")
    volume_hands = to_float(item.get("f5"))
    return {
        "code": code,
        "market": item.get("f13"),
        "market_label": market_label(item.get("f13"), code),
        "name": str(item.get("f14", "")),
        "last_price": scale_quote_price(item.get("f2")),
        "change_pct": scale_quote_percent(item.get("f3")),
        "change_amount": scale_quote_price(item.get("f4")),
        "volume_hands": volume_hands,
        "volume_shares": volume_hands * 100 if volume_hands is not None else None,
        "volume_hands_text": volume_hands_text(item.get("f5")),
        "turnover": to_float(item.get("f6")),
        "turnover_text": money_yuan_text(item.get("f6")),
        "amplitude_pct": scale_quote_percent(item.get("f7")),
        "turnover_rate": scale_quote_percent(item.get("f8")),
        "pe_dynamic": scale_quote_percent(item.get("f9")),
        "volume_ratio": scale_quote_percent(item.get("f10")),
        "high": scale_quote_price(item.get("f15")),
        "low": scale_quote_price(item.get("f16")),
        "open": scale_quote_price(item.get("f17")),
        "previous_close": scale_quote_price(item.get("f18")),
        "total_market_value": to_float(item.get("f20")),
        "total_market_value_text": money_yuan_text(item.get("f20")),
        "float_market_value": to_float(item.get("f21")),
        "float_market_value_text": money_yuan_text(item.get("f21")),
        "pb": scale_quote_percent(item.get("f23")),
        "change_60d_pct": scale_quote_percent(item.get("f24")),
        "change_ytd_pct": scale_quote_percent(item.get("f25")),
        "main_net_inflow": to_float(item.get("f62")),
        "main_net_inflow_text": money_yuan_text(item.get("f62")),
        "main_net_inflow_pct": scale_quote_percent(item.get("f184")),
        "quote_timestamp": quote_timestamp,
        "quote_time": timestamp_to_iso(quote_timestamp),
        "quote_date": timestamp_to_date(quote_timestamp),
    }


def fetch_board_constituents_from_h5(board_code: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    page_size = 100

    while True:
        payload = fetch_json(h5_clist_url(board_code, page, page_size), timeout=12, retries=3, referer=H5_REFERER)
        data = payload.get("data") or {}
        diff = data.get("diff") or []
        if page == 1 and not diff:
            raise RuntimeError("empty H5 board constituent response")
        total = int(data.get("total") or len(rows) + len(diff))
        for item in diff:
            rows.append(normalize_constituent(item))
        if len(rows) >= total or not diff:
            break
        page += 1
        if page > 20:
            break

    return rows


def fetch_board_constituents_from_quote(board_code: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    page_size = 100

    while True:
        payload = None
        errors = []
        for host in QUOTE_HOSTS:
            url = quote_clist_url(host, board_code, page, page_size)
            try:
                candidate = fetch_json(url, timeout=12, retries=2)
                data = candidate.get("data") or {}
                diff = data.get("diff") or []
                if diff:
                    payload = candidate
                    break
                errors.append(f"{host}: empty diff")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{host}: {exc}")
        if payload is None:
            if page == 1:
                raise RuntimeError("; ".join(errors) or "failed to fetch board constituents")
            break

        data = payload.get("data") or {}
        diff = data.get("diff") or []
        total = int(data.get("total") or len(rows) + len(diff))
        for item in diff:
            rows.append(normalize_constituent(item))
        if len(rows) >= total or not diff:
            break
        page += 1
        if page > 20:
            break

    return rows


def fetch_board_constituents(board_code: str) -> list[dict[str, Any]]:
    errors = []
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
    number = to_float(value)
    return number if number is not None else 0.0


def stock_sort_key(item: dict[str, Any]) -> tuple[float, float, float, float, str]:
    return (
        -sortable_number(item.get("total_market_value")),
        -sortable_number(item.get("turnover")),
        -sortable_number(item.get("main_net_inflow")),
        -sortable_number(item.get("change_pct")),
        str(item.get("code") or ""),
    )


def latest_quote_timestamp(items: list[dict[str, Any]]) -> Any:
    best_value = None
    best_number = 0.0
    for item in items:
        number = to_float(item.get("quote_timestamp"))
        if number is not None and number > best_number:
            best_number = number
            best_value = item.get("quote_timestamp")
    return best_value


def build_report(limit: int, board_spec: dict[str, str]) -> dict[str, Any]:
    board = search_board_code(board_spec)
    errors: list[str] = []
    try:
        constituents = fetch_board_constituents(board["code"])
    except Exception as exc:  # noqa: BLE001
        constituents = []
        errors.append(f"{board.get('name') or board_spec.get('keyword')}: {exc}")

    items: list[dict[str, Any]] = []
    for raw in constituents:
        item = {
            "code": raw.get("code"),
            "name": raw.get("name"),
            "market": raw.get("market"),
            "market_label": raw.get("market_label"),
            "concept": board["name"],
            "last_price": raw.get("last_price"),
            "change_pct": raw.get("change_pct"),
            "change_amount": raw.get("change_amount"),
            "volume_hands": raw.get("volume_hands"),
            "volume_shares": raw.get("volume_shares"),
            "volume_hands_text": raw.get("volume_hands_text"),
            "turnover": raw.get("turnover"),
            "turnover_text": raw.get("turnover_text"),
            "amplitude_pct": raw.get("amplitude_pct"),
            "turnover_rate": raw.get("turnover_rate"),
            "pe_dynamic": raw.get("pe_dynamic"),
            "volume_ratio": raw.get("volume_ratio"),
            "open": raw.get("open"),
            "high": raw.get("high"),
            "low": raw.get("low"),
            "previous_close": raw.get("previous_close"),
            "total_market_value": raw.get("total_market_value"),
            "total_market_value_text": raw.get("total_market_value_text"),
            "float_market_value": raw.get("float_market_value"),
            "float_market_value_text": raw.get("float_market_value_text"),
            "pb": raw.get("pb"),
            "change_60d_pct": raw.get("change_60d_pct"),
            "change_ytd_pct": raw.get("change_ytd_pct"),
            "main_net_inflow": raw.get("main_net_inflow"),
            "main_net_inflow_text": raw.get("main_net_inflow_text"),
            "main_net_inflow_pct": raw.get("main_net_inflow_pct"),
            "quote_timestamp": raw.get("quote_timestamp"),
            "quote_time": raw.get("quote_time"),
            "quote_date": raw.get("quote_date"),
        }
        items.append(item)

    items.sort(key=stock_sort_key)
    top = items[:limit]
    quote_ts = latest_quote_timestamp(items)
    quote_dt = timestamp_to_datetime(quote_ts)
    fetched_at = datetime.now(SHANGHAI_TZ).isoformat()

    warnings = []
    if len(items) < limit:
        warnings.append(f"Only {len(items)} solid-state battery concept stock quote(s) found.")
    if errors:
        warnings.append("Some concept data failed to load: " + "; ".join(errors))

    return {
        "fetched_at": fetched_at,
        "source": RUNTIME_SOURCE,
        "board": {
            "keyword": board["keyword"],
            "code": board["code"],
            "name": board["name"],
            "quote_id": board["quote_id"],
            "constituent_count": len(constituents),
        },
        "errors": errors,
        "trade_date": quote_dt.date().isoformat() if quote_dt else datetime.now(SHANGHAI_TZ).date().isoformat(),
        "quote_time": quote_dt.isoformat() if quote_dt else None,
        "schedule_note": "The report is scheduled for 22:50; trade_date is the latest quote date returned by Eastmoney.",
        "ranked_count": len(items),
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
    parser = argparse.ArgumentParser(description="Fetch A-share solid-state battery concept leader stock quotes.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--concept",
        help=(
            "Concept spec. Format: keyword, keyword:BK0000, or "
            "keyword:BK0000:DisplayName. Defaults to 固态电池:BK0968:固态电池."
        ),
    )
    args = parser.parse_args(argv)

    if args.limit <= 0:
        parser.error("--limit must be positive")

    board_spec = parse_board_spec(args.concept)
    payload = build_report(args.limit, board_spec)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
