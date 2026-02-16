from __future__ import annotations

import hashlib
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Dict, Optional


def slugify(text: str, max_len: int = 80) -> str:
    """Create an ASCII-only slug.

    - Keeps a-z0-9 and hyphens.
    - If result is empty (e.g., Korean title), fall back to a short hash.
    """
    raw = (text or "").strip().lower()
    if not raw:
        return f"post-{int(time.time())}"

    # Normalize and strip accents
    norm = unicodedata.normalize("NFKD", raw)
    norm = "".join([c for c in norm if not unicodedata.combining(c)])

    # Replace non-alnum with hyphen
    norm = re.sub(r"[^a-z0-9]+", "-", norm)
    norm = norm.strip("-")
    norm = re.sub(r"-+", "-", norm)

    if not norm:
        h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
        norm = f"post-{h}"

    return norm[:max_len].rstrip("-")


def html_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


@dataclass
class SEOPage:
    title: str
    description: str
    lang: str
    canonical_url: str = ""
    og_image_url: str = ""
    body_html: str = ""
    alternates: Optional[Dict[str, str]] = None  # lang -> url


def render_html(page: SEOPage) -> str:
    """Render a simple SEO-friendly HTML page."""
    title = html_escape(page.title)
    desc = html_escape(page.description)
    lang = (page.lang or "en").split("-")[0]
    canonical = page.canonical_url.strip()
    og_image = page.og_image_url.strip()

    alternates = page.alternates or {}
    hreflang_links = "\n".join(
        [f'<link rel="alternate" hreflang="{html_escape(k)}" href="{html_escape(v)}" />' for k, v in alternates.items() if v]
    )

    canonical_link = f'<link rel="canonical" href="{html_escape(canonical)}" />' if canonical else ""
    og_image_tag = f'<meta property="og:image" content="{html_escape(og_image)}" />' if og_image else ""

    # Minimal CSS for readability
    css = """
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial;max-width:820px;margin:32px auto;padding:0 16px;line-height:1.6;color:#111;}
    .badge{display:inline-block;padding:4px 10px;border:1px solid rgba(0,0,0,.12);border-radius:999px;font-size:12px;margin-right:6px;}
    h1{letter-spacing:-0.4px;}
    a{color:#0a58ca;text-decoration:none;}
    a:hover{text-decoration:underline;}
    .muted{color:rgba(0,0,0,.65);font-size:14px;}
    .box{border:1px solid rgba(0,0,0,.12);border-radius:14px;padding:14px 16px;background:#fff;}
    """

    return f"""<!doctype html>
<html lang="{html_escape(lang)}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{title}</title>
  <meta name="description" content="{desc}" />
  {canonical_link}
  {hreflang_links}
  <meta property="og:type" content="article" />
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{desc}" />
  {og_image_tag}
  <style>{css}</style>
</head>
<body>
  <div class="muted"><span class="badge">StayPick</span><span class="badge">SEO Export</span></div>
  <h1>{title}</h1>
  <p class="muted">{desc}</p>
  <div class="box">{page.body_html}</div>
</body>
</html>"""


def export_html_file(
    *,
    out_dir: str,
    filename: str,
    html_text: str,
) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_text)
    return path
