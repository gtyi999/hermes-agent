---
name: bilibili-subtitle-download
description: >
  Download subtitles, captions, or transcript files from Bilibili/B站 videos
  without downloading the video media. Use when the user asks for Bilibili
  字幕, CC, transcript, SRT, VTT, or caption files from bilibili.com, b23.tv,
  BV/av IDs, or bangumi ep/ss links.
---

# Bilibili Subtitle Download

Download Bilibili subtitles with `yt-dlp` while skipping the video/audio media.

## Boundaries

Only download subtitles the user owns, controls, or is authorized to save. Do
not bypass DRM, paywalls, private access, region restrictions, or membership
requirements. If subtitles require login cookies, ask the user to provide a
cookie file or approve browser-cookie access; never ask for passwords.

## Setup

```bash
source venv/bin/activate  # if working inside the Hermes repo
python -m pip install -U yt-dlp
```

`ffmpeg` may be needed only when converting subtitle formats with
`--convert-to`, such as converting to SRT.

## Helper Script

`SKILL_DIR` is the directory containing this `SKILL.md`.

```bash
# Download available Chinese/English subtitles into ./downloads/bilibili-subtitles
python3 SKILL_DIR/scripts/download_bilibili_subtitles.py "https://www.bilibili.com/video/BV..."

# Save as SRT when conversion is available
python3 SKILL_DIR/scripts/download_bilibili_subtitles.py "URL" --convert-to srt

# List available subtitle tracks before downloading
python3 SKILL_DIR/scripts/download_bilibili_subtitles.py "URL" --list-subs

# Authenticated subtitles with an exported Netscape cookie file
python3 SKILL_DIR/scripts/download_bilibili_subtitles.py "URL" --cookies /path/to/cookies.txt

# Use browser cookies, e.g. chrome, chromium, edge, firefox
python3 SKILL_DIR/scripts/download_bilibili_subtitles.py "URL" --cookies-from-browser chrome

# Preview the exact yt-dlp command without downloading
python3 SKILL_DIR/scripts/download_bilibili_subtitles.py "URL" --dry-run
```

Accepted inputs include full `bilibili.com` URLs, `b23.tv` short links,
scheme-less URLs such as `www.bilibili.com/video/BV...`, raw `BV...` IDs, raw
`av...` IDs, and bangumi `ep...`/`ss...` IDs.

## Workflow

1. Confirm the Bilibili URL or ID is present. If missing, ask the user for it.
2. If the user does not specify a language, use the default Chinese/English
   fallback set. Use `--list-subs` first if they need a specific track.
3. Run the helper script. Add `--convert-to srt` only when the user asks for
   SRT or another explicit subtitle format.
4. Use `--cookies` or `--cookies-from-browser` only when the page requires
   authentication or subtitles are visible in the browser but unavailable
   anonymously.
5. Report the output directory (`./downloads/bilibili-subtitles` by default),
   the requested format, and any important limitation.

## Common Failures

- **No subtitles listed**: retry with `--list-subs`; if still empty, tell the
  user the video likely has subtitles disabled or hidden behind login.
- **Login required**: retry with `--cookies` or `--cookies-from-browser`.
- **Conversion failed**: install `ffmpeg` or rerun without `--convert-to` to
  keep the subtitle format provided by Bilibili/yt-dlp.
- **b23.tv redirect fails**: open the short link in a browser and retry with
  the expanded `bilibili.com` URL.
- **Region/private/member-only restriction**: do not bypass access controls;
  ask the user for an authorized URL or cookies.
