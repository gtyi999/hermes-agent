#!/usr/bin/env python3
"""Fetch previous-trading-day solid-state battery concept limit-up stocks.

The script uses Eastmoney public endpoints and emits JSON for Hermes cron.
It prefers Python stdlib fetching and falls back to curl because some
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


USER_AGENT = "Mozilla/5.0 (compatible; HermesAgentSolidBatteryLimitups/1.0)"
REFERER = "https://quote.eastmoney.com/"
H5_REFERER = "https://emdatah5.eastmoney.com/dc/zjlx/block"
QUOTE_TOKEN = "bd1d9ddb04089700cf9c27f6f7426281"
ZT_POOL_TOKEN = "7eea3edcaed734bea9cbfc24409ed989"
DEFAULT_BOARD_CODE = "BK0968"
DEFAULT_BOARD_NAME = "固态电池"
RUNTIME_SOURCE = "Eastmoney public quote and H5 data APIs"

QUOTE_HOSTS = (
    "https://push2.eastmoney.com",
    "https://1.push2.eastmoney.com",
    "https://79.push2.eastmoney.com",
)


def fetch_text(url: str, *, timeout: int = 12, retries: int = 3, referer: str = REFERER) -> str:
    last_error: Exception | None = None
    headers = {"User-Agent": USER_AGENT, "Referer": referer}

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


def scale_percent(value: Any) -> float | None:
    if value in (None, "-", ""):
        return None
    number = float(value)
    return number / 100.0 if abs(number) > 200 else number


def scale_board_price(value: Any) -> float | None:
    if value in (None, "-", ""):
        return None
    number = float(value)
    return number / 100.0 if abs(number) > 1000 else number


def scale_zt_price(value: Any) -> float | None:
    if value in (None, "-", ""):
        return None
    number = float(value)
    return number / 1000.0 if abs(number) > 1000 else number


def money_yuan_text(value: Any) -> str:
    if value in (None, "-", ""):
        return "-"
    number = float(value)
    abs_number = abs(number)
    if abs_number >= 1e8:
        return f"{number / 1e8:.2f}亿"
    if abs_number >= 1e4:
        return f"{number / 1e4:.2f}万"
    return f"{number:.0f}"


def hhmmss(value: Any) -> str | None:
    if value in (None, "-", "", 0):
        return None
    text = str(int(value)).rjust(6, "0")
    return f"{text[:2]}:{text[2:4]}:{text[4:]}"


def market_label(market: Any) -> str:
    return "SH" if str(market) == "1" else "SZ"


def search_board_code(keyword: str = DEFAULT_BOARD_NAME) -> dict[str, str]:
    query = urllib.parse.urlencode({"input": keyword, "type": "14", "token": "0", "count": "10"})
    url = f"https://searchapi.eastmoney.com/api/suggest/get?{query}"
    try:
        payload = fetch_json(url, timeout=10, retries=2)
        rows = ((payload.get("QuotationCodeTable") or {}).get("Data") or [])
        for row in rows:
            if row.get("Classify") == "BK" and keyword in str(row.get("Name", "")):
                return {
                    "code": str(row.get("Code") or DEFAULT_BOARD_CODE),
                    "name": str(row.get("Name") or keyword),
                    "quote_id": str(row.get("QuoteID") or f"90.{DEFAULT_BOARD_CODE}"),
                }
    except Exception:
        pass
    return {"code": DEFAULT_BOARD_CODE, "name": keyword, "quote_id": f"90.{DEFAULT_BOARD_CODE}"}


def quote_clist_url(host: str, board_code: str, page: int, page_size: int = 100) -> str:
    params = {
        "np": "1",
        "fltt": "1",
        "invt": "2",
        "fs": f"b:{board_code}",
        "fields": "f12,f13,f14,f2,f3,f20,f21,f62",
        "fid": "f3",
        "pn": str(page),
        "pz": str(page_size),
        "po": "1",
        "ut": QUOTE_TOKEN,
        "dect": "1",
    }
    return f"{host}/api/qt/clist/get?{urllib.parse.urlencode(params)}"


def h5_clist_url(board_code: str, page: int, page_size: int = 100) -> str:
    params = {
        "fields": "f12,f13,f14,f2,f3,f20,f21,f62",
        "pn": str(page),
        "pz": str(page_size),
        "fid": "f3",
        "po": "1",
        "fs": f"b:{board_code}",
        "ut": QUOTE_TOKEN,
    }
    return f"https://emdatah5.eastmoney.com/dc/ZJLX/getZDYLBData?{urllib.parse.urlencode(params)}"


def normalize_constituent(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": str(item.get("f12", "")),
        "market": item.get("f13"),
        "market_label": market_label(item.get("f13")),
        "name": str(item.get("f14", "")),
        "last_price": scale_board_price(item.get("f2")),
        "change_pct": scale_percent(item.get("f3")),
        "total_market_value": item.get("f20"),
        "float_market_value": item.get("f21"),
        "main_net_inflow": item.get("f62"),
    }


def fetch_board_constituents_from_h5(board_code: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    page_size = 100
    total = None

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
    total = None

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


def zt_pool_url(date_text: str, page_size: int = 500) -> str:
    params = {
        "ut": ZT_POOL_TOKEN,
        "dpt": "wz.ztzt",
        "Pageindex": "0",
        "pagesize": str(page_size),
        "sort": "fbt:asc",
        "date": date_text,
    }
    return f"https://push2ex.eastmoney.com/getTopicZTPool?{urllib.parse.urlencode(params)}"


def candidate_dates(days_back: int = 10) -> list[str]:
    tz = timezone(timedelta(hours=8))
    today = datetime.now(tz).date()
    return [(today - timedelta(days=offset)).strftime("%Y%m%d") for offset in range(days_back + 1)]


def fetch_latest_limitup_pool() -> dict[str, Any]:
    errors = []
    for date_text in candidate_dates(10):
        try:
            payload = fetch_json(zt_pool_url(date_text), timeout=15, retries=3)
            data = payload.get("data") or {}
            pool = data.get("pool") or []
            qdate = data.get("qdate")
            if qdate and pool:
                return {
                    "requested_date": date_text,
                    "trade_date": str(qdate),
                    "total_limitup_count": data.get("tc"),
                    "pool": pool,
                }
            errors.append(f"{date_text}: empty pool")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{date_text}: {exc}")
    raise RuntimeError("failed to fetch a recent limit-up pool: " + "; ".join(errors[:5]))


def stock_sort_key(item: dict[str, Any]) -> tuple[float, float, int]:
    lbc = float(item.get("consecutive_limitups") or 0)
    fund = float(item.get("sealed_fund") or 0)
    fbt = int(item.get("first_limitup_raw") or 999999)
    return (-lbc, -fund, fbt)


def build_report(limit: int) -> dict[str, Any]:
    board = search_board_code()
    constituents = fetch_board_constituents(board["code"])
    constituent_by_code = {row["code"]: row for row in constituents}
    limit_pool = fetch_latest_limitup_pool()

    matches = []
    for raw in limit_pool["pool"]:
        code = str(raw.get("c", ""))
        board_row = constituent_by_code.get(code)
        if not board_row:
            continue
        zttj = raw.get("zttj") or {}
        item = {
            "code": code,
            "name": str(raw.get("n") or board_row.get("name") or ""),
            "market": raw.get("m"),
            "market_label": market_label(raw.get("m")),
            "concept": board["name"],
            "industry": raw.get("hybk"),
            "price": scale_zt_price(raw.get("p")),
            "limitup_pct": scale_percent(raw.get("zdp")),
            "turnover": raw.get("amount"),
            "turnover_text": money_yuan_text(raw.get("amount")),
            "float_market_value": raw.get("ltsz"),
            "float_market_value_text": money_yuan_text(raw.get("ltsz")),
            "turnover_rate": scale_percent(raw.get("hs")),
            "consecutive_limitups": raw.get("lbc") or 0,
            "first_limitup_time": hhmmss(raw.get("fbt")),
            "last_limitup_time": hhmmss(raw.get("lbt")),
            "first_limitup_raw": raw.get("fbt"),
            "sealed_fund": raw.get("fund"),
            "sealed_fund_text": money_yuan_text(raw.get("fund")),
            "open_count": raw.get("zbc"),
            "limitup_stat": {
                "days": zttj.get("days"),
                "count": zttj.get("ct"),
            },
            "board_change_pct": board_row.get("change_pct"),
            "board_last_price": board_row.get("last_price"),
        }
        matches.append(item)

    matches.sort(key=stock_sort_key)
    top = matches[:limit]
    fetched_at = datetime.now(timezone(timedelta(hours=8))).isoformat()

    return {
        "fetched_at": fetched_at,
        "source": RUNTIME_SOURCE,
        "board": board,
        "trade_date": limit_pool["trade_date"],
        "requested_date": limit_pool["requested_date"],
        "schedule_note": "The pool date is the latest trading date returned by Eastmoney.",
        "total_limitup_count": limit_pool["total_limitup_count"],
        "board_constituent_count": len(constituents),
        "matched_count": len(matches),
        "limit": limit,
        "ranking_rule": "consecutive_limitups desc, sealed_fund desc, first_limitup_time asc",
        "items": top,
        "warnings": (
            [f"Only {len(matches)} matching solid-state battery concept limit-up stock(s) found."]
            if len(matches) < limit
            else []
        ),
        "source_urls": {
            "board_search": "https://searchapi.eastmoney.com/api/suggest/get",
            "board_constituents_h5": "https://emdatah5.eastmoney.com/dc/ZJLX/getZDYLBData?fs=b:BK0968",
            "board_constituents": "https://push2.eastmoney.com/api/qt/clist/get?fs=b:BK0968",
            "limitup_pool": "https://push2ex.eastmoney.com/getTopicZTPool",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch A-share solid-state battery concept limit-up stocks.")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)

    if args.limit <= 0:
        parser.error("--limit must be positive")

    payload = build_report(args.limit)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
