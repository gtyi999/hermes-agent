---
name: a-share-innovative-drug-leaders-feishu
description: Configure and run a scheduled A-share innovative-drug concept leader-stock quote digest for Feishu/Lark. Use when the user asks for 创新药概念龙头股, current-trading-day A股创新药价格和交易信息, a daily 23:18 report, or Feishu delivery of innovative-drug leader quotes.
---

# A-share Innovative Drug Leaders Feishu

Create or maintain a Hermes cron job that reports the latest trading day's price and trading information for five leading A-share stocks in Eastmoney's `创新药` concept board.

## Install Or Update The Job

Run from the repository root:

```bash
source venv/bin/activate
python skills/research/a-share-innovative-drug-leaders-feishu/scripts/setup_daily_innovative_drug_leaders.py --deliver 'feishu:oc_xxx'
```

Defaults:

- Schedule: `18 23 * * *` (daily at 23:18 in the Hermes/system timezone)
- Job name: `Daily A-share Innovative Drug Leaders to Feishu`
- Runtime crawler: `HERMES_HOME/scripts/a_share_innovative_drug_leaders.py`
- Delivery: the explicit Feishu target passed with `--deliver`, or the configured Feishu home channel

Use `--trigger-now` only when the user explicitly requests an immediate delivery test.

## Runtime Behavior

The crawler resolves and reads Eastmoney's public `创新药` concept quote data:

- Exact concept board: `创新药` (`BK1106`)
- Primary constituent quotes: H5 `ZJLX/getZDYLBData`
- Fallback constituent quotes: Quote `clist/get`

It determines the latest trading date from quote timestamps and excludes stale/suspended rows from the five-stock ranking. It ranks remaining stocks by:

1. Total market value
2. Current-day turnover
3. Main net inflow
4. Current-day percentage change

The report is a market-data digest, not personalized investment advice. If fewer than five current-trading-day quotes are available, report the real count. Never invent missing values or silently turn source failure into an empty market.

Hermes cron injects the crawler's JSON stdout into the prompt and delivers the final response. Do not call `send_message` from the prompt.

## Useful Commands

Run the bundled crawler:

```bash
source venv/bin/activate
python skills/research/a-share-innovative-drug-leaders-feishu/scripts/fetch_innovative_drug_leaders.py --limit 5
```

List the installed job:

```bash
source venv/bin/activate
python - <<'PY'
from cron.jobs import list_jobs
for job in list_jobs(include_disabled=True):
    if job.get("name") == "Daily A-share Innovative Drug Leaders to Feishu":
        print(job)
PY
```

## Troubleshooting

- If `deliver=feishu` is ambiguous, rerun setup with `--deliver 'feishu:<chat_id>'`.
- If the Gateway is stopped, the job cannot tick; verify `hermes-gateway.service`.
- Eastmoney may intermittently close TLS connections. The crawler retries and then falls back to `curl` and alternate quote hosts.
- On a non-trading day, the report correctly labels the latest quote date instead of claiming the calendar date is a trading day.
