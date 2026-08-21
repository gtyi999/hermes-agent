import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


PIL_Image = pytest.importorskip("PIL.Image")


def test_blank_browser_screenshot_detects_all_white(tmp_path):
    from tools.browser_tool import _is_blank_browser_screenshot, _is_blank_png_screenshot

    path = tmp_path / "blank.png"
    PIL_Image.new("RGB", (1280, 720), (255, 255, 255)).save(path)

    assert _is_blank_browser_screenshot(path) is True
    assert _is_blank_png_screenshot(path) is True


def test_blank_browser_screenshot_allows_visible_content(tmp_path):
    from tools.browser_tool import _is_blank_browser_screenshot, _is_blank_png_screenshot

    path = tmp_path / "content.png"
    image = PIL_Image.new("RGB", (1280, 720), (255, 255, 255))
    for x in range(100, 300):
        for y in range(100, 180):
            image.putpixel((x, y), (0, 0, 0))
    image.save(path)

    assert _is_blank_browser_screenshot(path) is False
    assert _is_blank_png_screenshot(path) is False


def test_browser_vision_does_not_share_blank_screenshot(monkeypatch, tmp_path):
    import hermes_constants
    from tools import browser_tool

    monkeypatch.setattr(hermes_constants, "get_hermes_dir", lambda *args: tmp_path)
    monkeypatch.setattr(browser_tool, "_cleanup_old_screenshots", lambda *args, **kwargs: None)
    monkeypatch.setattr(browser_tool, "_is_local_backend", lambda: True)
    call_llm = MagicMock()
    monkeypatch.setattr(browser_tool, "_lazy_call_llm", call_llm)

    def fake_run_browser_command(task_id, command, args, timeout=None, **kwargs):
        assert command == "screenshot"
        screenshot_path = Path(args[-1])
        PIL_Image.new("RGB", (1280, 720), (255, 255, 255)).save(screenshot_path)
        return {"success": True, "data": {"path": str(screenshot_path)}}

    monkeypatch.setattr(browser_tool, "_run_browser_command", fake_run_browser_command)

    result = json.loads(browser_tool.browser_vision("截图当前网页", task_id="test"))

    assert result["success"] is False
    assert result["screenshot_blank"] is True
    assert "screenshot_path" not in result
    assert "blank" in result["error"].lower()
    call_llm.assert_not_called()
