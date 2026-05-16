---
name: youtube-video-download
description: >
  Download YouTube video or audio media from youtube.com, music.youtube.com,
  youtube-nocookie.com, or youtu.be links when the user asks to save an
  authorized YouTube video locally. Use for YouTube video downloads from watch
  URLs, youtu.be links, Shorts, embeds, live links, or raw video IDs; use the
  YouTube content skill for transcript, summary, or content transformation
  requests.
---

# YouTube Video Download

Download YouTube videos with `yt-dlp`, preserving title metadata. The default
mode prefers a single file that already contains both video and audio so the
result plays with sound even when `ffmpeg` is not installed.

## Boundaries

Only download videos the user owns, controls, has permission to save, or that
are otherwise authorized for local download. Do not bypass DRM, paywalls,
private access, age gates, region restrictions, or platform access controls. If
a video needs login cookies, ask the user to provide a cookie file or approve
browser-cookie access; never ask for passwords.

## Setup

```bash
source venv/bin/activate  # if working inside the Hermes repo
python -m pip install -U yt-dlp
ffmpeg -version  # required for --best-quality or --audio-only
```

`ffmpeg` is needed only when using `--best-quality` to merge separate
video/audio streams, or when extracting/converting audio with `--audio-only`.

## Helper Script

`SKILL_DIR` is the directory containing this `SKILL.md`.

```bash
# Basic single-video download into ./downloads/youtube
python3 SKILL_DIR/scripts/download_youtube.py "https://www.youtube.com/watch?v=Ee-7aHmfhAk&list=RDEe-7aHmfhAk&start_radio=1"

# Highest quality download; requires ffmpeg for audio/video merging
python3 SKILL_DIR/scripts/download_youtube.py "URL" --best-quality

# Authenticated download with an exported Netscape cookie file
python3 SKILL_DIR/scripts/download_youtube.py "URL" --cookies /path/to/cookies.txt

# Use browser cookies, e.g. chrome, chromium, edge, firefox
python3 SKILL_DIR/scripts/download_youtube.py "URL" --cookies-from-browser chrome

# Download audio only
python3 SKILL_DIR/scripts/download_youtube.py "URL" --audio-only --audio-format mp3

# Include subtitles and thumbnail
python3 SKILL_DIR/scripts/download_youtube.py "URL" --subtitles --thumbnail

# Preview the exact yt-dlp command without downloading
python3 SKILL_DIR/scripts/download_youtube.py "URL" --dry-run
```

Accepted inputs include full YouTube URLs, `youtu.be` short links, scheme-less
URLs such as `www.youtube.com/watch?v=...`, Shorts URLs, embed URLs, live URLs,
and raw 11-character YouTube video IDs.

By default, the helper downloads exactly one video. For watch URLs that contain
playlist parameters such as `list=RD...`, it extracts the `v=` video ID and drops
playlist/radio parameters. Use `--playlist` only when the user explicitly asks
to download a playlist.

## Workflow

1. Confirm the YouTube URL or video ID is present. If missing, ask the user for
   it.
2. Use `--dry-run` if the request is ambiguous or needs review.
3. Run the helper script. Prefer `--cookies` or `--cookies-from-browser` only
   when the video requires authentication or better quality requires login.
4. Add `--best-quality` only when the user prioritizes maximum quality over
   no-setup playback, and confirm `ffmpeg` is installed.
5. Add `--playlist` only when the user asks for playlist download.
6. If `yt-dlp` is missing, install it in the active environment and retry.
7. If merging fails, install or locate `ffmpeg`, then retry with
   `--best-quality`.
8. Report the output directory (`./downloads/youtube` by default) and any
   important limitation, such as login required, unavailable video, region
   restriction, or permission denied.

## Common Failures

- **Playlist/radio URL downloads too much**: rerun without `--playlist`; the
  default behavior should download only the `v=` video.
- **Downloaded file has no sound**: rerun with the default format, not a custom
  `bestvideo`/video-only selector. For maximum quality, install `ffmpeg` and use
  `--best-quality` so separate audio and video streams are merged.
- **Login, age, or membership required**: retry with `--cookies` or
  `--cookies-from-browser` only if the user has authorized access.
- **`ffmpeg` missing**: default video downloads still work, but
  `--best-quality` and `--audio-only` require `ffmpeg`.
- **Format unavailable**: run `--list-formats`, then retry with an explicit
  `--format` selector.
- **Private, region-restricted, or removed video**: do not bypass access
  controls; ask the user for an authorized URL or cookies.
