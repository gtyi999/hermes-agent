#!/usr/bin/env python3
"""Fetch this week's publicly visible 富盈公馆 second-hand transactions.

The script emits JSON for Hermes cron. Fang's desktop transaction page can
require an interactive slider, so the fetch path is direct-first with a
read-only rendering fallback. Market snapshots remain explicitly separate
from transaction records, and missing prices are never estimated.
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import re
import shutil
import subprocess
import time
import urllib.request
import zlib
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from statistics import mean
from typing import Any, Iterable


COMMUNITY_NAME = "富盈公馆"
COMMUNITY_LOCATION = "广东省东莞市中堂镇"
COMMUNITY_ADDRESS = "东莞市中堂镇北王西路东侧（江南农批斜对面）"
FANG_PROJECT_ID = "2819973108"
LEYOUJIA_COMMUNITY_ID = "822642"

FANG_DEALS_URL = f"https://dg.esf.fang.com/loupan/{FANG_PROJECT_ID}/chengjiao/"
FANG_DEALS_READER_URL = f"https://r.jina.ai/{FANG_DEALS_URL}"
FANG_WEEKLY_URL = f"https://m.fang.com/xiaoqu/weekreport/dg/{FANG_PROJECT_ID}.html"
LEYOUJIA_URL = f"https://wap.leyoujia.com/dongguan/xq/detail/{LEYOUJIA_COMMUNITY_ID}.html"

SHANGHAI_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


class VisibleTextParser(HTMLParser):
    """Collect visible text while ignoring script and style blocks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.parts.append(text)


def visible_text(raw_html: str) -> str:
    parser = VisibleTextParser()
    parser.feed(raw_html)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def _decode_response(raw: bytes, *, charset: str, content_encoding: str) -> str:
    encoding = content_encoding.lower().strip()
    if encoding == "gzip":
        raw = gzip.decompress(raw)
    elif encoding == "deflate":
        raw = zlib.decompress(raw)
    return raw.decode(charset or "utf-8", errors="replace")


def _validate_response(text: str, expected: Iterable[str]) -> str:
    if not text.strip():
        raise RuntimeError("empty response")
    missing = [marker for marker in expected if marker not in text]
    if missing:
        prefix = re.sub(r"\s+", " ", visible_text(text) or text)[:120]
        raise RuntimeError(f"response missing {missing!r}: {prefix!r}")
    return text


def fetch_text(
    url: str,
    *,
    expected: Iterable[str] = (),
    timeout: int = 20,
    retries: int = 2,
    referer: str | None = None,
) -> str:
    """Fetch text with stdlib first and curl as a transport fallback."""

    markers = tuple(expected)
    last_error: Exception | None = None
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "close",
    }
    if referer:
        headers["Referer"] = referer

    for attempt in range(max(1, retries)):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                text = _decode_response(
                    raw,
                    charset=charset,
                    content_encoding=response.headers.get("Content-Encoding", ""),
                )
            return _validate_response(text, markers)
        except Exception as exc:  # noqa: BLE001 - diagnostics are returned in cron JSON
            last_error = exc
            time.sleep(0.25 * (attempt + 1))

    curl = shutil.which("curl")
    if curl:
        command = [
            curl,
            "--compressed",
            "-L",
            "-sS",
            "--max-time",
            str(timeout),
            "-A",
            USER_AGENT,
            "-H",
            "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
        ]
        if referer:
            command.extend(["-e", referer])
        command.append(url)
        try:
            result = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=timeout + 5,
                check=False,
            )
            if result.returncode == 0:
                return _validate_response(result.stdout, markers)
            detail = result.stderr.strip() or f"exit code {result.returncode}"
            last_error = RuntimeError(f"curl failed: {detail}")
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    raise RuntimeError(f"failed to fetch {url}: {last_error}") from last_error


def _cell_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _number(value: str) -> float | None:
    match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
    return float(match.group(0)) if match else None


