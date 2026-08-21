---
name: fuying-gongguan-weekly-deals-feishu
description: Configure and run a weekly second-hand home transaction digest for 富盈公馆 in 中堂镇, 东莞, delivered to Feishu/Lark. Use this skill when the user asks to crawl or summarize this week's 富盈公馆二手房成交记录, schedule the report for Sundays at 10:50, send the community transaction report to 飞书助手, or test and repair this Hermes cron job.
---

# Fuying Gongguan Weekly Deals Feishu

Create or maintain the Hermes cron job that reports publicly visible second-hand transaction records for 富盈公馆 in 中堂镇, 东莞.

## Install Or Update The Job

Run from the repository root:

```bash
source venv/bin/activate
python skills/research/fuying-gongguan-weekly-deals-feishu/scripts/setup_weekly_fuying_gongguan_deals.py --deliver 'feishu:oc_xxx'
```

Defaults:

- Schedule: `50 10 * * 0` (Sunday at 10:50 in the Hermes configured timezone)
- Job name: `Weekly Fuying Gongguan Second-hand Deals to Feishu`
- Runtime crawler: `HERMES_HOME/scripts/fuying_gongguan_weekly_deals.py`
- Community: 东莞市中堂镇富盈公馆, Fang project `2819973108`

Use `--trigger-now` only when the user explicitly requests an immediate Feishu delivery.

## Runtime Behavior

Run the crawler before the cron agent turn. It:

1. Reads the public Fang transaction table, using a read-only rendering fallback if the direct page requests verification.
2. Filters records locally to Monday 00:00 through the Sunday execution time in Asia/Shanghai.
3. Computes count, disclosed area, total-price, and unit-price statistics without filling missing values.
4. Adds the latest Fang market-week snapshot and a LeYouJia community snapshot as labeled context.
5. Emits JSON for the cron prompt.

Treat `weekly_deal_count: 0` as “the public sources exposed no new record,” not proof of zero official registrations. If `weekly_deal_count` is `null`, report a source failure rather than saying there were no transactions. Keep source periods and caveats in the Feishu message.

Hermes cron delivers the final response automatically. Do not call `send_message` from the cron prompt.

## Useful Commands

Run the crawler without sending:

```bash
source venv/bin/activate
python skills/research/fuying-gongguan-weekly-deals-feishu/scripts/fetch_fuying_gongguan_weekly_deals.py
```

List the installed job:

```bash
source venv/bin/activate
python - <<'PY'
from cron.jobs import list_jobs
for job in list_jobs(include_disabled=True):
    if job.get("name") == "Weekly Fuying Gongguan Second-hand Deals to Feishu":
        print(job)
PY
```

## Troubleshooting

- If the Fang desktop page returns a slider challenge, retain the read-only rendering fallback and surface its use in `warnings`.
- If all transaction sources fail, keep `weekly_deal_count` as `null`; never turn an unavailable source into zero deals.
- If the source omits total price or unit price, render “未披露” instead of estimating it.
- If `deliver=feishu` cannot resolve, pass an explicit `feishu:<chat_id>` target.
- If the gateway is stopped, start it with `hermes gateway start`; scheduled jobs only tick while the gateway is running.
