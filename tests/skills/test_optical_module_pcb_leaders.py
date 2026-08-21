from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    PROJECT_ROOT
    / "skills"
    / "research"
    / "a-share-optical-module-pcb-leaders-feishu"
    / "scripts"
    / "fetch_optical_module_pcb_leaders.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("optical_module_pcb_leaders_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_normalizes_eastmoney_quote_fields():
    mod = load_module()
    row = mod.normalize_constituent(
        {
            "f12": "300308",
            "f13": 0,
            "f14": "中际旭创",
            "f2": 116931,
            "f3": -124,
            "f4": -1474,
            "f5": 247946,
            "f6": 29281915790.66,
            "f8": 223,
            "f9": 5685,
            "f10": 67,
            "f20": 1304055018068,
            "f21": 1297863681813,
            "f62": 275699712.0,
            "f124": 1784100873,
            "f184": 94,
        }
    )

    assert row["market_label"] == "SZ"
    assert row["last_price"] == 1169.31
    assert row["change_pct"] == -1.24
    assert row["change_amount"] == -14.74
    assert row["turnover_rate"] == 2.23
    assert row["pe_dynamic"] == 56.85
    assert row["volume_ratio"] == 0.67
    assert row["main_net_inflow_text"] == "2.76亿"
    assert row["quote_date"] == "2026-07-15"

    h5_row = mod.normalize_constituent({"f12": "300308", "f13": 0, "f14": "中际旭创", "f2": 1169.31, "f3": -1.24})
    assert h5_row["last_price"] == 1169.31
    assert h5_row["change_pct"] == -1.24


def test_normalizes_market_index_quote_fields():
    mod = load_module()
    requested_by_code = {
        "000001": {"name": "上证指数", "code": "000001", "secid": "1.000001"},
        "399001": {"name": "深证指数", "code": "399001", "secid": "0.399001"},
    }

    shanghai = mod.normalize_market_index(
        {
            "f12": "000001",
            "f13": 1,
            "f14": "上证指数",
            "f2": 387678,
            "f3": 25,
            "f4": 975,
            "f5": 562122601,
            "f6": 1025875517700.1,
            "f7": 70,
            "f15": 387883,
            "f16": 385171,
            "f17": 386809,
            "f18": 386703,
            "f124": 1784794322,
        },
        requested_by_code,
    )
    shenzhen = mod.normalize_market_index(
        {
            "f12": "399001",
            "f13": 0,
            "f14": "深证成指",
            "f2": 1412331,
            "f3": 44,
            "f4": 6187,
            "f5": 625578724,
            "f6": 1169425765213.4976,
            "f7": 151,
            "f15": 1420364,
            "f16": 1399183,
            "f17": 1411602,
            "f18": 1406144,
            "f124": 1784794311,
        },
        requested_by_code,
    )

    assert shanghai["name"] == "上证指数"
    assert shanghai["last_price"] == 3876.78
    assert shanghai["change_pct"] == 0.25
    assert shanghai["change_amount"] == 9.75
    assert shanghai["turnover_text"] == "10258.76亿"
    assert shanghai["quote_date"] == "2026-07-23"

    assert shenzhen["name"] == "深证指数"
    assert shenzhen["source_name"] == "深证成指"
    assert shenzhen["last_price"] == 14123.31
    assert shenzhen["change_pct"] == 0.44
    assert shenzhen["change_amount"] == 61.87


