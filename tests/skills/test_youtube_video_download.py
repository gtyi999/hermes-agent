from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "media"
    / "youtube-video-download"
    / "scripts"
    / "download_youtube.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "youtube_video_download_skill",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_normalizes_common_youtube_inputs():
    mod = load_module()

    expected = "https://www.youtube.com/watch?v=Ee-7aHmfhAk"
    assert mod._normalize_youtube_input("Ee-7aHmfhAk") == expected
    assert mod._normalize_youtube_input("https://youtu.be/Ee-7aHmfhAk?si=x") == expected
    assert (
        mod._normalize_youtube_input(
            "https://www.youtube.com/watch?v=Ee-7aHmfhAk&list=RDEe-7aHmfhAk&start_radio=1"
        )
        == expected
    )
    assert mod._normalize_youtube_input("youtube.com/shorts/Ee-7aHmfhAk") == expected
    assert (
        mod._normalize_youtube_input("//www.youtube.com/embed/Ee-7aHmfhAk")
        == expected
    )
    assert (
        mod._normalize_youtube_input("https://music.youtube.com/watch?v=Ee-7aHmfhAk")
        == expected
    )


def test_playlist_mode_preserves_playlist_url():
    mod = load_module()

    url = "https://www.youtube.com/watch?v=Ee-7aHmfhAk&list=RDEe-7aHmfhAk&start_radio=1"
    assert mod._normalize_youtube_input(url, preserve_playlist=True) == url


def test_build_command_downloads_single_video_by_default_and_skips_dry_run_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])
    output_dir = tmp_path / "downloads"

    args = mod.parse_args(
        [
            "https://www.youtube.com/watch?v=Ee-7aHmfhAk&list=RDEe-7aHmfhAk&start_radio=1",
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ]
    )
    cmd = mod._build_command(args)

    assert cmd[-1] == "https://www.youtube.com/watch?v=Ee-7aHmfhAk"
    assert "--no-playlist" in cmd
    assert "--merge-output-format" not in cmd
    assert "-f" in cmd
    assert "[acodec!=none]" in cmd[cmd.index("-f") + 1]
    assert "[vcodec!=none]" in cmd[cmd.index("-f") + 1]
    assert not output_dir.exists()


def test_best_quality_uses_split_streams_and_requires_merge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])
    monkeypatch.setattr(mod, "_ffmpeg_command", lambda: "/usr/bin/ffmpeg")

    args = mod.parse_args(
        [
            "https://www.youtube.com/watch?v=Ee-7aHmfhAk",
            "--output-dir",
            str(tmp_path),
            "--best-quality",
            "--dry-run",
        ]
    )
    cmd = mod._build_command(args)

    assert "-f" in cmd
    assert "+" in cmd[cmd.index("-f") + 1]
    assert "--merge-output-format" in cmd


def test_best_quality_missing_ffmpeg_fails_before_running_yt_dlp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])
    monkeypatch.setattr(mod, "_ffmpeg_command", lambda: None)

    args = mod.parse_args(
        [
            "https://www.youtube.com/watch?v=Ee-7aHmfhAk",
            "--output-dir",
            str(tmp_path),
            "--best-quality",
            "--dry-run",
        ]
    )

    with pytest.raises(RuntimeError, match="ffmpeg"):
        mod._build_command(args)


def test_playlist_flag_allows_playlist_downloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])
    monkeypatch.setattr(mod, "_ffmpeg_command", lambda: "/usr/bin/ffmpeg")
    url = "https://www.youtube.com/watch?v=Ee-7aHmfhAk&list=RDEe-7aHmfhAk&start_radio=1"

    args = mod.parse_args(
        [
            url,
            "--output-dir",
            str(tmp_path),
            "--playlist",
            "--dry-run",
        ]
    )
    cmd = mod._build_command(args)

    assert cmd[-1] == url
    assert "--yes-playlist" in cmd


def test_auto_js_runtime_uses_available_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])
    monkeypatch.setattr(
        mod,
        "_available_js_runtimes",
        lambda: ["node:/usr/bin/node"],
    )

    args = mod.parse_args(
        [
            "https://www.youtube.com/watch?v=Ee-7aHmfhAk",
            "--output-dir",
            str(tmp_path),
            "--dry-run",
        ]
    )
    cmd = mod._build_command(args)

    assert "--js-runtimes" in cmd
    assert cmd[cmd.index("--js-runtimes") + 1] == "node:/usr/bin/node"


def test_js_runtime_can_be_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])
    monkeypatch.setattr(
        mod,
        "_available_js_runtimes",
        lambda: ["node:/usr/bin/node"],
    )

    args = mod.parse_args(
        [
            "https://www.youtube.com/watch?v=Ee-7aHmfhAk",
            "--output-dir",
            str(tmp_path),
            "--js-runtimes",
            "none",
            "--dry-run",
        ]
    )
    cmd = mod._build_command(args)

    assert "--js-runtimes" not in cmd


def test_explicit_js_runtime_passthrough(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])
    monkeypatch.setattr(
        mod,
        "_available_js_runtimes",
        lambda: ["node:/usr/bin/node"],
    )

    args = mod.parse_args(
        [
            "https://www.youtube.com/watch?v=Ee-7aHmfhAk",
            "--output-dir",
            str(tmp_path),
            "--js-runtimes",
            "deno:/opt/deno",
            "--dry-run",
        ]
    )
    cmd = mod._build_command(args)

    assert "--js-runtimes" in cmd
    assert cmd[cmd.index("--js-runtimes") + 1] == "deno:/opt/deno"


def test_audio_only_uses_audio_format_without_merge_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])
    monkeypatch.setattr(mod, "_ffmpeg_command", lambda: "/usr/bin/ffmpeg")

    args = mod.parse_args(
        [
            "https://www.youtube.com/watch?v=Ee-7aHmfhAk",
            "--output-dir",
            str(tmp_path),
            "--audio-only",
            "--dry-run",
        ]
    )
    cmd = mod._build_command(args)

    assert "-f" in cmd
    assert cmd[cmd.index("-f") + 1] == mod.AUDIO_ONLY_FORMAT
    assert "--merge-output-format" not in cmd
    assert "-x" in cmd


def test_missing_cookie_file_fails_before_running_yt_dlp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    mod = load_module()
    monkeypatch.setattr(mod, "_yt_dlp_command", lambda: ["/usr/bin/yt-dlp"])

    args = mod.parse_args(
        [
            "https://www.youtube.com/watch?v=Ee-7aHmfhAk",
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
            "https://www.youtube.com/watch?v=Ee-7aHmfhAk",
        ]
    )

    assert "/tmp/cookies.txt" not in rendered
    assert "chrome" not in rendered
    assert "user:pass" not in rendered
    assert rendered.count("<redacted>") == 3