def _normalize_deal(cells: list[str]) -> dict[str, Any] | None:
    if len(cells) < 5 or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", cells[1].strip()):
        return None
    try:
        deal_date = date.fromisoformat(cells[1].strip())
    except ValueError:
        return None

    area = _number(cells[0])
    total_price = None if "暂无" in cells[2] or "--" in cells[2] else _number(cells[2])
    unit_price = None if "暂无" in cells[3] or "--" in cells[3] else _number(cells[3])
    if area is None:
        return None

    return {
        "deal_date": deal_date.isoformat(),
        "area_sqm": round(area, 2),
        "total_price_wan": round(total_price, 2) if total_price is not None else None,
        "unit_price_yuan_sqm": round(unit_price, 2) if unit_price is not None else None,
        "information_source": cells[4].strip() or None,
        "source_url": FANG_DEALS_URL,
    }


def parse_deal_rows(text: str) -> list[dict[str, Any]]:
    """Parse Fang's HTML table or the reader fallback's Markdown table."""

    candidates: list[list[str]] = []
    for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", text, flags=re.I | re.S):
        cells = [
            _cell_text(cell)
            for cell in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row_html, flags=re.I | re.S)
        ]
        if cells:
            candidates.append(cells)

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.count("|") < 6:
            continue
        cells = [re.sub(r"\s+", " ", part).strip() for part in stripped.strip("|").split("|")]
        candidates.append(cells)

    deals: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for cells in candidates:
        deal = _normalize_deal(cells)
        if not deal:
            continue
        key = (
            deal["deal_date"],
            deal["area_sqm"],
            deal["total_price_wan"],
            deal["unit_price_yuan_sqm"],
        )
        if key in seen:
            continue
        seen.add(key)
        deals.append(deal)

    return sorted(deals, key=lambda item: (item["deal_date"], item["area_sqm"]), reverse=True)


def fetch_deal_records(*, timeout: int, retries: int) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    warnings: list[str] = []
    transport = "direct"
    try:
        text = fetch_text(
            FANG_DEALS_URL,
            expected=("房源面积", "成交时间", COMMUNITY_NAME),
            timeout=timeout,
            retries=retries,
            referer=f"https://dg.esf.fang.com/loupan/{FANG_PROJECT_ID}.htm",
        )
    except Exception as direct_error:  # noqa: BLE001
        transport = "reader_fallback"
        warnings.append(f"房天下成交页直连不可用，已使用只读转换回退：{direct_error}")
        text = fetch_text(
            FANG_DEALS_READER_URL,
            expected=("房源面积", "成交时间", COMMUNITY_NAME),
            timeout=max(timeout, 30),
            retries=retries,
            referer=FANG_DEALS_URL,
        )

    deals = parse_deal_rows(text)
    if not deals:
        raise RuntimeError("Fang transaction table was fetched but contained no parseable records")
    source = {
        "name": "房天下富盈公馆成交记录",
        "url": FANG_DEALS_URL,
        "transport": transport,
        "visible_record_count": len(deals),
        "latest_record_date": deals[0]["deal_date"],
    }
    return deals, source, warnings


def _signed_change(direction: str, value: str) -> float:
    number = float(value)
    if direction == "下跌":
        return -number
    if direction == "持平":
        return 0.0
    return number


