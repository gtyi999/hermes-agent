---
name: a-share-solid-state-battery-limitups-feishu
description: Configure and run a scheduled A-share solid-state battery limit-up digest for Feishu/Lark. Use this skill when the user asks to crawl A股固态电池概念, find previous-trading-day涨停 stocks, schedule a daily 00:20 stock report, send solid-state battery concept涨停股 to Feishu, or test/repair this cron job.
---

# A-share Solid-state Battery Limit-ups Feishu

Create or maintain a Hermes cron job that reports previous-trading-day A-share limit-up stocks in the Eastmoney `固态电池` concept board.

## Install Or Update The Job

Run from the repository root:

```bash
source venv/bin/activate
python skills/research/a-share-solid-state-battery-limitups-feishu/scripts/setup_daily_solid_state_limitups.py
```

Defaults:

- Schedule: `20 0 * * *` (daily at 00:20 in the Hermes configured timezone)
- Delivery target: the Feishu DM target passed to the setup script, or `feishu` if none is provided
- Job name: `Daily A-share Solid-state Battery Limit-ups to Feishu`
- Runtime crawler: copied to `HERMES_HOME/scripts/a_share_solid_state_battery_limitups.py`

Use the known Feishu DM target explicitly when available:

```bash
python skills/research/a-share-solid-state-battery-limitups-feishu/scripts/setup_daily_solid_state_limitups.py --deliver 'feishu:oc_xxx'
```

Use `--trigger-now` only when the user explicitly wants an immediate test delivery.

## Runtime Behavior

The crawler uses Eastmoney public endpoints:

- Search API to confirm the `固态电池` concept board code (`BK0968`)
- H5 `ZJLX/getZDYLBData` with `fs=b:BK0968` to fetch board constituents, with Quote `clist/get` as fallback
- `push2ex.eastmoney.com/getTopicZTPool` to fetch the limit-up pool for the latest available trading day

The script intersects the limit-up pool with board constituents and returns up to 10 stocks sorted by limit-up strength:

1. Higher consecutive limit-up count (`lbc`)
2. Higher sealed-order fund (`fund`)
3. Earlier first limit-up time (`fbt`)

The cron prompt formats the JSON into a concise Chinese Feishu message. Do not call `send_message` inside the cron prompt; Hermes cron automatically delivers the final response.

## Useful Commands

Run the crawler locally:

```bash
source venv/bin/activate
python skills/research/a-share-solid-state-battery-limitups-feishu/scripts/fetch_solid_state_battery_limitups.py --limit 10
```

Create the job but deliver locally for debugging:

```bash
python skills/research/a-share-solid-state-battery-limitups-feishu/scripts/setup_daily_solid_state_limitups.py --deliver local
```

List the installed job:

```bash
source venv/bin/activate
python - <<'PY'
from cron.jobs import list_jobs
for job in list_jobs(include_disabled=True):
    if job.get("name") == "Daily A-share Solid-state Battery Limit-ups to Feishu":
        print(job)
PY
```

## Troubleshooting

- If `deliver=feishu` cannot resolve, set `FEISHU_HOME_CHANNEL` in `HERMES_HOME/.env` or recreate the job with `--deliver 'feishu:<chat_id>'`.
- If the gateway is not running, cron jobs will not tick. Start it with `hermes gateway start`.
- If Eastmoney temporarily closes connections, the crawler retries and falls back to `curl`; make sure `curl` is available on the host.
- If fewer than 10 matching stocks exist for the previous trading day, report the actual count instead of inventing stocks.
