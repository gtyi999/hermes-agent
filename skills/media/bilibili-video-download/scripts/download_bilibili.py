#!/usr/bin/env python3
"""Download an authorized Bilibili video using yt-dlp.

This is a thin, safe wrapper around yt-dlp. It avoids shell interpolation,
keeps defaults predictable, and prints a small JSON summary after completion.
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
from urllib.parse import urlparse


DEFAULT_OUTPUT_DIR = Path("downloads") / "bilibili"
DEFAULT_TEMPLATE = "%(title).200B [%(id)s].%(ext)s"
DEFAULT_FORMAT = "b[acodec!=none][vcodec!=none]/best[acodec!=none][vcodec!=none]"
BEST_QUALITY_FORMAT = "bv*[vcodec!=none]+ba[acodec!=none]/bv*+ba/b[acodec!=none][vcodec!=none]"
AUDIO_ONLY_FORMAT = "ba[acodec!=none]/bestaudio/b"
ALLOWED_HOSTS = ("bilibili.com", "b23.tv", "acg.tv")
BVID_RE = re.compile(r"^BV[0-9A-Za-z]{10}$", re.IGNORECASE)
AVID_RE = re.compile(r"^av(\d+)$", re.IGNORECASE)
BANGUMI_ID_RE = re.compile(r"^(ep|ss)(\d+)$", re.IGNORECASE)


def _yt_dlp_command() -> list[str] | None:
    """Return a command prefix for yt-dlp, preferring the active Python env."""
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    return None


def _ffmpeg_command() -> str | None:
    return shutil.which("ffmpeg")


def _require_ffmpeg(reason: str) -> None:
    if _ffmpeg_command() is None:
        raise RuntimeError(
            f"{reason}. ffmpeg is not installed or not on PATH. "
            "Install ffmpeg, then retry."
        )


def _format_needs_merge(format_selector: str) -> bool:
    return "+" in format_selector


def _is_allowed_host(host: str) -> bool:
    host = host.lower()
    return any(
        host == allowed or host.endswith("." + allowed)
        for allowed in ALLOWED_HOSTS
    )


def _normalize_bilibili_input(value: str) -> str:
    """Normalize common Bilibili inputs into URLs yt-dlp understands."""
    raw = value.strip()
    if not raw:
        raise ValueError("URL cannot be empty.")

    if BVID_RE.fullmatch(raw):
        return f"https://www.bilibili.com/video/{raw}"

    avid = AVID_RE.fullmatch(raw)
    if avid:
        return f"https://www.bilibili.com/video/av{avid.group(1)}"

    bangumi_id = BANGUMI_ID_RE.fullmatch(raw)
    if bangumi_id:
        kind, numeric_id = bangumi_id.groups()
        return f"https://www.bilibili.com/bangumi/play/{kind.lower()}{numeric_id}"

    if raw.startswith("//"):
        return f"https:{raw}"

    parsed = urlparse(raw)
    if parsed.scheme:
        return raw

    candidate_host = raw.split("/", 1)[0].split("?", 1)[0].lower()
    if _is_allowed_host(candidate_host):
        return f"https://{raw}"

    return raw


def _looks_like_bilibili_url(value: str) -> bool:
    try:
        normalized = _normalize_bilibili_input(value)
    except ValueError:
        return False
    parsed = urlparse(normalized)
    host = (parsed.netloc or "").lower()
    return _is_allowed_host(host)


def _build_command(args: argparse.Namespace) -> list[str]:
    prefix = _yt_dlp_command()
    if prefix is None:
        raise RuntimeError(
            "yt-dlp is not installed. Run: python -m pip install -U yt-dlp"
        )

    output_dir = Path(args.output_dir).expanduser()
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    url = _normalize_bilibili_input(args.url)
    selected_format = args.format
    if args.best_quality and args.format == DEFAULT_FORMAT:
        selected_format = BEST_QUALITY_FORMAT
    if args.audio_only and args.format == DEFAULT_FORMAT:
        selected_format = AUDIO_ONLY_FORMAT

    if not getattr(args, "list_formats", False):
        if args.audio_only:
            _require_ffmpeg("Audio extraction/conversion requires ffmpeg")
        elif _format_needs_merge(selected_format):
            _require_ffmpeg("Best-quality video/audio merging requires ffmpeg")

    cmd = [
        *prefix,
        "--newline",
        "--no-playlist" if not args.playlist else "--yes-playlist",
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
        "--referer",
        "https://www.bilibili.com/",
    ]

    if not args.audio_only and _format_needs_merge(selected_format):
        cmd.extend(["--merge-output-format", args.merge_format])
    if args.cookies:
        cookies_path = Path(args.cookies).expanduser()
        if not cookies_path.is_file():
            raise RuntimeError(f"Cookie file not found: {cookies_path}")
        cmd.extend(["--cookies", str(cookies_path)])
    if args.cookies_from_browser:
        cmd.extend(["--cookies-from-browser", args.cookies_from_browser])
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
    if args.proxy:
        cmd.extend(["--proxy", args.proxy])
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
        description="Download an authorized Bilibili video with yt-dlp."
    )
    parser.add_argument(
        "url",
        help="Bilibili URL, b23.tv short link, BV/av ID, or episode URL",
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
        help="Container used after merging with --best-quality",
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
        default="zh-Hans,zh-Hant,en.*",
        help="Subtitle language selector",
    )
    parser.add_argument("--thumbnail", action="store_true", help="Download thumbnail")
    parser.add_argument(
        "--info-json",
        action="store_true",
        help="Write yt-dlp metadata JSON",
    )
    parser.add_argument(
        "--best-quality",
        action="store_true",
        help="Download separate best video/audio streams and merge with ffmpeg",
    )
    parser.add_argument(
        "--playlist",
        action="store_true",
        help="Allow playlist/series downloads",
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

    if not _looks_like_bilibili_url(args.url):
        print(
            json.dumps(
                {
                    "warning": (
                        "The URL does not look like bilibili.com, b23.tv, "
                        "or acg.tv."
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
