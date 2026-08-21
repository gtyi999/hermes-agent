#!/usr/bin/env python3
"""Install or update the weekly 富盈公馆 transaction cron job."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any


JOB_NAME = "Weekly Fuying Gongguan Second-hand Deals to Feishu"
SKILL_NAME = "fuying-gongguan-weekly-deals-feishu"
RUNTIME_FETCH_SCRIPT = "fuying_gongguan_weekly_deals.py"
DEFAULT_SCHEDULE = "50 10 * * 0"

CRON_PROMPT = """请根据 Script Output 中的 JSON，生成一条适合发送到飞书的中文“东莞中堂镇富盈公馆二手房成交周报”。

要求：
1. 标题使用“富盈公馆二手房成交周报（YYYY-MM-DD 至 YYYY-MM-DD）”；日期取 week_start 到 filter_end 的本地日期。
2. weekly_deal_count 为数字时，明确写“公开来源本周发现 N 条新增成交记录”。为 0 时必须写“本次公开来源未发现本周新增成交记录”，不得写成“官方零成交”。
3. weekly_deal_count 为 null 时，说明成交源抓取失败，列出 errors 中的关键错误；不得把失败解释为零成交。
4. 逐条输出 weekly_deals：成交日期、建筑面积、成交总价、成交单价、信息来源。JSON 为 null 的价格写“未披露”，不得估算。
5. 输出 weekly_statistics 中有值的字段：总/平均面积、已披露价格的样本数、总价合计与均值、单价均值及区间；没有已披露价格时明确说明。
6. 本周无新增记录时，可列出 latest_visible_deals 中最多 3 条，标题必须写“最近可见历史记录（非本周）”。
7. 单列“行情参考”：market_snapshot 的小区挂牌均价、周变化、在售套数、交易热度、商圈排名，以及中堂挂牌/成交均价；同时注明 market_snapshot.reported_period，不能把它误写为本周成交明细。
8. 可用一句话补充 leyoujia_snapshot 的挂牌均价、在售套数和历史成交展示数，并注明这是另一平台口径。
9. 末尾保留 caveats 的核心含义：公开平台数据可能滞后或遗漏，0 条不等于官方确认零网签，行情仅供参考。
10. 不要编造 Script Output 中不存在的楼栋、户型、价格或成交数量；保持简洁，适合飞书阅读。
11. 不要调用 send_message；Hermes cron 会自动投递最终响应。
"""


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[4]


def skill_dir_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def load_hermes_env(hermes_home: Path) -> dict[str, str]:
    env_path = hermes_home / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        values[key] = value
        os.environ.setdefault(key, value)
    return values


def copy_skill_to_hermes_home(skill_dir: Path, hermes_home: Path) -> Path:
    target = hermes_home / "skills" / "research" / SKILL_NAME
    if skill_dir.resolve() == target.resolve():
        return target
    if target.exists():
        shutil.rmtree(target)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    shutil.copytree(skill_dir, target, ignore=ignore)
    return target


def install_fetch_script(skill_dir: Path, hermes_home: Path) -> Path:
    source = skill_dir / "scripts" / "fetch_fuying_gongguan_weekly_deals.py"
    if not source.exists():
        raise FileNotFoundError(f"missing crawler script: {source}")
    scripts_dir = hermes_home / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    target = scripts_dir / RUNTIME_FETCH_SCRIPT
    shutil.copy2(source, target)
    target.chmod(0o700)
    return target


def find_existing_job(jobs: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((job for job in jobs if job.get("name") == name), None)


def create_or_update_job(args: argparse.Namespace) -> dict[str, Any]:
    from cron.jobs import create_job, list_jobs, trigger_job, update_job

    existing = find_existing_job(list_jobs(include_disabled=True), args.name)
    updates = {
        "prompt": CRON_PROMPT,
        "schedule": args.schedule,
        "deliver": args.deliver,
        "skills": [SKILL_NAME],
        "skill": SKILL_NAME,
        "script": RUNTIME_FETCH_SCRIPT,
        "enabled": True,
        "state": "scheduled",
        "paused_at": None,
        "paused_reason": None,
    }
    if existing:
        job = update_job(existing["id"], updates)
        action = "updated"
    else:
        job = create_job(
            prompt=CRON_PROMPT,
            schedule=args.schedule,
            name=args.name,
            deliver=args.deliver,
            skills=[SKILL_NAME],
            script=RUNTIME_FETCH_SCRIPT,
        )
        action = "created"

    if args.trigger_now and job:
        job = trigger_job(job["id"]) or job
        action += "_and_triggered"
    return {"action": action, "job": job}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install/update the weekly 富盈公馆 Feishu cron job.")
    parser.add_argument("--schedule", default=DEFAULT_SCHEDULE, help="Cron schedule; default: 50 10 * * 0")
    parser.add_argument("--deliver", default="feishu", help="Delivery target, e.g. feishu:oc_xxx")
    parser.add_argument("--name", default=JOB_NAME)
    parser.add_argument("--trigger-now", action="store_true", help="Also run on the next scheduler tick.")
    parser.add_argument("--skip-skill-install", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo_root = repo_root_from_script()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from hermes_constants import display_hermes_home, get_hermes_home

    hermes_home = get_hermes_home()
    display_home = display_hermes_home()
    env_values = load_hermes_env(hermes_home)
    skill_dir = skill_dir_from_script()

    installed_skill = None
    if not args.skip_skill_install:
        installed_skill = copy_skill_to_hermes_home(skill_dir, hermes_home)
    runtime_script = install_fetch_script(skill_dir, hermes_home)
    result = create_or_update_job(args)

    warnings: list[str] = []
    if args.deliver.strip().lower() == "feishu" and not (
        env_values.get("FEISHU_HOME_CHANNEL") or os.getenv("FEISHU_HOME_CHANNEL")
    ):
        warnings.append(
            f"deliver=feishu needs FEISHU_HOME_CHANNEL in {display_home}/.env, "
            "or pass --deliver 'feishu:<chat_id>'."
        )

    output = {
        "success": True,
        "action": result["action"],
        "job": result["job"],
        "runtime_script": str(runtime_script),
        "installed_skill": str(installed_skill) if installed_skill else None,
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    else:
        job = result["job"]
        print(f"{output['action']}: {job['name']} ({job['id']})")
        print(f"schedule: {job.get('schedule_display')}")
        print(f"deliver: {job.get('deliver')}")
        print(f"next_run_at: {job.get('next_run_at')}")
        print(f"runtime_script: {runtime_script}")
        if installed_skill:
            print(f"installed_skill: {installed_skill}")
        for warning in warnings:
            print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
