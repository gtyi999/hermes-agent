#!/usr/bin/env python3
"""Archive public videos from an authorized Douyin account using yt-dlp."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_OUTPUT_DIR = Path("archives") / "douyin"
DEFAULT_FORMAT = (
    "b[ext=mp4][acodec!=none][vcodec!=none]/"
    "b[acodec!=none][vcodec!=none]/best"
)
DEFAULT_VIDEO_TEMPLATE = (
    "videos/%(upload_date|unknown-date)s_%(id)s_%(title).120B.%(ext)s"
)
DEFAULT_COVER_TEMPLATE = (
    "covers/%(upload_date|unknown-date)s_%(id)s_%(title).120B.%(ext)s"
)
DEFAULT_INFO_TEMPLATE = (
    "metadata/%(upload_date|unknown-date)s_%(id)s_%(title).120B.info.json"
)
ALLOWED_HOSTS = (
    "douyin.com",
    "v.douyin.com",
    "iesdouyin.com",
    "douyinvod.com",
)
SEC_USER_ID_RE = re.compile(r"^MS4wLjAB[0-9A-Za-z_.-]+$")
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".flv", ".avi", ".m4v"}
COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
DEFAULTS: dict[str, Any] = {
    "account_url": None,
    "output_dir": str(DEFAULT_OUTPUT_DIR),
    "format": DEFAULT_FORMAT,
    "video_template": DEFAULT_VIDEO_TEMPLATE,
    "cover_template": DEFAULT_COVER_TEMPLATE,
    "info_template": DEFAULT_INFO_TEMPLATE,
    "cookies": None,
    "cookies_from_browser": None,
    "proxy": None,
    "rate_limit": None,
    "max_filesize": None,
    "max_videos": None,
    "date_after": None,
    "date_before": None,
    "match_filter": None,
    "cover": True,
    "metadata_only": False,
    "skip_probe": False,
    "allow_unauthenticated": False,
    "retries": 10,
    "fragment_retries": 10,
    "concurrent_fragments": 4,
    "sleep_interval": None,
    "max_sleep_interval": None,
    "dry_run": False,
}


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
    return any(host == allowed or host.endswith("." + allowed) for allowed in ALLOWED_HOSTS)


def _normalize_douyin_input(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("Account URL cannot be empty.")

    if SEC_USER_ID_RE.fullmatch(raw):
        return f"https://www.douyin.com/user/{raw}"

    if raw.startswith("//"):
        return f"https:{raw}"

    parsed = urlparse(raw)
    if parsed.scheme:
        return raw

    candidate_host = raw.split("/", 1)[0].split("?", 1)[0].lower()
    if _is_allowed_host(candidate_host):
        return f"https://{raw}"

    return raw


def _looks_like_douyin_url(value: str) -> bool:
    try:
        normalized = _normalize_douyin_input(value)
    except ValueError:
        return False
    parsed = urlparse(normalized)
    return _is_allowed_host(parsed.netloc or "")


def _load_config_file(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}

    path = Path(path_value).expanduser()
    if not path.is_file():
        raise RuntimeError(f"Config file not found: {path}")

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except Exception as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("YAML config requires PyYAML to be installed.") from exc
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text or "{}")

    if not isinstance(data, dict):
        raise RuntimeError("Config file must contain an object/dictionary.")
    return data


def _cli_values(args: argparse.Namespace) -> dict[str, Any]:
    return {key: value for key, value in vars(args).items() if key != "config" and value is not None}


def _resolve_options(args: argparse.Namespace) -> dict[str, Any]:
    config = _load_config_file(getattr(args, "config", None))
    unknown = sorted(set(config) - set(DEFAULTS))
    if unknown:
        raise RuntimeError(f"Unknown config keys: {', '.join(unknown)}")

    options = {**DEFAULTS, **config, **_cli_values(args)}
    if not options.get("account_url"):
        raise RuntimeError("Provide a Douyin account URL or sec_user_id.")

    options["account_url"] = _normalize_douyin_input(str(options["account_url"]))
    if not _looks_like_douyin_url(options["account_url"]):
        raise RuntimeError("The account URL does not look like a Douyin URL.")

    if not options.get("allow_unauthenticated"):
        if not options.get("cookies") and not options.get("cookies_from_browser"):
            raise RuntimeError(
                "Authorized Douyin access is required. Provide --cookies, "
                "--cookies-from-browser, or explicitly pass --allow-unauthenticated."
            )

    if options.get("cookies"):
        cookies_path = Path(str(options["cookies"])).expanduser()
        if not cookies_path.is_file():
            raise RuntimeError(f"Cookie file not found: {cookies_path}")
        options["cookies"] = str(cookies_path)

    if options.get("max_videos") is not None:
        options["max_videos"] = int(options["max_videos"])
        if options["max_videos"] <= 0:
            raise RuntimeError("--max-videos must be greater than 0.")

    return options


def _add_auth_args(cmd: list[str], options: dict[str, Any]) -> None:
    if options.get("cookies"):
        cmd.extend(["--cookies", str(options["cookies"])])
    if options.get("cookies_from_browser"):
        cmd.extend(["--cookies-from-browser", str(options["cookies_from_browser"])])
    if options.get("proxy"):
        cmd.extend(["--proxy", str(options["proxy"])])


def _add_filter_args(cmd: list[str], options: dict[str, Any]) -> None:
    if options.get("max_videos"):
        cmd.extend(["--playlist-end", str(options["max_videos"])])
    if options.get("date_after"):
        cmd.extend(["--dateafter", str(options["date_after"])])
    if options.get("date_before"):
        cmd.extend(["--datebefore", str(options["date_before"])])
    if options.get("match_filter"):
        cmd.extend(["--match-filter", str(options["match_filter"])])


def _build_probe_command(options: dict[str, Any]) -> list[str]:
    prefix = _yt_dlp_command()
    if prefix is None:
        raise RuntimeError("yt-dlp is not installed. Run: python -m pip install -U yt-dlp")

    cmd = [
        *prefix,
        "--dump-single-json",
        "--flat-playlist",
        "--skip-download",
        "--yes-playlist",
    ]
    _add_auth_args(cmd, options)
    _add_filter_args(cmd, options)
    cmd.append(str(options["account_url"]))
    return cmd


def _build_download_command(options: dict[str, Any]) -> list[str]:
    prefix = _yt_dlp_command()
    if prefix is None:
        raise RuntimeError("yt-dlp is not installed. Run: python -m pip install -U yt-dlp")

    output_dir = Path(str(options["output_dir"])).expanduser()
    reports_dir = output_dir / "reports"
    cmd = [
        *prefix,
        "--newline",
        "--yes-playlist",
        "--ignore-errors",
        "--paths",
        str(output_dir),
        "-f",
        str(options["format"]),
        "-o",
        f"video:{options['video_template']}",
        "--write-info-json",
        "-o",
        f"infojson:{options['info_template']}",
        "--download-archive",
        str(reports_dir / "download-archive.txt"),
        "--retries",
        str(options["retries"]),
        "--fragment-retries",
        str(options["fragment_retries"]),
        "--concurrent-fragments",
        str(options["concurrent_fragments"]),
    ]

    if options.get("metadata_only"):
        cmd.append("--skip-download")
    if options.get("cover"):
        cmd.extend(["--write-thumbnail", "-o", f"thumbnail:{options['cover_template']}"])
    if options.get("rate_limit"):
        cmd.extend(["--limit-rate", str(options["rate_limit"])])
    if options.get("max_filesize"):
        cmd.extend(["--max-filesize", str(options["max_filesize"])])
    if options.get("sleep_interval") is not None:
        cmd.extend(["--sleep-interval", str(options["sleep_interval"])])
    if options.get("max_sleep_interval") is not None:
        cmd.extend(["--max-sleep-interval", str(options["max_sleep_interval"])])

    _add_auth_args(cmd, options)
    _add_filter_args(cmd, options)
    cmd.append(str(options["account_url"]))
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


def _ensure_output_dirs(output_dir: Path) -> None:
    for name in ("videos", "covers", "metadata", "reports"):
        (output_dir / name).mkdir(parents=True, exist_ok=True)


def _run_probe(options: dict[str, Any], output_dir: Path) -> dict[str, Any] | None:
    if options.get("skip_probe"):
        return None

    cmd = _build_probe_command(options)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    summary: dict[str, Any] = {
        "exit_code": proc.returncode,
        "command": _redacted_command(cmd),
    }
    if proc.returncode == 0 and proc.stdout.strip():
        discovered_path = output_dir / "reports" / "discovered.json"
        discovered_path.write_text(proc.stdout, encoding="utf-8")
        summary["path"] = _relative_path(discovered_path, output_dir)
    else:
        summary["stderr"] = proc.stderr.strip()[-2000:]
    return summary


def _relative_path(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_upload_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    if re.fullmatch(r"\d{8}", text):
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text


def _format_timestamp(value: Any) -> str | None:
    numeric = _safe_int(value)
    if numeric is None:
        return None
    return datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()


def _first_present(info: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = info.get(key)
        if value is not None:
            return value
    return None


def _find_related_file(
    output_dir: Path,
    video_id: str | None,
    extensions: set[str],
    excluded: set[Path],
) -> Path | None:
    if not video_id:
        return None
    matches: list[Path] = []
    for path in output_dir.rglob("*"):
        if not path.is_file() or path in excluded:
            continue
        if path.suffix.lower() in extensions and video_id in path.name:
            matches.append(path)
    return sorted(matches)[0] if matches else None


def _item_from_info(info_path: Path, output_dir: Path) -> dict[str, Any]:
    info = json.loads(info_path.read_text(encoding="utf-8"))
    video_id = str(info.get("id") or "")
    excluded = {info_path}
    video_path = _find_related_file(output_dir, video_id, VIDEO_EXTENSIONS, excluded)
    cover_path = _find_related_file(output_dir, video_id, COVER_EXTENSIONS, excluded)

    interactions = {
        "view_count": _safe_int(info.get("view_count")),
        "like_count": _safe_int(_first_present(info, ["like_count", "digg_count"])),
        "comment_count": _safe_int(info.get("comment_count")),
        "share_count": _safe_int(info.get("share_count")),
        "repost_count": _safe_int(info.get("repost_count")),
        "favorite_count": _safe_int(_first_present(info, ["favorite_count", "collect_count"])),
    }

    return {
        "id": video_id or None,
        "title": info.get("title"),
        "description": info.get("description"),
        "webpage_url": info.get("webpage_url") or info.get("original_url"),
        "uploader": _first_present(info, ["uploader", "creator", "channel"]),
        "uploader_id": _first_present(info, ["uploader_id", "channel_id"]),
        "duration": _safe_int(info.get("duration")),
        "upload_date": _format_upload_date(info.get("upload_date")),
        "timestamp": _format_timestamp(_first_present(info, ["timestamp", "release_timestamp"])),
        "thumbnail": info.get("thumbnail"),
        "interaction": interactions,
        "files": {
            "video": _relative_path(video_path, output_dir),
            "cover": _relative_path(cover_path, output_dir),
            "info_json": _relative_path(info_path, output_dir),
        },
    }


def _collect_manifest_items(output_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for info_path in sorted(output_dir.rglob("*.info.json")):
        try:
            items.append(_item_from_info(info_path, output_dir))
        except Exception as exc:
            items.append(
                {
                    "id": None,
                    "title": None,
                    "error": f"Failed to parse {info_path}: {exc}",
                    "files": {"info_json": _relative_path(info_path, output_dir)},
                }
            )
    return items


def _write_csv_manifest(items: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "id",
        "title",
        "webpage_url",
        "uploader",
        "uploader_id",
        "upload_date",
        "timestamp",
        "duration",
        "view_count",
        "like_count",
        "comment_count",
        "share_count",
        "repost_count",
        "favorite_count",
        "video_path",
        "cover_path",
        "info_json_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            interaction = item.get("interaction") or {}
            files = item.get("files") or {}
            writer.writerow(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "webpage_url": item.get("webpage_url"),
                    "uploader": item.get("uploader"),
                    "uploader_id": item.get("uploader_id"),
                    "upload_date": item.get("upload_date"),
                    "timestamp": item.get("timestamp"),
                    "duration": item.get("duration"),
                    "view_count": interaction.get("view_count"),
                    "like_count": interaction.get("like_count"),
                    "comment_count": interaction.get("comment_count"),
                    "share_count": interaction.get("share_count"),
                    "repost_count": interaction.get("repost_count"),
                    "favorite_count": interaction.get("favorite_count"),
                    "video_path": files.get("video"),
                    "cover_path": files.get("cover"),
                    "info_json_path": files.get("info_json"),
                }
            )


def _write_report(
    *,
    report_path: Path,
    options: dict[str, Any],
    items: list[dict[str, Any]],
    exit_code: int,
    download_command: str,
    probe_summary: dict[str, Any] | None,
) -> None:
    video_count = sum(1 for item in items if (item.get("files") or {}).get("video"))
    cover_count = sum(1 for item in items if (item.get("files") or {}).get("cover"))
    lines = [
        "# Douyin Account Archive Report",
        "",
        f"- Account URL: {options['account_url']}",
        f"- Output directory: {Path(str(options['output_dir'])).expanduser()}",
        f"- Download exit code: {exit_code}",
        f"- Metadata items: {len(items)}",
        f"- Video files matched: {video_count}",
        f"- Cover files matched: {cover_count}",
        f"- Metadata-only mode: {bool(options.get('metadata_only'))}",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Commands",
        "",
        f"- Download: `{download_command}`",
    ]
    if probe_summary:
        lines.append(f"- Probe: `{probe_summary.get('command')}`")
        lines.append(f"- Probe exit code: {probe_summary.get('exit_code')}")
    lines.extend(
        [
            "",
            "## Output Files",
            "",
            "- `reports/manifest.json`",
            "- `reports/manifest.csv`",
            "- `reports/download-report.md`",
            "- `reports/download-archive.txt`",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_outputs(
    *,
    options: dict[str, Any],
    exit_code: int,
    download_command: str,
    probe_summary: dict[str, Any] | None,
) -> dict[str, str]:
    output_dir = Path(str(options["output_dir"])).expanduser()
    reports_dir = output_dir / "reports"
    items = _collect_manifest_items(output_dir)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account_url": options["account_url"],
        "output_dir": str(output_dir),
        "download_exit_code": exit_code,
        "totals": {
            "metadata_items": len(items),
            "video_files": sum(1 for item in items if (item.get("files") or {}).get("video")),
            "cover_files": sum(1 for item in items if (item.get("files") or {}).get("cover")),
        },
        "probe": probe_summary,
        "items": items,
    }

    manifest_json = reports_dir / "manifest.json"
    manifest_csv = reports_dir / "manifest.csv"
    report_md = reports_dir / "download-report.md"
    manifest_json.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_csv_manifest(items, manifest_csv)
    _write_report(
        report_path=report_md,
        options=options,
        items=items,
        exit_code=exit_code,
        download_command=download_command,
        probe_summary=probe_summary,
    )
    return {
        "manifest_json": str(manifest_json),
        "manifest_csv": str(manifest_csv),
        "report": str(report_md),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Archive public videos from an authorized Douyin account."
    )
    parser.set_defaults(
        cover=None,
        metadata_only=None,
        skip_probe=None,
        allow_unauthenticated=None,
        dry_run=None,
    )
    parser.add_argument("account_url", nargs="?", help="Douyin profile URL or sec_user_id")
    parser.add_argument("--config", help="JSON/YAML config file")
    parser.add_argument("--output-dir", help="Archive output directory")
    parser.add_argument("--format", help="yt-dlp format selector")
    parser.add_argument("--video-template", help="yt-dlp video output template")
    parser.add_argument("--cover-template", help="yt-dlp thumbnail output template")
    parser.add_argument("--info-template", help="yt-dlp infojson output template")
    parser.add_argument("--cookies", help="Path to a Netscape-format cookies.txt file")
    parser.add_argument(
        "--cookies-from-browser",
        help="Browser cookie source, e.g. chrome, chromium, edge, firefox",
    )
    parser.add_argument("--proxy", help="Proxy URL passed to yt-dlp")
    parser.add_argument("--rate-limit", help="Rate limit, e.g. 2M")
    parser.add_argument("--max-filesize", help="Abort if media exceeds this size, e.g. 2G")
    parser.add_argument("--max-videos", type=int, help="Maximum account videos to process")
    parser.add_argument("--date-after", help="Only process videos after YYYYMMDD")
    parser.add_argument("--date-before", help="Only process videos before YYYYMMDD")
    parser.add_argument("--match-filter", help="yt-dlp match filter expression")
    parser.add_argument("--no-cover", dest="cover", action="store_false", help="Skip cover download")
    parser.add_argument("--metadata-only", action="store_true", help="Write metadata/covers without video files")
    parser.add_argument("--skip-probe", action="store_true", help="Skip the flat playlist discovery probe")
    parser.add_argument(
        "--allow-unauthenticated",
        action="store_true",
        help="Allow public unauthenticated extraction if the user explicitly approves",
    )
    parser.add_argument("--retries", type=int, help="Whole-download retry count")
    parser.add_argument("--fragment-retries", type=int, help="Fragment retry count")
    parser.add_argument("--concurrent-fragments", type=int, help="Parallel fragment downloads")
    parser.add_argument("--sleep-interval", type=float, help="Minimum sleep between downloads")
    parser.add_argument("--max-sleep-interval", type=float, help="Maximum randomized sleep")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without writing files")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        options = _resolve_options(args)
        download_cmd = _build_download_command(options)
        probe_cmd = None if options.get("skip_probe") else _build_probe_command(options)
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 2

    output_dir = Path(str(options["output_dir"])).expanduser()
    summary = {
        "output_dir": str(output_dir),
        "dry_run": bool(options.get("dry_run")),
        "account_url": options["account_url"],
        "download_command": _redacted_command(download_cmd),
        "probe_command": _redacted_command(probe_cmd) if probe_cmd else None,
    }

    if options.get("dry_run"):
        print(json.dumps({"success": True, **summary}, ensure_ascii=False, indent=2))
        return 0

    _ensure_output_dirs(output_dir)
    probe_summary = _run_probe(options, output_dir)

    print("Running:", _redacted_command(download_cmd), flush=True)
    proc = subprocess.run(download_cmd)
    outputs = _write_outputs(
        options=options,
        exit_code=proc.returncode,
        download_command=_redacted_command(download_cmd),
        probe_summary=probe_summary,
    )
    success = proc.returncode == 0
    print(
        json.dumps(
            {
                "success": success,
                "exit_code": proc.returncode,
                **summary,
                **outputs,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
