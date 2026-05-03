"""Windows regression: let the OpenAI SDK manage its default transport.

Custom httpx HTTPTransport socket_options keepalive injection works around
stale sockets on POSIX, but on Windows it can break ChatGPT Codex
connections with connect timeouts. Guard that Windows builds do not inject a
custom http_client by default.
"""

from run_agent import AIAgent


def test_create_openai_client_skips_custom_http_client_on_windows(monkeypatch):
    captured = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    agent = AIAgent(
        api_key="test-key",
        base_url="https://chatgpt.com/backend-api/codex",
        model="gpt-5.4-mini",
        provider="openai-codex",
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
    )

    monkeypatch.setattr("run_agent.OpenAI", _FakeOpenAI)
    monkeypatch.setattr("run_agent.os.name", "nt")

    agent._create_openai_client(
        {"api_key": "test-key", "base_url": "https://chatgpt.com/backend-api/codex"},
        reason="test",
        shared=False,
    )

    assert "http_client" not in captured
