#!/usr/bin/env python3
"""Download authorized Bilibili subtitles using yt-dlp.

This wrapper skips media downloads, keeps defaults predictable, and prints a
small JSON summary after completion.
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


DEFAULT_OUTPUT_DIR = Path("downloads") / "bilibili-subtitles"
DEFAULT_TEMPLATE = "%(title).200B [%(id)s].%(ext)s"
DEFAULT_SUB_LANGS = "zh-Hans,zh-Hant,zh-CN,zh-TW,en.*"
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

    url = _normalize_bilibili_input(args.url)
    output_dir = Path(args.output_dir).expanduser()
    if not args.dry_run and not args.list_subs:
        output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        *prefix,
        "--newline",
        "--no-playlist" if not args.playlist else "--yes-playlist",
        "--referer",
        "https://www.bilibili.com/",
    ]

    _add_auth_args(cmd, args)

    if args.list_subs:
        cmd.append("--list-subs")
    else:
        cmd.extend([
            "--skip-download",
            "--paths",
            str(output_dir),
            "-o",
            args.template,
        ])
        if not args.auto_only:
            cmd.append("--write-subs")
        if not args.manual_only:
            cmd.append("--write-auto-subs")
        cmd.extend(["--sub-langs", args.sub_langs])
        if args.sub_format:
            cmd.extend(["--sub-format", args.sub_format])
        if args.convert_to:
            cmd.extend(["--convert-subs", args.convert_to])
        if args.info_json:
            cmd.append("--write-info-json")

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
        description="Download authorized Bilibili subtitles with yt-dlp."
    )
    parser.add_argument(
        "url",
        help="Bilibili URL, b23.tv short link, BV/av ID, or episode URL",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Subtitle download directory",
    )
    parser.add_argument(
        "--template",
        default=DEFAULT_TEMPLATE,
        help="yt-dlp output filename template",
    )
    parser.add_argument(
        "--sub-langs",
        default=DEFAULT_SUB_LANGS,
        help="Subtitle language selector, e.g. zh-Hans,en.* or all",
    )
    parser.add_argument(
        "--sub-format",
        default="best",
        help="Preferred subtitle source format passed to yt-dlp",
    )
    parser.add_argument(
        "--convert-to",
        help="Convert subtitles to this format, e.g. srt, vtt, ass, or lrc",
    )
    parser.add_argument(
        "--manual-only",
        action="store_true",
        help="Download only uploader/manual subtitles",
    )
    parser.add_argument(
        "--auto-only",
        action="store_true",
        help="Download only automatic subtitles",
    )
    parser.add_argument(
        "--list-subs",
        action="store_true",
        help="List available subtitle tracks without downloading",
    )
    parser.add_argument("--cookies", help="Path to a Netscape-format cookies.txt file")
    parser.add_argument(
        "--cookies-from-browser",
        help="Browser cookie source, e.g. chrome, chromium, edge, firefox",
    )
    parser.add_argument(
        "--playlist",
        action="store_true",
        help="Allow playlist/series subtitle downloads",
    )
    parser.add_argument(
        "--info-json",
        action="store_true",
        help="Write yt-dlp metadata JSON alongside subtitles",
    )
    parser.add_argument("--proxy", help="Proxy URL passed to yt-dlp")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print command without running it",
    )

    args = parser.parse_args(argv)
    if args.manual_only and args.auto_only:
        parser.error("--manual-only and --auto-only cannot be used together")
    return args


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
        "list_subs": bool(args.list_subs),
        "sub_langs": args.sub_langs,
        "convert_to": args.convert_to,
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
