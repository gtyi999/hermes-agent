"""Stable error codes for WeChat article conversion."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    INVALID_URL = "INVALID_URL"
    UNSUPPORTED_DOMAIN = "UNSUPPORTED_DOMAIN"
    ARTICLE_NOT_PUBLICLY_ACCESSIBLE = "ARTICLE_NOT_PUBLICLY_ACCESSIBLE"
    HTTP_FETCH_FAILED = "HTTP_FETCH_FAILED"
    ARTICLE_CONTENT_NOT_FOUND = "ARTICLE_CONTENT_NOT_FOUND"
    IMAGE_DOWNLOAD_FAILED = "IMAGE_DOWNLOAD_FAILED"
    MARKDOWN_CONVERSION_FAILED = "MARKDOWN_CONVERSION_FAILED"
    COPYRIGHT_AUTHORIZATION_REQUIRED = "COPYRIGHT_AUTHORIZATION_REQUIRED"
    OUTPUT_WRITE_FAILED = "OUTPUT_WRITE_FAILED"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"


class ConversionError(RuntimeError):
    """A user-facing conversion failure with a stable machine error code."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
