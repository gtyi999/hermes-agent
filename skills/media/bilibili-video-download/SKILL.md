---
name: bilibili-video-download
description: >
  Download Bilibili video/audio media from bilibili.com or b23.tv links when
  the user asks to save an authorized B站/Bilibili video locally. Use for
  video media downloads from Bilibili URLs, BV/av links, bangumi episode links,
  or shortened b23.tv links; use the Bilibili subtitle skill for subtitles-only
  requests.
---

# Bilibili Video Download

Download Bilibili videos with `yt-dlp`, preserving title metadata and merging
video/audio with `ffmpeg` when needed.

## Boundaries

Only download videos the user owns, controls, or is authorized to save. Do not
bypass DRM, paywalls, private access, or platform restrictions. If a video needs
login cookies, ask the user to provide a cookie file or approve browser-cookie
access; never ask for passwords.

## Setup

```bash
source venv/bin/activate  # if working inside the Hermes repo
python -m pip install -U yt-dlp
ffmpeg -version
```

`ffmpeg` is needed for Bilibili DASH streams because video and audio are often
downloaded separately and merged.

## Helper Script

`SKILL_DIR` is the directory containing this `SKILL.md`.

```bash
# Basic download into ./downloads/bilibili
python3 SKILL_DIR/scripts/download_bilibili.py "https://www.bilibili.com/video/BV..."

# Authenticated download with an exported Netscape cookie file
python3 SKILL_DIR/scripts/download_bilibili.py "URL" --cookies /path/to/cookies.txt

# Use browser cookies, e.g. chrome, chromium, edge, firefox
python3 SKILL_DIR/scripts/download_bilibili.py "URL" --cookies-from-browser chrome

# Include subtitles and thumbnail
python3 SKILL_DIR/scripts/download_bilibili.py "URL" --subtitles --thumbnail

# Preview the exact yt-dlp command without downloading
python3 SKILL_DIR/scripts/download_bilibili.py "URL" --dry-run
```

Accepted inputs include full `bilibili.com` URLs, `b23.tv` short links, scheme-less
URLs such as `www.bilibili.com/video/BV...`, raw `BV...` IDs, raw `av...` IDs,
and bangumi `ep...`/`ss...` IDs.

## Workflow

1. Confirm the Bilibili URL is present. If missing, ask the user for it.
2. Use `--dry-run` if the request is ambiguous or needs review.
3. Run the helper script. Prefer `--cookies` or `--cookies-from-browser` only
   when the video requires authentication or better quality requires login.
4. If `yt-dlp` is missing, install it in the active environment and retry.
5. If merging fails, install or locate `ffmpeg`, then retry.
6. Report the output directory (`./downloads/bilibili` by default) and any
   important limitation, such as login required, region restriction,
   unavailable video, or permission denied.

## Common Failures

- **Login required or low quality only**: retry with `--cookies` or
  `--cookies-from-browser`.
- **`ffmpeg` missing**: install `ffmpeg`; without it, DASH video/audio merge
  may fail.
- **b23.tv redirect fails**: open the short link in a browser and retry with
  the expanded `bilibili.com` URL.
- **Region/private/member-only restriction**: do not bypass access controls;
  ask the user for an authorized URL or cookies.
