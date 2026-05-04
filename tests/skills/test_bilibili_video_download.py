from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "media"
    / "bilibili-video-download"
    / "scripts"
    / "download_bilibili.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "bilibili_video_download_skill",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_normalizes_common_bilibili_inputs():
    mod = load_module()

    assert (
        mod._normalize_bilibili_input("BV1xx411c7mD")
        == "https://www.bilibili.com/video/BV1xx411c7mD"
    )
    assert (
        mod._normalize_bilibili_input("av170001")
        == "https://www.bilibili.com/video/av170001"
    )
    assert (
        mod._normalize_bilibili_input("ep12345")
        == "https://www.bilibili.com/bangumi/play/ep12345"
    )
    assert (
        mod._normalize_bilibili_input("ss67890")
        == "https://www.bilibili.com/bangumi/play/ss67890"
    )
    assert mod._normalize_bilibili_input("b23.tv/abc123") == "https://b23.tv/abc123"
    assert (
        mod._normalize_bilibili_input("//www.bilibili.com/video/BV1xx411c7mD")
        == "https://www.bilibili.com/video/BV1xx411c7mD"
    )


def test_build_command_uses_normalized_url_and_skips_dry_run_directory_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])
    output_dir = tmp_path / "downloads"

    args = mod.parse_args([
        "BV1xx411c7mD",
        "--output-dir",
        str(output_dir),
        "--dry-run",
    ])
    cmd = mod._build_command(args)

    assert cmd[-1] == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert "--no-playlist" in cmd
    assert "--merge-output-format" in cmd
    assert not output_dir.exists()


def test_audio_only_uses_audio_format_without_merge_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])

    args = mod.parse_args(
        [
            "https://www.bilibili.com/video/BV1xx411c7mD",
            "--output-dir",
            str(tmp_path),
            "--audio-only",
            "--dry-run",
        ]
    )
    cmd = mod._build_command(args)

    assert "-f" in cmd
    assert cmd[cmd.index("-f") + 1] == "ba/b"
    assert "--merge-output-format" not in cmd
    assert "-x" in cmd


def test_missing_cookie_file_fails_before_running_yt_dlp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])

    args = mod.parse_args(
        [
            "https://www.bilibili.com/video/BV1xx411c7mD",
            "--cookies",
            str(tmp_path / "missing-cookies.txt"),
            "--dry-run",
        ]
    )

    with pytest.raises(RuntimeError, match="Cookie file not found"):
        mod._build_command(args)


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
            "https://www.bilibili.com/video/BV1xx411c7mD",
        ]
    )

    assert "/tmp/cookies.txt" not in rendered
    assert "chrome" not in rendered
    assert "user:pass" not in rendered
    assert rendered.count("<redacted>") == 3
