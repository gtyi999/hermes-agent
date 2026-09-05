"""URL and DNS validation used before every network hop."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import urlsplit, urlunsplit

from .errors import ConversionError, ErrorCode


ARTICLE_HOSTS = frozenset({"mp.weixin.qq.com"})
IMAGE_HOSTS = frozenset({
    "mmbiz.qpic.cn",
    "mmbiz.qlogo.cn",
    "wx.qlogo.cn",
    "res.wx.qq.com",
})


def _host_allowed(host: str, allowed_hosts: Iterable[str]) -> bool:
    normalized = host.rstrip(".").lower()
    return normalized in {item.rstrip(".").lower() for item in allowed_hosts}


def validate_url(
    url: str,
    *,
    allowed_hosts: Iterable[str],
    resolve_dns: bool = True,
) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise ConversionError(ErrorCode.INVALID_URL, "Malformed URL") from exc

    if parsed.scheme.lower() != "https":
        raise ConversionError(ErrorCode.INVALID_URL, "Only HTTPS URLs are accepted")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ConversionError(ErrorCode.INVALID_URL, "URL host is missing or contains credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ConversionError(ErrorCode.INVALID_URL, "Invalid URL port") from exc
    if port not in (None, 443):
        raise ConversionError(ErrorCode.INVALID_URL, "Only the standard HTTPS port is accepted")

    host = parsed.hostname.rstrip(".").lower()
    if not _host_allowed(host, allowed_hosts):
        raise ConversionError(
            ErrorCode.UNSUPPORTED_DOMAIN,
            f"Host is not an allowed WeChat domain: {host}",
        )
    if resolve_dns:
        ensure_public_dns(host)

    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))


def ensure_public_dns(host: str) -> None:
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ConversionError(ErrorCode.HTTP_FETCH_FAILED, f"DNS lookup failed for {host}") from exc
    if not records:
        raise ConversionError(ErrorCode.HTTP_FETCH_FAILED, f"DNS lookup returned no addresses for {host}")

    for record in records:
        address = record[4][0].split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ConversionError(ErrorCode.HTTP_FETCH_FAILED, "DNS returned an invalid address") from exc
        if not ip.is_global:
            raise ConversionError(
                ErrorCode.INVALID_URL,
                f"Blocked non-public destination for {host}",
            )
