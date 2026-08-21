---
title: "A Share Optical Module Pcb Leaders Feishu"
sidebar_label: "A Share Optical Module Pcb Leaders Feishu"
description: "Configure and run a scheduled A-share optical-module and PCB concept leaders quote digest for Feishu/Lark"
---

{/* This page is auto-generated from the skill's SKILL.md by website/scripts/generate-skill-docs.py. Edit the source SKILL.md, not this page. */}

# A Share Optical Module Pcb Leaders Feishu

Configure and run a scheduled A-share optical-module and PCB concept leaders quote digest for Feishu/Lark. Use this skill when the user asks to crawl 光模块PCB概念龙头股, 光通信模块、CPO、PCB概念股票价格, current-trading-day A股行情, schedule a daily 21:50 stock report, or send optical-module/PCB leader stock trading information to Feishu.

## Skill metadata

| | |
|---|---|
| Source | Bundled (installed by default) |
| Path | `skills/research/a-share-optical-module-pcb-leaders-feishu` |

## Reference: full SKILL.md

:::info
The following is the complete skill definition that Hermes loads when this skill is triggered. This is what the agent sees as instructions when the skill is active.
:::

# A-share Optical Module PCB Leaders Feishu

Create or maintain a Hermes cron job that reports current-trading-day A-share quote and trading information for the top 5 leader stocks related to optical module and PCB concept boards, plus a market-index snapshot for 上证指数 and 深证指数.

## Install Or Update The Job

Run from the repository root:

```bash
source venv/bin/activate
python skills/research/a-share-optical-module-pcb-leaders-feishu/scripts/setup_daily_optical_module_pcb_leaders.py
```

Defaults:

- Schedule: `50 21 * * *` (daily at 21:50 in the Hermes configured timezone)
- Delivery target: the Feishu DM target passed to the setup script, or `feishu` if none is provided
- Job name: `Daily A-share Optical Module PCB Leaders to Feishu`
- Runtime crawler: copied to `HERMES_HOME/scripts/a_share_optical_module_pcb_leaders.py`

Use the known Feishu DM target explicitly when available:

```bash
python skills/research/a-share-optical-module-pcb-leaders-feishu/scripts/setup_daily_optical_module_pcb_leaders.py --deliver 'feishu:oc_xxx'
```

Use `--trigger-now` only when the user explicitly wants an immediate test delivery.

## Runtime Behavior

The crawler uses Eastmoney public quote endpoints:

- Search API to resolve concept board codes
- Quote `ulist.np/get` to fetch 上证指数 (`1.000001`) and 深证指数 (`0.399001`)
- H5 `ZJLX/getZDYLBData` with `fs=b:<board_code>` to fetch current quote and trading fields, with Quote `clist/get` as fallback

Default concept boards:

- `光通信模块` (`BK1136`)
- `CPO概念` (`BK1128`)
- `PCB` (`BK0877`)

The script unions board constituents and ranks leader stocks with an explainable rule:

1. Higher total market value
2. Higher current-day turnover
3. More matched concept boards
4. Higher main net inflow
5. Higher current-day change percentage

The cron prompt formats the JSON into a concise Chinese Feishu message. Do not call `send_message` inside the cron prompt; Hermes cron automatically delivers the final response.
The generated message should include the two market indices before the ranked stock list when `market_indices` is present.

## Useful Commands

Run the crawler locally:

```bash
source venv/bin/activate
python skills/research/a-share-optical-module-pcb-leaders-feishu/scripts/fetch_optical_module_pcb_leaders.py --limit 5
```

Create the job but deliver locally for debugging:

```bash
python skills/research/a-share-optical-module-pcb-leaders-feishu/scripts/setup_daily_optical_module_pcb_leaders.py --deliver local
```

List the installed job:

```bash
source venv/bin/activate
python - <<'PY'
from cron.jobs import list_jobs
for job in list_jobs(include_disabled=True):
    if job.get("name") == "Daily A-share Optical Module PCB Leaders to Feishu":
        print(job)
PY
```

## Troubleshooting

- If `deliver=feishu` cannot resolve, set `FEISHU_HOME_CHANNEL` in `HERMES_HOME/.env` or recreate the job with `--deliver 'feishu:<chat_id>'`.
- If the gateway is not running, cron jobs will not tick. Start it with `hermes gateway start`.
- If Eastmoney temporarily closes connections, the crawler retries and falls back to `curl`; make sure `curl` is available on the host.
- If fewer than 5 matching stocks are available, report the actual count instead of inventing stocks.
