import argparse
import importlib.util
import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = PROJECT_ROOT / "skills" / "research" / "fuying-gongguan-weekly-deals-feishu"
FETCH_SCRIPT = SKILL_DIR / "scripts" / "fetch_fuying_gongguan_weekly_deals.py"
SETUP_SCRIPT = SKILL_DIR / "scripts" / "setup_weekly_fuying_gongguan_deals.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


DEAL_HTML = """
<html><body><h1>富盈公馆</h1><table>
<tr><th>房源面积</th><th>成交时间</th><th>成交总价</th><th>成交均价</th><th>信息来源</th></tr>
<tr><td><p>100.00㎡</p></td><td><p>2026-08-03</p></td><td><p>80万</p></td><td><p>8000元/㎡</p></td><td><p>市场信息</p></td></tr>
<tr><td><p>87.02㎡</p></td><td><p>2026-07-28</p></td><td><p>暂无</p></td><td><p>暂无</p></td><td><p>市场信息</p></td></tr>
</table></body></html>
"""


DEAL_MARKDOWN = """
Title: 富盈公馆成交记录，历史成交价，成交量-房天下

| 房源面积 | 成交时间 | 成交总价 | 成交均价 | 信息来源 |
| --- | --- | --- | --- | --- |
| 100.00㎡ | 2026-08-03 | 80万 | 8000元/㎡ | 市场信息 |
| 87.02㎡ | 2026-07-28 | 暂无 | 暂无 | 市场信息 |
"""


MARKET_HTML = """
<html><body>
<h1>富盈公馆</h1><p>中堂· 07月25日-07月31日</p>
<div><em>8685</em>元/平</div><p>本周挂牌均价</p><div>-0.53 %</div><div>低</div><p>交易热度</p>
<p>本小区均价环比上周下跌0.53%；</p><p>本小区均价在商圈内排名19（共25个挂牌小区）;</p>
<p>小区总在售房源：约133套</p>
<h2>所在商圈：中堂</h2><em>11056.00</em>元/平<p>本周挂牌均价</p><div>环比上周 0.23%</div>
<em>13343.00</em>元/平<p>本周成交均价</p><div>环比上周 100%</div>
</body></html>
"""


LEYOUJIA_HTML = """
<h1>富盈公馆</h1>
<p class="card-money">12668<span>元/㎡</span></p>
<p class="sell-num">9<span>套</span></p><p class="sell-type">在售房源</p>
<p class="sell-num">1<span>套</span></p><p class="sell-type">历史成交</p>
"""


def test_parse_html_and_markdown_deal_tables():
    mod = load_module(FETCH_SCRIPT, "fuying_fetch_parse")
    html_rows = mod.parse_deal_rows(DEAL_HTML)
    markdown_rows = mod.parse_deal_rows(DEAL_MARKDOWN)

    assert html_rows == markdown_rows
    assert html_rows[0]["deal_date"] == "2026-08-03"
    assert html_rows[0]["total_price_wan"] == 80.0
    assert html_rows[0]["unit_price_yuan_sqm"] == 8000.0
    assert html_rows[1]["total_price_wan"] is None


def test_parse_market_and_leyoujia_snapshots():
    mod = load_module(FETCH_SCRIPT, "fuying_fetch_snapshots")
    market = mod.parse_fang_market_snapshot(MARKET_HTML)
    leyoujia = mod.parse_leyoujia_snapshot(LEYOUJIA_HTML)

    assert market["reported_period"] == "07月25日-07月31日"
    assert market["community_listing_avg_yuan_sqm"] == 8685.0
    assert market["community_listing_week_change_pct"] == -0.53
    assert market["transaction_heat"] == "低"
    assert market["active_listing_count"] == 133
    assert market["zhongtang_deal_avg_yuan_sqm"] == 13343.0
    assert leyoujia["listing_avg_yuan_sqm"] == 12668.0
    assert leyoujia["active_listing_count"] == 9
    assert leyoujia["historical_deal_count"] == 1


def test_build_digest_filters_current_week_and_keeps_missing_prices(monkeypatch):
    mod = load_module(FETCH_SCRIPT, "fuying_fetch_digest")
    records = mod.parse_deal_rows(DEAL_HTML)
    source = {
        "name": "房天下富盈公馆成交记录",
        "url": mod.FANG_DEALS_URL,
        "transport": "reader_fallback",
        "visible_record_count": len(records),
        "latest_record_date": records[0]["deal_date"],
    }
    monkeypatch.setattr(mod, "fetch_deal_records", lambda **kwargs: (records, source, ["fallback used"]))
    monkeypatch.setattr(mod, "fetch_fang_market_snapshot", lambda **kwargs: {"reported_period": "07月25日-07月31日"})
    monkeypatch.setattr(mod, "fetch_leyoujia_snapshot", lambda **kwargs: {"historical_deal_count": 1})
    args = argparse.Namespace(
        now="2026-08-09T10:50:00+08:00",
        timeout=10,
        retries=1,
        latest_limit=5,
    )

    digest = mod.build_digest(args)

    assert digest["success"] is True
    assert digest["week_start"] == "2026-08-03T00:00:00+08:00"
    assert digest["weekly_deal_count"] == 1
    assert digest["weekly_deals"][0]["deal_date"] == "2026-08-03"
    assert digest["weekly_statistics"]["average_unit_price_yuan_sqm"] == 8000.0
    assert digest["warnings"] == ["fallback used"]


def test_build_digest_uses_null_count_when_transaction_source_fails(monkeypatch):
    mod = load_module(FETCH_SCRIPT, "fuying_fetch_failure")

    def fail(**kwargs):
        raise RuntimeError("source unavailable")

    monkeypatch.setattr(mod, "fetch_deal_records", fail)
    monkeypatch.setattr(mod, "fetch_fang_market_snapshot", fail)
    monkeypatch.setattr(mod, "fetch_leyoujia_snapshot", fail)
    args = argparse.Namespace(
        now="2026-08-09T10:50:00+08:00",
        timeout=10,
        retries=1,
        latest_limit=5,
    )

    digest = mod.build_digest(args)

    assert digest["success"] is False
    assert digest["weekly_deal_count"] is None
    assert digest["weekly_statistics"] is None
    assert len(digest["errors"]) == 3


def test_setup_installs_runtime_script_and_creates_weekly_cron_job(monkeypatch, capsys):
    mod = load_module(SETUP_SCRIPT, "fuying_setup")
    hermes_home = Path(os.environ["HERMES_HOME"])
    (hermes_home / "cron" / "output").mkdir(parents=True, exist_ok=True)
    (hermes_home / "scripts").mkdir(exist_ok=True)

    import cron.jobs as jobs_mod

    monkeypatch.setattr(jobs_mod, "HERMES_DIR", hermes_home)
    monkeypatch.setattr(jobs_mod, "CRON_DIR", hermes_home / "cron")
    monkeypatch.setattr(jobs_mod, "JOBS_FILE", hermes_home / "cron" / "jobs.json")
    monkeypatch.setattr(jobs_mod, "OUTPUT_DIR", hermes_home / "cron" / "output")

    assert mod.main(["--deliver", "local", "--skip-skill-install", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["success"] is True
    assert output["job"]["name"] == mod.JOB_NAME
    assert output["job"]["schedule_display"] == "50 10 * * 0"
    assert output["job"]["deliver"] == "local"
    assert output["job"]["skills"] == [mod.SKILL_NAME]
    assert output["job"]["script"] == mod.RUNTIME_FETCH_SCRIPT
    assert (hermes_home / "scripts" / mod.RUNTIME_FETCH_SCRIPT).exists()
