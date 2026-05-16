---
name: ai-news-daily-feishu
description: Configure and run a scheduled AI-news digest for Feishu/Lark. Use this skill when the user asks to crawl, summarize, rank, or schedule the hottest AI news, especially requests like daily AI news at 00:00, send AI headlines to Feishu, create an AI news cron job, or test/repair the Feishu AI news digest.
---

# AI News Daily Feishu

Create or maintain a Hermes cron job that fetches the top AI news and delivers a Chinese digest to Feishu.

## Install Or Update The Job

Run the setup script from the repository root:

```bash
source venv/bin/activate
python skills/research/ai-news-daily-feishu/scripts/setup_daily_ai_news.py
```

Defaults:

- Schedule: `0 0 * * *` (daily at 00:00 in the Hermes configured timezone)
- Delivery target: `feishu`
- Job name: `Daily AI News to Feishu`
- Runtime crawler: copied to `HERMES_HOME/scripts/ai_news_daily_feishu_fetch.py`

If `deliver=feishu` is used without an explicit chat ID, Hermes must have `FEISHU_HOME_CHANNEL` configured in `HERMES_HOME/.env`. For a specific chat, pass:

```bash
python skills/research/ai-news-daily-feishu/scripts/setup_daily_ai_news.py --deliver 'feishu:oc_xxx'
```

Use `--trigger-now` only when the user explicitly wants an immediate test delivery.

## Runtime Behavior

The cron job runs the bundled crawler before the agent turn. The crawler gathers candidate stories from:

- Hacker News Algolia searches for AI terms
- Google News RSS search
- AI-focused RSS/Atom feeds from major technology and AI publications

The crawler outputs JSON with a ranked `top_items` list. The cron prompt then formats the top 10 items into a concise Chinese Feishu message. Do not call `send_message` from inside the cron prompt; Hermes cron automatically delivers the final response.

## Useful Commands

List cron jobs:

```bash
source venv/bin/activate
python - <<'PY'
from cron.jobs import list_jobs
for job in list_jobs(include_disabled=True):
    if job.get("name") == "Daily AI News to Feishu":
        print(job)
PY
```

Run only the crawler locally:

```bash
source venv/bin/activate
python skills/research/ai-news-daily-feishu/scripts/fetch_ai_news.py --limit 10
```

Create the job but deliver locally for debugging:

```bash
python skills/research/ai-news-daily-feishu/scripts/setup_daily_ai_news.py --deliver local
```

## Troubleshooting

- If delivery reports `no delivery target resolved for deliver=feishu`, set `FEISHU_HOME_CHANNEL` or recreate the job with `--deliver 'feishu:<chat_id>'`.
- If the gateway is not running, cron jobs will not tick. Start it with `hermes gateway start`.
- If all network sources fail, the crawler still emits JSON with `errors`; the cron response should report the source failures instead of inventing news.
