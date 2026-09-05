from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = PROJECT_ROOT / "skills" / "research" / "a-share-innovative-drug-leaders-feishu"
FETCH_SCRIPT = SKILL_ROOT / "scripts" / "fetch_innovative_drug_leaders.py"
SETUP_SCRIPT = SKILL_ROOT / "scripts" / "setup_daily_innovative_drug_leaders.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_normalizes_integer_and_decimal_quote_fields():
    mod = load_module(FETCH_SCRIPT, "innovative_drug_leaders_normalization_test")
    row = mod.normalize_constituent(
        {
            "f12": "600276",
            "f13": 1,
            "f14": "恒瑞医药",
            "f2": 4596,
            "f3": 86,
            "f4": 39,
            "f5": 502917,
            "f6": 2_300_358_125,
            "f8": 79,
            "f9": 3416,
            "f10": 78,
            "f20": 305_045_706_209,
            "f21": 293_178_944_513,
            "f62": 27_130_912,
            "f124": 1788423093,
            "f184": 118,
        }
    )

    assert row["market_label"] == "SH"
    assert row["last_price"] == 45.96
    assert row["change_pct"] == 0.86
    assert row["change_amount"] == 0.39
    assert row["turnover_rate"] == 0.79
    assert row["pe_dynamic"] == 34.16
    assert row["volume_ratio"] == 0.78
    assert row["main_net_inflow_text"] == "2713.09万"
    assert row["quote_date"] == "2026-09-03"

    h5_row = mod.normalize_constituent(
        {"f12": "600276", "f13": 1, "f14": "恒瑞医药", "f2": 45.96, "f3": 0.86}
    )
    assert h5_row["last_price"] == 45.96
    assert h5_row["change_pct"] == 0.86


def test_report_keeps_latest_trade_date_and_ranks_five(monkeypatch):
    mod = load_module(FETCH_SCRIPT, "innovative_drug_leaders_report_test")
    board = {"keyword": "创新药", "code": "BK1106", "name": "创新药", "quote_id": "90.BK1106"}
    latest_ts = 1788423093
    stale_ts = 1788336693
    rows = [
        {"code": "603259", "name": "药明康德", "last_price": 156.63, "total_market_value": 4700, "turnover": 46, "main_net_inflow": 3, "change_pct": 0.4, "quote_timestamp": latest_ts, "quote_date": "2026-09-03"},
        {"code": "688235", "name": "百济神州", "last_price": 269.08, "total_market_value": 4100, "turnover": 8, "main_net_inflow": -1, "change_pct": 0.3, "quote_timestamp": latest_ts, "quote_date": "2026-09-03"},
        {"code": "600276", "name": "恒瑞医药", "last_price": 45.96, "total_market_value": 3000, "turnover": 23, "main_net_inflow": 2, "change_pct": 0.8, "quote_timestamp": latest_ts, "quote_date": "2026-09-03"},
        {"code": "688506", "name": "百利天恒", "last_price": 265.3, "total_market_value": 1000, "turnover": 4, "main_net_inflow": -2, "change_pct": 4.6, "quote_timestamp": latest_ts, "quote_date": "2026-09-03"},
        {"code": "002653", "name": "海思科", "last_price": 68.01, "total_market_value": 700, "turnover": 3, "main_net_inflow": 1, "change_pct": 1.8, "quote_timestamp": latest_ts, "quote_date": "2026-09-03"},
        {"code": "300558", "name": "贝达药业", "last_price": 99.0, "total_market_value": 600, "turnover": 5, "main_net_inflow": 4, "change_pct": 5.0, "quote_timestamp": latest_ts, "quote_date": "2026-09-03"},
        {"code": "000001", "name": "停牌旧行情", "last_price": 1.0, "total_market_value": 9999, "turnover": 99, "main_net_inflow": 99, "change_pct": 9, "quote_timestamp": stale_ts, "quote_date": "2026-09-02"},
    ]

    monkeypatch.setattr(mod, "search_board_code", lambda spec: board)
    monkeypatch.setattr(mod, "fetch_board_constituents", lambda code: rows)
    report = mod.build_report(5, mod.parse_board_spec())

    assert report["trade_date"] == "2026-09-03"
    assert report["board"]["code"] == "BK1106"
    assert report["board"]["constituent_count"] == 7
    assert report["current_trading_day_quote_count"] == 6
    assert report["stale_quote_count"] == 1
    assert [item["code"] for item in report["items"]] == [
        "603259",
        "688235",
        "600276",
        "688506",
        "002653",
    ]
    assert all(item["concept"] == "创新药" for item in report["items"])


def test_setup_contract_uses_requested_schedule_and_runtime_names():
    mod = load_module(SETUP_SCRIPT, "innovative_drug_leaders_setup_test")

    assert mod.DEFAULT_SCHEDULE == "18 23 * * *"
    assert mod.SKILL_NAME == "a-share-innovative-drug-leaders-feishu"
    assert mod.RUNTIME_FETCH_SCRIPT == "a_share_innovative_drug_leaders.py"
    assert "创新药概念龙头股行情" in mod.CRON_PROMPT
    assert "不要调用 send_message" in mod.CRON_PROMPT
