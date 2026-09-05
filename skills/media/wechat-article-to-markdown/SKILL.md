---
name: wechat-article-to-markdown
description: >
  Convert public WeChat Official Account article links into structured Markdown
  with metadata and optional local images. Use for mp.weixin.qq.com article
  export, archival, Markdown conversion, or 微信公众号文章转 Markdown requests.
license: MIT
metadata:
  hermes:
    tags: [WeChat, Markdown, Article, Export]
---

# WeChat Article to Markdown

Convert a publicly accessible `https://mp.weixin.qq.com/...` article with the
bundled deterministic parser. Do not use an LLM to rewrite an authorized
full-text conversion.

## Copyright and access boundary

- Default to summary mode. It writes metadata, a structural overview, and at
  most one short extract; it never presents the result as the complete article.
- Pass `--authorized-full-text` only when the user explicitly confirms that
  they own the text, have permission, supplied it themselves, or it is public
  domain/openly licensed. In that mode, preserve wording, punctuation, numbers,
  and paragraph order.
- Never use cookies, login sessions, CAPTCHA solving, archive relays, signature
  tricks, or anti-bot bypasses. If the public page cannot be read, report the
  script's error instead of attempting another access path.
- Do not infer authorization merely because a URL is public.

## Run the converter

`SKILL_DIR` is the directory containing this `SKILL.md`.

```bash
# Safe default: metadata + bounded summary
python3 SKILL_DIR/scripts/convert_wechat_article.py \
  "https://mp.weixin.qq.com/s/ARTICLE_ID" \
  --output ./output

# Full text, only after explicit authorization
python3 SKILL_DIR/scripts/convert_wechat_article.py \
  "https://mp.weixin.qq.com/s/ARTICLE_ID" \
  --output ./output \
  --authorized-full-text

# Keep remote image URLs
python3 SKILL_DIR/scripts/convert_wechat_article.py \
  "https://mp.weixin.qq.com/s/ARTICLE_ID" \
  --output ./output \
  --no-download-images
```

The script prints one JSON result. Exit code `0` means the Markdown file was
written; exit code `1` means the `error` field explains why it was not. Logs go
to stderr and never include cookies or authorization headers.

For module-style use, run from the scripts directory:

```bash
cd SKILL_DIR/scripts
python3 -m wechat_article_to_markdown \
  "https://mp.weixin.qq.com/s/ARTICLE_ID"
```

## Workflow

1. Confirm the input is a WeChat Official Account article URL. The fetcher
   rejects other schemes, credentials, nonstandard ports, non-WeChat hosts,
   private IP resolution, and redirects outside the allowlist.
2. Determine copyright mode. Omit `--authorized-full-text` unless authorization
   is explicit.
3. Run the script once. Do not retry access errors by changing identity,
   headers, cookies, or endpoints.
4. Read the JSON result and report `markdown_file`, `assets_dir`, `mode`, and
   any image warnings. A failed image remains a remote URL and does not fail the
   article.
5. For full text, verify `integrity_verified` is `true`. If it is false, do not
   deliver the file as a faithful conversion.

## Python API

Add `SKILL_DIR/scripts` to `PYTHONPATH`, then:

```python
import asyncio
from wechat_article_to_markdown import convert_wechat_article

result = asyncio.run(convert_wechat_article(
    "https://mp.weixin.qq.com/s/ARTICLE_ID",
    output_dir="./output",
    download_images=True,
    authorized_full_text=False,
))
print(result.to_dict())
```

## Behavior and limits

- Metadata and content use selector fallbacks headed by `#activity-name`,
  `#js_name`, and `#js_content`.
- Lazy images prefer `data-src`, then `data-original`, `src`, and
  `data-backup-src`. Raster images are MIME-checked, size-limited, and
  SHA-256-deduplicated. Unsupported or failed images retain their public URL.
- Simple tables become Markdown tables. Tables with spans or nesting remain
  sanitized HTML so information is not discarded.
- Explicit heading tags are preserved. Styled `<section>` containers are not
  guessed to be headings.
- The parser handles static public HTML. It does not execute JavaScript, access
  video media, recover comments, or bypass an interstitial. Summary mode is a
  bounded deterministic overview, not a semantic LLM synopsis.
