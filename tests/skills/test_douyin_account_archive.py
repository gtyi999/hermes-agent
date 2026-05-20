from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "media"
    / "douyin-account-archive"
    / "scripts"
    / "archive_douyin_account.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "douyin_account_archive_skill",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_normalizes_common_douyin_inputs():
    mod = load_module()

    sec_user_id = "MS4wLjABAAAAabcdef_1234567890"
    assert (
        mod._normalize_douyin_input(sec_user_id)
        == f"https://www.douyin.com/user/{sec_user_id}"
    )
    assert (
        mod._normalize_douyin_input("www.douyin.com/user/MS4wLjABAAAAabcdef")
        == "https://www.douyin.com/user/MS4wLjABAAAAabcdef"
    )
    assert (
        mod._normalize_douyin_input("//www.douyin.com/user/MS4wLjABAAAAabcdef")
        == "https://www.douyin.com/user/MS4wLjABAAAAabcdef"
    )
    assert mod._looks_like_douyin_url("https://v.douyin.com/abc123/")


def test_requires_authorized_access_unless_explicitly_allowed(tmp_path: Path):
    mod = load_module()

    args = mod.parse_args(
        [
            "https://www.douyin.com/user/MS4wLjABAAAAabcdef",
            "--output-dir",
            str(tmp_path),
        ]
    )

    with pytest.raises(RuntimeError, match="Authorized Douyin access is required"):
        mod._resolve_options(args)


def test_build_download_command_uses_archive_layout_and_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    output_dir = tmp_path / "archive"

    args = mod.parse_args(
        [
            "https://www.douyin.com/user/MS4wLjABAAAAabcdef",
            "--cookies",
            str(cookies),
            "--output-dir",
            str(output_dir),
            "--max-videos",
            "25",
            "--dry-run",
        ]
    )
    options = mod._resolve_options(args)
    cmd = mod._build_download_command(options)

    assert cmd[-1] == "https://www.douyin.com/user/MS4wLjABAAAAabcdef"
    assert "--yes-playlist" in cmd
    assert "--write-thumbnail" in cmd
    assert "--write-info-json" in cmd
    assert "--playlist-end" in cmd
    assert cmd[cmd.index("--playlist-end") + 1] == "25"
    assert f"video:{mod.DEFAULT_VIDEO_TEMPLATE}" in cmd
    assert f"thumbnail:{mod.DEFAULT_COVER_TEMPLATE}" in cmd
    assert f"infojson:{mod.DEFAULT_INFO_TEMPLATE}" in cmd
    assert str(output_dir / "reports" / "download-archive.txt") in cmd
    assert not output_dir.exists()


def test_metadata_only_skips_video_but_keeps_info_and_cover(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    args = mod.parse_args(
        [
            "https://www.douyin.com/user/MS4wLjABAAAAabcdef",
            "--cookies",
            str(cookies),
            "--metadata-only",
            "--dry-run",
        ]
    )
    options = mod._resolve_options(args)
    cmd = mod._build_download_command(options)

    assert "--skip-download" in cmd
    assert "--write-info-json" in cmd
    assert "--write-thumbnail" in cmd


def test_no_cover_omits_thumbnail_args(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")

    args = mod.parse_args(
        [
            "https://www.douyin.com/user/MS4wLjABAAAAabcdef",
            "--cookies",
            str(cookies),
            "--no-cover",
            "--dry-run",
        ]
    )
    options = mod._resolve_options(args)
    cmd = mod._build_download_command(options)

    assert "--write-thumbnail" not in cmd
    assert not any(part.startswith("thumbnail:") for part in cmd)


def test_config_file_values_are_merged_with_cli_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "account_url": "https://www.douyin.com/user/MS4wLjABAAAAfromconfig",
                "cookies": str(cookies),
                "max_videos": 10,
            }
        ),
        encoding="utf-8",
    )

    args = mod.parse_args(["--config", str(config), "--max-videos", "3"])
    options = mod._resolve_options(args)

    assert options["account_url"].endswith("MS4wLjABAAAAfromconfig")
    assert options["max_videos"] == 3


def test_redacts_sensitive_command_values():
    mod = load_module()

    rendered = mod._redacted_command(
        [
            "yt-dlp",
            "--cookies",
            "/tmp/cookies.txt",
            "--cookies-from-browser",
            "chrome",
            "--proxy",
            "http://user:pass@example.invalid:8080",
            "https://www.douyin.com/user/MS4wLjABAAAAabcdef",
        ]
    )

    assert "/tmp/cookies.txt" not in rendered
    assert "chrome" not in rendered
    assert "user:pass" not in rendered
    assert rendered.count("<redacted>") == 3


def test_manifest_collects_metadata_and_related_files(tmp_path: Path):
    mod = load_module()
    output_dir = tmp_path / "archive"
    metadata_dir = output_dir / "metadata"
    videos_dir = output_dir / "videos"
    covers_dir = output_dir / "covers"
    metadata_dir.mkdir(parents=True)
    videos_dir.mkdir(parents=True)
    covers_dir.mkdir(parents=True)

    (videos_dir / "20240520_7123456789_Test title.mp4").write_bytes(b"video")
    (covers_dir / "20240520_7123456789_Test title.jpg").write_bytes(b"cover")
    info_path = metadata_dir / "20240520_7123456789_Test title.info.json"
    info_path.write_text(
        json.dumps(
            {
                "id": "7123456789",
                "title": "Test title",
                "webpage_url": "https://www.douyin.com/video/7123456789",
                "uploader": "creator",
                "uploader_id": "MS4wLjABAAAAabcdef",
                "upload_date": "20240520",
                "timestamp": 1716192000,
                "duration": 12,
                "view_count": 100,
                "digg_count": 9,
                "comment_count": 3,
                "share_count": 2,
                "collect_count": 1,
            }
        ),
        encoding="utf-8",
    )

    items = mod._collect_manifest_items(output_dir)

    assert len(items) == 1
    item = items[0]
    assert item["id"] == "7123456789"
    assert item["upload_date"] == "2024-05-20"
    assert item["interaction"]["like_count"] == 9
    assert item["interaction"]["favorite_count"] == 1
    assert item["files"]["video"] == "videos/20240520_7123456789_Test title.mp4"
    assert item["files"]["cover"] == "covers/20240520_7123456789_Test title.jpg"
    assert item["files"]["info_json"] == "metadata/20240520_7123456789_Test title.info.json"
