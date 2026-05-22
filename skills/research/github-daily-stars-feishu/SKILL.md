---
name: github-daily-stars-feishu
description: Configure and run a scheduled GitHub daily star-growth digest for Feishu/Lark. Use this skill when the user asks to crawl yesterday's highest-star-gain GitHub repositories, schedule a daily 22:00 GitHub stars report, send GitHub trending/star rankings to Feishu, or test/repair this cron job.
---

# GitHub Daily Stars Feishu

Create or maintain a Hermes cron job that ranks GitHub repositories by the number of stars gained yesterday and delivers a Chinese digest to Feishu.

## Install Or Update The Job

Run from the repository root:

```bash
source venv/bin/activate
python skills/research/github-daily-stars-feishu/scripts/setup_daily_github_stars.py
```

Defaults:

- Schedule: `0 22 * * *` (daily at 22:00 in the Hermes configured timezone)
- Delivery target: the Feishu DM target passed to the setup script, or `feishu` if none is provided
- Job name: `Daily GitHub Yesterday Stars to Feishu`
- Runtime crawler: copied to `HERMES_HOME/scripts/github_daily_stars_fetch.py`
- Ranking source: GH Archive `WatchEvent` counts for yesterday's local-date window

Use the known Feishu DM target explicitly when available:

```bash
python skills/research/github-daily-stars-feishu/scripts/setup_daily_github_stars.py --deliver 'feishu:oc_xxx'
```

Use `--trigger-now` only when the user explicitly wants an immediate test delivery.

## Runtime Behavior

The crawler reads GH Archive hourly event files for the target local day, counts `WatchEvent` records per repository, and enriches the top repositories with GitHub REST API metadata.

Important details:

- "Yesterday" is calculated in `HERMES_TIMEZONE`, `TZ`, or `Asia/Shanghai` by default.
- `GITHUB_TOKEN` or `GH_TOKEN` in `HERMES_HOME/.env` is optional, but recommended to avoid GitHub REST API rate limits during metadata enrichment.
- GH Archive files are UTC-hourly, so the script maps the local-day window to the needed UTC hours and filters event timestamps precisely.
- The cron prompt formats the JSON into a concise Chinese Feishu message. Do not call `send_message` inside the cron prompt; Hermes cron automatically delivers the final response.

## Useful Commands

Run the crawler locally:

```bash
source venv/bin/activate
python skills/research/github-daily-stars-feishu/scripts/fetch_github_daily_stars.py --limit 10
```

Run for a specific date and timezone:

```bash
python skills/research/github-daily-stars-feishu/scripts/fetch_github_daily_stars.py --date 2026-05-21 --timezone Asia/Shanghai
```

Create the job but deliver locally for debugging:

```bash
python skills/research/github-daily-stars-feishu/scripts/setup_daily_github_stars.py --deliver local
```

List the installed job:

```bash
source venv/bin/activate
python - <<'PY'
from cron.jobs import list_jobs
for job in list_jobs(include_disabled=True):
    if job.get("name") == "Daily GitHub Yesterday Stars to Feishu":
        print(job)
PY
```

## Troubleshooting

- If `deliver=feishu` cannot resolve, set `FEISHU_HOME_CHANNEL` in `HERMES_HOME/.env` or recreate the job with `--deliver 'feishu:<chat_id>'`.
- If the gateway is not running, cron jobs will not tick. Start it with `hermes gateway start`.
- If GitHub metadata enrichment is rate-limited, set `GITHUB_TOKEN` or `GH_TOKEN` in `HERMES_HOME/.env`; the star ranking itself still comes from GH Archive.
- If GH Archive has not published every hourly file yet, the crawler emits partial results plus `errors`; the cron response should call out partial data instead of inventing repositories.
