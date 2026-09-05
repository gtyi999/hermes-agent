"""Command-line interface for the WeChat article converter."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from .models import HttpLimits
from .skill import convert_wechat_article


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a public WeChat Official Account article to Markdown.",
    )
    parser.add_argument("url", help="Public https://mp.weixin.qq.com article URL")
    parser.add_argument("--output", "--output-dir", default="./output", dest="output_dir")
    parser.add_argument("--no-download-images", action="store_true")
    parser.add_argument(
        "--authorized-full-text",
        action="store_true",
        help="Confirm ownership, permission, public domain, or an open license",
    )
    parser.add_argument("--connect-timeout", type=float, default=10.0)
    parser.add_argument("--read-timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--max-redirects", type=int, default=5)
    parser.add_argument("--max-html-mb", type=float, default=10.0)
    parser.add_argument("--max-image-mb", type=float, default=20.0)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="[%(levelname)s] %(message)s",
        stream=sys.stderr,
    )
    try:
        limits = HttpLimits(
            connect_timeout=args.connect_timeout,
            read_timeout=args.read_timeout,
            retries=args.retries,
            max_redirects=args.max_redirects,
            max_html_bytes=int(args.max_html_mb * 1024 * 1024),
            max_image_bytes=int(args.max_image_mb * 1024 * 1024),
        )
    except ValueError as exc:
        print(json.dumps({"success": False, "error": "INVALID_ARGUMENT", "error_message": str(exc)}))
        return 2

    result = asyncio.run(convert_wechat_article(
        args.url,
        output_dir=args.output_dir,
        download_images=not args.no_download_images,
        authorized_full_text=args.authorized_full_text,
        limits=limits,
    ))
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.success else 1
