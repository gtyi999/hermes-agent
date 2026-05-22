import importlib.util
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "research"
    / "github-daily-stars-feishu"
    / "scripts"
    / "fetch_github_daily_stars.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("fetch_github_daily_stars", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_target_day_window_maps_asia_shanghai_to_utc_hours():
    mod = load_module()

    start, end = mod.target_day_window("2026-05-21", "Asia/Shanghai")
    hours = list(mod.iter_utc_hours(start, end))

    assert start.isoformat() == "2026-05-21T00:00:00+08:00"
    assert end.isoformat() == "2026-05-22T00:00:00+08:00"
    assert len(hours) == 24
    assert mod.gharchive_url(hours[0]).endswith("/2026-05-20-16.json.gz")
    assert mod.gharchive_url(hours[-1]).endswith("/2026-05-21-15.json.gz")


def test_count_watch_events_filters_type_action_and_window():
    mod = load_module()
    start = datetime(2026, 5, 20, 16, tzinfo=timezone.utc)
    end = datetime(2026, 5, 21, 16, tzinfo=timezone.utc)
    lines = [
        json.dumps({
            "type": "WatchEvent",
            "payload": {"action": "started"},
            "created_at": "2026-05-20T16:00:00Z",
            "repo": {"name": "owner/project"},
        }),
        json.dumps({
            "type": "WatchEvent",
            "payload": {"action": "started"},
            "created_at": "2026-05-21T15:59:59Z",
            "repo": {"name": "owner/project"},
        }).encode(),
        json.dumps({
            "type": "WatchEvent",
            "payload": {"action": "deleted"},
            "created_at": "2026-05-21T12:00:00Z",
            "repo": {"name": "owner/ignored"},
        }),
        json.dumps({
            "type": "PushEvent",
            "created_at": "2026-05-21T12:00:00Z",
            "repo": {"name": "owner/ignored"},
        }),
        json.dumps({
            "type": "WatchEvent",
            "payload": {"action": "started"},
            "created_at": "2026-05-21T16:00:00Z",
            "repo": {"name": "owner/outside"},
        }),
        "{bad json",
    ]

    counts, malformed = mod.count_watch_events_from_lines(lines, start, end)

    assert counts == Counter({"owner/project": 2})
    assert malformed == 1


def test_build_report_ranks_repositories_without_network(monkeypatch):
    mod = load_module()
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    def fake_fetch_hour_counts(hour, start_utc, end_utc):
        if hour.hour == 16:
            return Counter({"alpha/repo": 3, "beta/tool": 1}), []
        if hour.hour == 17:
            return Counter({"beta/tool": 4}), ["transient metadata source warning"]
        return Counter(), []

    def fake_enrich(repo, stars_yesterday, rank):
        return {
            "rank": rank,
            "repo": repo,
            "repo_url": f"https://github.com/{repo}",
            "stars_yesterday": stars_yesterday,
            "total_stars": 1000 if repo == "beta/tool" else 500,
            "language": "Python",
            "description": "",
        }

    report = mod.build_report(
        2,
        day="2026-05-21",
        timezone_name="Asia/Shanghai",
        candidates=5,
        workers=1,
        fetch_hour_counts_fn=fake_fetch_hour_counts,
        enrich_repo_fn=fake_enrich,
    )

    assert report["target_date"] == "2026-05-21"
    assert report["timezone"] == "Asia/Shanghai"
    assert report["total_watch_events"] == 8
    assert report["unique_repositories"] == 2
    assert report["partial_data"] is True
    assert [item["repo"] for item in report["items"]] == ["beta/tool", "alpha/repo"]
    assert [item["stars_yesterday"] for item in report["items"]] == [5, 3]