def test_build_report_ranks_top_five_by_market_value_and_trading_weight(monkeypatch):
    mod = load_module()
    boards = {
        "光通信模块": {"keyword": "光通信模块", "code": "BK1136", "name": "光通信模块", "quote_id": "90.BK1136"},
        "CPO概念": {"keyword": "CPO概念", "code": "BK1128", "name": "CPO概念", "quote_id": "90.BK1128"},
        "PCB": {"keyword": "PCB", "code": "BK0877", "name": "PCB", "quote_id": "90.BK0877"},
    }
    rows_by_board = {
        "BK1136": [
            {"code": "300308", "name": "中际旭创", "market": 0, "market_label": "SZ", "total_market_value": 1_300, "turnover": 20, "main_net_inflow": 1, "change_pct": 1, "quote_timestamp": 1784100873, "quote_time": "2026-07-15T15:34:33+08:00", "quote_date": "2026-07-15"},
            {"code": "300502", "name": "新易盛", "market": 0, "market_label": "SZ", "total_market_value": 900, "turnover": 25, "main_net_inflow": 2, "change_pct": 2, "quote_timestamp": 1784100873, "quote_time": "2026-07-15T15:34:33+08:00", "quote_date": "2026-07-15"},
            {"code": "002475", "name": "立讯精密", "market": 0, "market_label": "SZ", "total_market_value": 700, "turnover": 10, "main_net_inflow": 2, "change_pct": 1, "quote_timestamp": 1784100873, "quote_time": "2026-07-15T15:34:33+08:00", "quote_date": "2026-07-15"},
        ],
        "BK1128": [
            {"code": "300308", "name": "中际旭创", "market": 0, "market_label": "SZ", "total_market_value": 1_300, "turnover": 20, "main_net_inflow": 1, "change_pct": 1, "quote_timestamp": 1784100873, "quote_time": "2026-07-15T15:34:33+08:00", "quote_date": "2026-07-15"},
            {"code": "002384", "name": "东山精密", "market": 0, "market_label": "SZ", "total_market_value": 800, "turnover": 30, "main_net_inflow": 3, "change_pct": 3, "quote_timestamp": 1784100873, "quote_time": "2026-07-15T15:34:33+08:00", "quote_date": "2026-07-15"},
        ],
        "BK0877": [
            {"code": "002384", "name": "东山精密", "market": 0, "market_label": "SZ", "total_market_value": 800, "turnover": 30, "main_net_inflow": 3, "change_pct": 3, "quote_timestamp": 1784100873, "quote_time": "2026-07-15T15:34:33+08:00", "quote_date": "2026-07-15"},
            {"code": "601869", "name": "长飞光纤", "market": 1, "market_label": "SH", "total_market_value": 500, "turnover": 8, "main_net_inflow": 4, "change_pct": 4, "quote_timestamp": 1784100873, "quote_time": "2026-07-15T15:34:33+08:00", "quote_date": "2026-07-15"},
            {"code": "603228", "name": "景旺电子", "market": 1, "market_label": "SH", "total_market_value": 450, "turnover": 12, "main_net_inflow": 5, "change_pct": 5, "quote_timestamp": 1784100873, "quote_time": "2026-07-15T15:34:33+08:00", "quote_date": "2026-07-15"},
        ],
    }

    monkeypatch.setattr(mod, "search_board_code", lambda spec: boards[spec["keyword"]])
    monkeypatch.setattr(mod, "fetch_board_constituents", lambda code: rows_by_board[code])
    monkeypatch.setattr(
        mod,
        "fetch_market_indices",
        lambda: [
            {"code": "000001", "name": "上证指数", "last_price": 3876.78, "change_pct": 0.25},
            {"code": "399001", "name": "深证指数", "last_price": 14123.31, "change_pct": 0.44},
        ],
    )

    report = mod.build_report(5, mod.parse_concept_specs())

    assert report["trade_date"] == "2026-07-15"
    assert [item["name"] for item in report["market_indices"]] == ["上证指数", "深证指数"]
    assert report["market_index_errors"] == []
    assert report["concept_constituent_count"] == 6
    assert report["ranked_count"] == 6
    assert [item["code"] for item in report["items"]] == ["300308", "300502", "002384", "002475", "601869"]
    assert report["items"][0]["concept_hit_count"] == 2
    assert report["items"][0]["concepts_text"] == "光通信模块、CPO概念"
    assert report["items"][2]["concepts_text"] == "CPO概念、PCB"
