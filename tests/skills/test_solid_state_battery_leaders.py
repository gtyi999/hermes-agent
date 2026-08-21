from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    PROJECT_ROOT
    / "skills"
    / "research"
    / "a-share-solid-state-battery-leaders-feishu"
    / "scripts"
    / "fetch_solid_state_battery_leaders.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("solid_state_battery_leaders_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_normalizes_eastmoney_quote_fields():
    mod = load_module()
    row = mod.normalize_constituent(
        {
            "f12": "300750",
            "f13": 0,
            "f14": "宁德时代",
            "f2": 31250,
            "f3": 125,
            "f4": 386,
            "f5": 248000,
            "f6": 7750000000.0,
            "f8": 91,
            "f9": 2380,
            "f10": 82,
            "f20": 1370000000000,
            "f21": 1200000000000,
            "f62": 345000000.0,
            "f124": 1784100873,
            "f184": 445,
        }
    )

    assert row["market_label"] == "SZ"
    assert row["last_price"] == 312.5
    assert row["change_pct"] == 1.25
    assert row["change_amount"] == 3.86
    assert row["turnover_rate"] == 0.91
    assert row["pe_dynamic"] == 23.8
    assert row["volume_ratio"] == 0.82
    assert row["main_net_inflow_text"] == "3.45亿"
    assert row["quote_date"] == "2026-07-15"

    h5_row = mod.normalize_constituent({"f12": "300750", "f13": 0, "f14": "宁德时代", "f2": 312.5, "f3": 1.25})
    assert h5_row["last_price"] == 312.5
    assert h5_row["change_pct"] == 1.25


def test_build_report_ranks_top_five_by_market_value_and_trading_weight(monkeypatch):
    mod = load_module()
    board = {"keyword": "固态电池", "code": "BK0968", "name": "固态电池", "quote_id": "90.BK0968"}
    rows = [
        {"code": "300750", "name": "宁德时代", "market": 0, "market_label": "SZ", "total_market_value": 1_300, "turnover": 20, "main_net_inflow": 1, "change_pct": 1, "quote_timestamp": 1784100873, "quote_time": "2026-07-15T15:34:33+08:00", "quote_date": "2026-07-15"},
        {"code": "002594", "name": "比亚迪", "market": 0, "market_label": "SZ", "total_market_value": 1_200, "turnover": 25, "main_net_inflow": 2, "change_pct": 2, "quote_timestamp": 1784100873, "quote_time": "2026-07-15T15:34:33+08:00", "quote_date": "2026-07-15"},
        {"code": "601012", "name": "隆基绿能", "market": 1, "market_label": "SH", "total_market_value": 800, "turnover": 30, "main_net_inflow": 3, "change_pct": 3, "quote_timestamp": 1784100873, "quote_time": "2026-07-15T15:34:33+08:00", "quote_date": "2026-07-15"},
        {"code": "002460", "name": "赣锋锂业", "market": 0, "market_label": "SZ", "total_market_value": 700, "turnover": 10, "main_net_inflow": 4, "change_pct": 1, "quote_timestamp": 1784100873, "quote_time": "2026-07-15T15:34:33+08:00", "quote_date": "2026-07-15"},
        {"code": "300014", "name": "亿纬锂能", "market": 0, "market_label": "SZ", "total_market_value": 650, "turnover": 12, "main_net_inflow": 5, "change_pct": 5, "quote_timestamp": 1784100873, "quote_time": "2026-07-15T15:34:33+08:00", "quote_date": "2026-07-15"},
        {"code": "603799", "name": "华友钴业", "market": 1, "market_label": "SH", "total_market_value": 500, "turnover": 8, "main_net_inflow": 6, "change_pct": 4, "quote_timestamp": 1784100873, "quote_time": "2026-07-15T15:34:33+08:00", "quote_date": "2026-07-15"},
    ]

    monkeypatch.setattr(mod, "search_board_code", lambda spec: board)
    monkeypatch.setattr(mod, "fetch_board_constituents", lambda code: rows)

    report = mod.build_report(5, mod.parse_board_spec())

    assert report["trade_date"] == "2026-07-15"
    assert report["board"]["code"] == "BK0968"
    assert report["board"]["constituent_count"] == 6
    assert report["ranked_count"] == 6
    assert [item["code"] for item in report["items"]] == ["300750", "002594", "601012", "002460", "300014"]
    assert report["items"][0]["concept"] == "固态电池"
