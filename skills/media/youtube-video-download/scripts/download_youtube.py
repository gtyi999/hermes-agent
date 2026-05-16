#!/usr/bin/env python3
"""Download an authorized YouTube video using yt-dlp.

This is a thin wrapper around yt-dlp. It avoids shell interpolation, prevents
accidental playlist downloads by default, and prints a small JSON summary.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlunparse


DEFAULT_OUTPUT_DIR = Path("downloads") / "youtube"
DEFAULT_TEMPLATE = "%(title).200B [%(id)s].%(ext)s"
DEFAULT_FORMAT = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
DEFAULT_SUB_LANGS = "en.*,zh-Hans,zh-Hant,zh-CN,zh-TW"
ALLOWED_HOSTS = ("youtube.com", "youtube-nocookie.com", "youtu.be")
VIDEO_ID_RE = re.compile(r"^[0-9A-Za-z_-]{11}$")


def _yt_dlp_command() -> list[str] | None:
    """Return a command prefix for yt-dlp, preferring the active Python env."""
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    return None


def _is_allowed_host(host: str) -> bool:
    host = host.lower()
    return any(
        host == allowed or host.endswith("." + allowed)
        for allowed in ALLOWED_HOSTS
    )


def _extract_video_id(parsed) -> str | None:
    host = (parsed.netloc or "").lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)

    if "v" in query and query["v"]:
        candidate = query["v"][0]
        if VIDEO_ID_RE.fullmatch(candidate):
            return candidate

    if host == "youtu.be" and path_parts:
        candidate = path_parts[0]
        if VIDEO_ID_RE.fullmatch(candidate):
            return candidate

    if path_parts and path_parts[0] in {"shorts", "embed", "live"}:
        if len(path_parts) > 1 and VIDEO_ID_RE.fullmatch(path_parts[1]):
            return path_parts[1]

    return None


def _canonical_video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _ensure_scheme(value: str) -> str:
    if value.startswith("//"):
        return f"https:{value}"
    parsed = urlparse(value)
    if parsed.scheme:
        return value
    candidate_host = value.split("/", 1)[0].split("?", 1)[0].lower()
    if _is_allowed_host(candidate_host):
        return f"https://{value}"
    return value


def _normalize_youtube_input(value: str, *, preserve_playlist: bool = False) -> str:
    """Normalize common YouTube inputs into URLs yt-dlp understands."""
    raw = value.strip()
    if not raw:
        raise ValueError("URL cannot be empty.")

    if VIDEO_ID_RE.fullmatch(raw):
        return _canonical_video_url(raw)

    candidate = _ensure_scheme(raw)
    parsed = urlparse(candidate)

    if parsed.scheme and _is_allowed_host(parsed.netloc or ""):
        if preserve_playlist:
            return urlunparse(parsed)
        video_id = _extract_video_id(parsed)
        if video_id:
            return _canonical_video_url(video_id)
        return urlunparse(parsed)

    return candidate


def _looks_like_youtube_url(value: str) -> bool:
    try:
        normalized = _normalize_youtube_input(value, preserve_playlist=True)
    except ValueError:
        return False
    parsed = urlparse(normalized)
    host = (parsed.netloc or "").lower()
    return bool(VIDEO_ID_RE.fullmatch(value.strip())) or _is_allowed_host(host)


def _add_auth_args(cmd: list[str], args: argparse.Namespace) -> None:
    if args.cookies:
        cookies_path = Path(args.cookies).expanduser()
        if not cookies_path.is_file():
            raise RuntimeError(f"Cookie file not found: {cookies_path}")
        cmd.extend(["--cookies", str(cookies_path)])
    if args.cookies_from_browser:
        cmd.extend(["--cookies-from-browser", args.cookies_from_browser])
    if args.proxy:
        cmd.extend(["--proxy", args.proxy])


def _build_command(args: argparse.Namespace) -> list[str]:
    prefix = _yt_dlp_command()
    if prefix is None:
        raise RuntimeError(
            "yt-dlp is not installed. Run: python -m pip install -U yt-dlp"
        )

    url = _normalize_youtube_input(args.url, preserve_playlist=args.playlist)
    output_dir = Path(args.output_dir).expanduser()
    if not args.dry_run and not args.list_formats:
        output_dir.mkdir(parents=True, exist_ok=True)

    selected_format = args.format
    if args.audio_only and args.format == DEFAULT_FORMAT:
        selected_format = "ba/b"

    cmd = [
        *prefix,
        "--newline",
        "--no-playlist" if not args.playlist else "--yes-playlist",
    ]

    _add_auth_args(cmd, args)

    if args.list_formats:
        cmd.append("--list-formats")
    else:
        cmd.extend([
            "--paths",
            str(output_dir),
            "-o",
            args.template,
            "-f",
            selected_format,
            "--retries",
            str(args.retries),
            "--fragment-retries",
            str(args.fragment_retries),
            "--concurrent-fragments",
            str(args.concurrent_fragments),
        ])
        if not args.audio_only:
            cmd.extend(["--merge-output-format", args.merge_format])
        if args.subtitles:
            cmd.extend([
                "--write-subs",
                "--write-auto-subs",
                "--sub-langs",
                args.sub_langs,
            ])
        if args.thumbnail:
            cmd.append("--write-thumbnail")
        if args.info_json:
            cmd.append("--write-info-json")
        if args.write_description:
            cmd.append("--write-description")
        if args.rate_limit:
            cmd.extend(["--limit-rate", args.rate_limit])
        if args.max_filesize:
            cmd.extend(["--max-filesize", args.max_filesize])
        if args.audio_only:
            cmd.extend(["-x", "--audio-format", args.audio_format])

    cmd.append(url)
    return cmd


def _redacted_command(cmd: list[str]) -> str:
    redacted: list[str] = []
    skip_next = False
    secret_flags = {"--cookies", "--cookies-from-browser", "--proxy"}
    for idx, part in enumerate(cmd):
        if skip_next:
            redacted.append("<redacted>")
            skip_next = False
            continue
        redacted.append(part)
        if part in secret_flags and idx < len(cmd) - 1:
            skip_next = True
    return shlex.join(redacted)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download an authorized YouTube video with yt-dlp."
    )
    parser.add_argument(
        "url",
        help="YouTube URL, youtu.be short link, Shorts URL, embed URL, or video ID",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Download directory",
    )
    parser.add_argument(
        "--template",
        default=DEFAULT_TEMPLATE,
        help="yt-dlp output filename template",
    )
    parser.add_argument(
        "--format",
        default=DEFAULT_FORMAT,
        help="yt-dlp format selector",
    )
    parser.add_argument(
        "--merge-format",
        default="mp4",
        help="Container used after merging",
    )
    parser.add_argument("--cookies", help="Path to a Netscape-format cookies.txt file")
    parser.add_argument(
        "--cookies-from-browser",
        help="Browser cookie source, e.g. chrome, chromium, edge, firefox",
    )
    parser.add_argument(
        "--subtitles",
        action="store_true",
        help="Download available subtitles",
    )
    parser.add_argument(
        "--sub-langs",
        default=DEFAULT_SUB_LANGS,
        help="Subtitle language selector",
    )
    parser.add_argument("--thumbnail", action="store_true", help="Download thumbnail")
    parser.add_argument(
        "--info-json",
        action="store_true",
        help="Write yt-dlp metadata JSON",
    )
    parser.add_argument(
        "--write-description",
        action="store_true",
        help="Write the YouTube description text",
    )
    parser.add_argument(
        "--playlist",
        action="store_true",
        help="Allow playlist downloads; disabled by default",
    )
    parser.add_argument(
        "--list-formats",
        action="store_true",
        help="List available formats without downloading",
    )
    parser.add_argument("--proxy", help="Proxy URL passed to yt-dlp")
    parser.add_argument("--rate-limit", help="Rate limit, e.g. 2M")
    parser.add_argument(
        "--max-filesize",
        help="Abort if media exceeds this size, e.g. 2G",
    )
    parser.add_argument(
        "--audio-only",
        action="store_true",
        help="Extract audio instead of video",
    )
    parser.add_argument(
        "--audio-format",
        default="mp3",
        help="Audio format for --audio-only",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=10,
        help="Whole-download retry count",
    )
    parser.add_argument(
        "--fragment-retries",
        type=int,
        default=10,
        help="Fragment retry count",
    )
    parser.add_argument(
        "--concurrent-fragments",
        type=int,
        default=4,
        help="Parallel fragment downloads",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print command without running it",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    if not _looks_like_youtube_url(args.url):
        print(
            json.dumps(
                {
                    "warning": (
                        "The URL does not look like youtube.com, "
                        "youtube-nocookie.com, youtu.be, or a video ID."
                    ),
                    "url": args.url,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )

    try:
        cmd = _build_command(args)
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 2

    summary = {
        "output_dir": str(Path(args.output_dir).expanduser()),
        "dry_run": bool(args.dry_run),
        "playlist": bool(args.playlist),
        "list_formats": bool(args.list_formats),
        "normalized_url": _normalize_youtube_input(
            args.url,
            preserve_playlist=args.playlist,
        ),
        "command": _redacted_command(cmd),
    }

    if args.dry_run:
        print(json.dumps({"success": True, **summary}, ensure_ascii=False, indent=2))
        return 0

    print("Running:", _redacted_command(cmd), flush=True)
    proc = subprocess.run(cmd)
    success = proc.returncode == 0
    print(
        json.dumps(
            {
                "success": success,
                "exit_code": proc.returncode,
                **summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