def parse_fang_market_snapshot(raw_html: str) -> dict[str, Any]:
    text = visible_text(raw_html)
    snapshot: dict[str, Any] = {"source_url": FANG_WEEKLY_URL}

    period_match = re.search(r"(\d{2}月\d{2}日\s*-\s*\d{2}月\d{2}日)", text)
    if period_match:
        snapshot["reported_period"] = period_match.group(1).replace(" ", "")

    avg_match = re.search(rf"{COMMUNITY_NAME}.*?(\d+(?:\.\d+)?)\s*元/平\s*本周挂牌均价", text)
    if avg_match:
        snapshot["community_listing_avg_yuan_sqm"] = float(avg_match.group(1))

    change_match = re.search(r"本小区均价环比上周(上涨|下跌|持平)(\d+(?:\.\d+)?)%", text)
    if change_match:
        snapshot["community_listing_week_change_pct"] = _signed_change(
            change_match.group(1), change_match.group(2)
        )

    heat_match = re.search(r"(?:^|\s)(低|中|高)\s*交易热度", text)
    if heat_match:
        snapshot["transaction_heat"] = heat_match.group(1)

    listing_match = re.search(r"小区总在售房源：约(\d+)套", text)
    if listing_match:
        snapshot["active_listing_count"] = int(listing_match.group(1))

    rank_match = re.search(r"本小区均价在商圈内排名第?(\d+)（共(\d+)个挂牌小区）", text)
    if rank_match:
        snapshot["community_rank"] = int(rank_match.group(1))
        snapshot["ranked_community_count"] = int(rank_match.group(2))

    town_match = re.search(
        r"所在商圈：中堂.*?(\d+(?:\.\d+)?)\s*元/平\s*本周挂牌均价\s*"
        r"环比上周\s*([+-]?\d+(?:\.\d+)?)%.*?"
        r"(\d+(?:\.\d+)?)\s*元/平\s*本周成交均价\s*"
        r"环比上周\s*([+-]?\d+(?:\.\d+)?)%",
        text,
    )
    if town_match:
        snapshot["zhongtang_listing_avg_yuan_sqm"] = float(town_match.group(1))
        snapshot["zhongtang_listing_week_change_pct"] = float(town_match.group(2))
        snapshot["zhongtang_deal_avg_yuan_sqm"] = float(town_match.group(3))
        snapshot["zhongtang_deal_week_change_pct"] = float(town_match.group(4))

    if len(snapshot) == 1:
        raise RuntimeError("Fang weekly page contained no parseable market snapshot")
    return snapshot


def fetch_fang_market_snapshot(*, timeout: int, retries: int) -> dict[str, Any]:
    raw_html = fetch_text(
        FANG_WEEKLY_URL,
        expected=(COMMUNITY_NAME, "本周挂牌均价", "交易热度"),
        timeout=timeout,
        retries=retries,
        referer=f"https://m.fang.com/xiaoqu/dg/{FANG_PROJECT_ID}.html",
    )
    return parse_fang_market_snapshot(raw_html)


def parse_leyoujia_snapshot(raw_html: str) -> dict[str, Any]:
    snapshot: dict[str, Any] = {"source_url": LEYOUJIA_URL}
    avg_match = re.search(r'class="card-money">\s*(\d+(?:\.\d+)?)', raw_html)
    if avg_match:
        snapshot["listing_avg_yuan_sqm"] = float(avg_match.group(1))

    for label, key in (("在售房源", "active_listing_count"), ("历史成交", "historical_deal_count")):
        match = re.search(
            rf'class="sell-num">\s*(\d+)(?:(?!class="sell-num").)*?'
            rf'class="sell-type">\s*{label}',
            raw_html,
            flags=re.S,
        )
        if match:
            snapshot[key] = int(match.group(1))

    if len(snapshot) == 1:
        raise RuntimeError("LeYouJia community page contained no parseable snapshot")
    return snapshot


def fetch_leyoujia_snapshot(*, timeout: int, retries: int) -> dict[str, Any]:
    raw_html = fetch_text(
        LEYOUJIA_URL,
        expected=(COMMUNITY_NAME, "在售房源", "历史成交"),
        timeout=timeout,
        retries=retries,
    )
    return parse_leyoujia_snapshot(raw_html)


def parse_now(value: str | None = None) -> datetime:
    if not value:
        return datetime.now(SHANGHAI_TZ)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI_TZ)
    return parsed.astimezone(SHANGHAI_TZ)


