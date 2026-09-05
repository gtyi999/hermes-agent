"""Bounded public HTTP fetching with manual, validated redirects."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from email.message import Message
from urllib.parse import urljoin

from .errors import ConversionError, ErrorCode
from .models import FetchedResource, HttpLimits
from .security import ARTICLE_HOSTS, validate_url


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _content_type(headers: Message) -> str:
    return (headers.get_content_type() or "application/octet-stream").lower()


class SafeFetcher:
    def __init__(self, limits: HttpLimits | None = None) -> None:
        self.limits = limits or HttpLimits()
        self._opener = urllib.request.build_opener(_NoRedirect())

    def fetch_article(self, url: str) -> FetchedResource:
        return self.fetch(
            url,
            allowed_hosts=ARTICLE_HOSTS,
            max_bytes=self.limits.max_html_bytes,
            expected_prefix="text/html",
        )

    def fetch(
        self,
        url: str,
        *,
        allowed_hosts: Iterable[str],
        max_bytes: int,
        expected_prefix: str | None = None,
    ) -> FetchedResource:
        current = validate_url(url, allowed_hosts=allowed_hosts)
        redirects = 0
        last_error: BaseException | None = None

        while True:
            request = urllib.request.Request(
                current,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,image/*,*/*;q=0.8",
                    "Referer": "https://mp.weixin.qq.com/",
                },
            )
            response = None
            for attempt in range(self.limits.retries + 1):
                try:
                    response = self._opener.open(
                        request,
                        timeout=self.limits.connect_timeout,
                    )
                    self._set_read_timeout(response, self.limits.read_timeout)
                    break
                except urllib.error.HTTPError as exc:
                    if exc.code in REDIRECT_STATUSES:
                        response = exc
                        break
                    if exc.code in {401, 403, 407, 451}:
                        raise ConversionError(
                            ErrorCode.ARTICLE_NOT_PUBLICLY_ACCESSIBLE,
                            f"Public access was refused with HTTP {exc.code}",
                        ) from exc
                    if 500 <= exc.code < 600 and attempt < self.limits.retries:
                        last_error = exc
                        time.sleep(0.2 * (attempt + 1))
                        continue
                    raise ConversionError(
                        ErrorCode.HTTP_FETCH_FAILED,
                        f"HTTP fetch failed with status {exc.code}",
                    ) from exc
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    last_error = exc
                    if attempt < self.limits.retries:
                        time.sleep(0.2 * (attempt + 1))
                        continue
                    raise ConversionError(
                        ErrorCode.HTTP_FETCH_FAILED,
                        "Network request failed",
                    ) from exc

            if response is None:
                raise ConversionError(ErrorCode.HTTP_FETCH_FAILED, "Network request failed") from last_error

            try:
                status = int(getattr(response, "status", None) or response.getcode())
                headers = response.headers
                if status in REDIRECT_STATUSES:
                    location = headers.get("Location")
                    if not location:
                        raise ConversionError(ErrorCode.HTTP_FETCH_FAILED, "Redirect has no Location header")
                    redirects += 1
                    if redirects > self.limits.max_redirects:
                        raise ConversionError(ErrorCode.HTTP_FETCH_FAILED, "Redirect limit exceeded")
                    current = validate_url(
                        urljoin(current, location),
                        allowed_hosts=allowed_hosts,
                    )
                    continue
                if status != 200:
                    raise ConversionError(ErrorCode.HTTP_FETCH_FAILED, f"Unexpected HTTP status {status}")

                declared = headers.get("Content-Length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise ConversionError(ErrorCode.RESPONSE_TOO_LARGE, "Response exceeds configured size limit")
                body = self._read_bounded(response, max_bytes)
                content_type = _content_type(headers)
                if expected_prefix and not content_type.startswith(expected_prefix):
                    raise ConversionError(
                        ErrorCode.HTTP_FETCH_FAILED,
                        f"Unexpected response content type: {content_type}",
                    )
                return FetchedResource(
                    body=body,
                    final_url=current,
                    content_type=content_type,
                    status=status,
                )
            finally:
                response.close()

    @staticmethod
    def _read_bounded(response, max_bytes: int) -> bytes:  # noqa: ANN001
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(min(64 * 1024, max_bytes - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ConversionError(ErrorCode.RESPONSE_TOO_LARGE, "Response exceeds configured size limit")
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _set_read_timeout(response, timeout: float) -> None:  # noqa: ANN001
        """Apply a distinct read timeout to urllib's connected socket."""
        candidates = (
            getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None),
            getattr(getattr(response, "fp", None), "_sock", None),
        )
        for sock in candidates:
            if sock is not None and hasattr(sock, "settimeout"):
                sock.settimeout(timeout)
                return


def decode_html(resource: FetchedResource) -> str:
    for encoding in ("utf-8", "gb18030"):
        try:
            return resource.body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return resource.body.decode("utf-8", "replace")


def reject_interstitial(html: str) -> None:
    sample = html[:200_000].lower()
    markers = (
        "请输入验证码",
        "环境异常",
        "访问过于频繁",
        "verify you are human",
        "captcha",
        "id=\"js_verify\"",
    )
    if any(marker in sample for marker in markers):
        raise ConversionError(
            ErrorCode.ARTICLE_NOT_PUBLICLY_ACCESSIBLE,
            "The page returned an access-verification interstitial",
        )
