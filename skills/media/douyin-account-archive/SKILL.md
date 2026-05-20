---
name: douyin-account-archive
description: >
  Archive public videos from a user-authorized Douyin account/profile URL. Use
  when the user wants to collect an account's public video list, download video
  files and covers, and generate structured manifests with titles, publish time,
  interaction counts, metadata paths, and a download report.
---

# Douyin Account Archive

Archive public videos from a Douyin account that the user is authorized to
access. The bundled helper uses `yt-dlp`, keeps auth values out of printed
commands, writes per-video metadata, and generates JSON, CSV, and Markdown
reports.

## Boundaries

- Use only for accounts/videos the user owns, manages, has permission to
  archive, or that are otherwise authorized for local archival.
- Do not bypass DRM, paywalls, private access, account restrictions, CAPTCHA,
  region restrictions, or platform access controls.
- Prefer a Netscape-format `cookies.txt` file exported by the user, or
  `--cookies-from-browser` after explicit user approval. Never ask for
  passwords.
- Only archive public videos exposed by the provided profile/account URL unless
  the user supplies additional authorized URLs.

## Setup

```bash
source venv/bin/activate  # if working inside the Hermes repo
python -m pip install -U yt-dlp
ffmpeg -version           # recommended for merged video formats
```

## Quick Start

```bash
python skills/media/douyin-account-archive/scripts/archive_douyin_account.py \
  "https://www.douyin.com/user/MS4wLjAB..." \
  --cookies /path/to/cookies.txt \
  --output-dir archives/douyin/account-name
```

Browser-cookie mode is also supported after user approval:

```bash
python skills/media/douyin-account-archive/scripts/archive_douyin_account.py \
  "https://www.douyin.com/user/MS4wLjAB..." \
  --cookies-from-browser chrome \
  --output-dir archives/douyin/account-name
```

## Configuration File

For repeatable archives, put options in JSON or YAML and pass `--config`:

```json
{
  "account_url": "https://www.douyin.com/user/MS4wLjAB...",
  "output_dir": "archives/douyin/account-name",
  "cookies": "/path/to/cookies.txt",
  "max_videos": 100,
  "date_after": "20240101",
  "date_before": "20241231",
  "rate_limit": "2M",
  "sleep_interval": 1,
  "max_sleep_interval": 5
}
```

CLI flags override config values.

## Outputs

The helper creates these paths under `--output-dir`:

- `videos/` - downloaded video files
- `covers/` - downloaded thumbnails/covers
- `metadata/` - `yt-dlp` `.info.json` files
- `reports/discovered.json` - optional account listing probe
- `reports/manifest.json` - structured machine-readable manifest
- `reports/manifest.csv` - tabular manifest for spreadsheets
- `reports/download-report.md` - human-readable result report
- `reports/download-archive.txt` - `yt-dlp` archive file for incremental reruns

Each manifest item includes available title, publish date/time, URL, uploader,
duration, interaction counters, and relative file paths for the video, cover,
and info JSON.

## Useful Options

- `--max-videos N` limits how many account videos are processed.
- `--metadata-only` writes metadata and covers without media files.
- `--no-cover` skips thumbnail/cover downloads.
- `--date-after YYYYMMDD` and `--date-before YYYYMMDD` restrict archive dates.
- `--match-filter EXPR` passes a `yt-dlp` match filter.
- `--video-template`, `--cover-template`, and `--info-template` customize
  archive layout.
- `--dry-run` prints the planned commands and paths without writing files.

If Douyin changes its web extraction behavior, update `yt-dlp` first, then
retry with fresh authorized cookies.