def week_window(now: datetime) -> tuple[datetime, datetime]:
    local_now = now.astimezone(SHANGHAI_TZ)
    start = (local_now - timedelta(days=local_now.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return start, start + timedelta(days=7)


def summarize_deals(deals: list[dict[str, Any]]) -> dict[str, Any]:
    areas = [float(item["area_sqm"]) for item in deals if item.get("area_sqm") is not None]
    totals = [float(item["total_price_wan"]) for item in deals if item.get("total_price_wan") is not None]
    unit_prices = [
        float(item["unit_price_yuan_sqm"])
        for item in deals
        if item.get("unit_price_yuan_sqm") is not None
    ]
    return {
        "deal_count": len(deals),
        "total_area_sqm": round(sum(areas), 2) if areas else None,
        "average_area_sqm": round(mean(areas), 2) if areas else None,
        "known_total_price_count": len(totals),
        "total_price_wan_sum": round(sum(totals), 2) if totals else None,
        "average_total_price_wan": round(mean(totals), 2) if totals else None,
        "known_unit_price_count": len(unit_prices),
        "average_unit_price_yuan_sqm": round(mean(unit_prices), 2) if unit_prices else None,
        "min_unit_price_yuan_sqm": round(min(unit_prices), 2) if unit_prices else None,
        "max_unit_price_yuan_sqm": round(max(unit_prices), 2) if unit_prices else None,
    }


def build_digest(args: argparse.Namespace) -> dict[str, Any]:
    now = parse_now(args.now)
    week_start, week_end = week_window(now)
    errors: list[str] = []
    warnings: list[str] = []
    all_deals: list[dict[str, Any]] = []
    transaction_source: dict[str, Any] = {
        "name": "房天下富盈公馆成交记录",
        "url": FANG_DEALS_URL,
        "available": False,
    }

    try:
        all_deals, transaction_source, fetch_warnings = fetch_deal_records(
            timeout=args.timeout,
            retries=args.retries,
        )
        transaction_source["available"] = True
        warnings.extend(fetch_warnings)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"成交记录抓取失败：{exc}")

    market_snapshot = None
    try:
        market_snapshot = fetch_fang_market_snapshot(timeout=args.timeout, retries=args.retries)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"房天下行情周报抓取失败：{exc}")

    leyoujia_snapshot = None
    try:
        leyoujia_snapshot = fetch_leyoujia_snapshot(timeout=args.timeout, retries=args.retries)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"乐有家交叉参考抓取失败：{exc}")

    weekly_deals = [
        item
        for item in all_deals
        if week_start.date() <= date.fromisoformat(item["deal_date"]) < week_end.date()
        and date.fromisoformat(item["deal_date"]) <= now.date()
    ]
    weekly_deals.sort(key=lambda item: (item["deal_date"], item["area_sqm"]), reverse=True)

    count: int | None = len(weekly_deals) if transaction_source.get("available") else None
    return {
        "success": transaction_source.get("available", False),
        "report_type": "fuying_gongguan_weekly_second_hand_deals",
        "community": {
            "name": COMMUNITY_NAME,
            "location": COMMUNITY_LOCATION,
            "address": COMMUNITY_ADDRESS,
            "fang_project_id": FANG_PROJECT_ID,
            "leyoujia_community_id": LEYOUJIA_COMMUNITY_ID,
        },
        "timezone": "Asia/Shanghai",
        "generated_at": now.isoformat(),
        "week_start": week_start.isoformat(),
        "week_end_exclusive": week_end.isoformat(),
        "filter_end": now.isoformat(),
        "weekly_deal_count": count,
        "weekly_deals": weekly_deals,
        "weekly_statistics": summarize_deals(weekly_deals) if count is not None else None,
        "latest_visible_deals": all_deals[: args.latest_limit],
        "transaction_source": transaction_source,
        "market_snapshot": market_snapshot,
        "leyoujia_snapshot": leyoujia_snapshot,
        "warnings": warnings,
        "errors": errors,
        "caveats": [
            "成交明细来自公开房产平台，不是东莞住建局即时网签明细，可能存在延迟、遗漏或后续修订。",
            "weekly_deal_count 为 0 只表示本次抓取未发现本周新增公开记录，不等于官方确认零成交。",
            "总价或单价缺失时保持 null，不进行反推或估算。",
            "行情均价、挂牌量和交易热度仅作市场参考，不应视为真实成交价或投资建议。",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch weekly 富盈公馆 second-hand transaction records.")
    parser.add_argument("--now", help="Override current time with an ISO-8601 value for reproducible runs.")
    parser.add_argument("--timeout", type=int, default=20, help="Per-request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Number of stdlib fetch attempts per source.")
    parser.add_argument("--latest-limit", type=int, default=5, help="Recent records to include as context.")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_digest(args)
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=None if args.compact else 2,
            separators=(",", ":") if args.compact else None,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
