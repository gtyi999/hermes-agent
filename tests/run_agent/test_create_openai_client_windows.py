"""Windows regression: do not inject low-level TCP socket options.

The legacy keepalive transport supplied ``socket_options`` to httpx, which
could break ChatGPT Codex connections on Windows. The current pool-lifecycle
implementation is portable, but must never reintroduce those low-level options.
"""

from unittest.mock import MagicMock

import httpx

from run_agent import AIAgent


def test_keepalive_http_client_does_not_set_socket_options(monkeypatch):
    transport = MagicMock(side_effect=lambda **kwargs: ("transport", kwargs))
    client = MagicMock(return_value=object())
    monkeypatch.setattr(httpx, "HTTPTransport", transport)
    monkeypatch.setattr(httpx, "Client", client)
    monkeypatch.setattr("run_agent._get_proxy_for_base_url", lambda _url: None)

    result = AIAgent._build_keepalive_http_client(
        "https://chatgpt.com/backend-api/codex"
    )

    assert result is client.return_value
    assert transport.call_count == 2
    assert all("socket_options" not in call.kwargs for call in transport.call_args_list)
