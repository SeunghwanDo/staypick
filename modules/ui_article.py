from __future__ import annotations

import html
import re
from typing import List, Tuple


def build_article_header(title: str, meta: str, url: str) -> str:
    safe_title = html.escape(title or "")
    safe_meta = html.escape(meta or "")
    safe_url = html.escape(url or "")
    return (
        "<div class=\"article-header\">"
        f"<div class=\"article-title\">{safe_title}</div>"
        f"<div class=\"article-meta\">{safe_meta} · "
        f"<a href=\"{safe_url}\" target=\"_blank\">원문 보기</a></div>"
        "</div>"
    )


def build_news_row(title: str, meta: str, excerpt: str, thumb_html: str) -> str:
    safe_title = html.escape(title or "")
    safe_meta = html.escape(meta or "")
    safe_excerpt = html.escape(excerpt or "")
    return (
        "<div class=\"news-row\">"
        f"<div class=\"news-thumb\">{thumb_html}</div>"
        "<div>"
        f"<div class=\"news-title\">{safe_title}</div>"
        f"<div class=\"news-meta\">{safe_meta}</div>"
        f"<div class=\"news-excerpt\">{safe_excerpt}</div>"
        "</div>"
        "</div>"
    )


def build_yt_row(
    title: str,
    channel: str,
    meta: str,
    desc: str,
    thumb_html: str,
    chip: str = "",
) -> str:
    safe_title = html.escape(title or "")
    safe_channel = html.escape(channel or "")
    safe_meta = html.escape(meta or "")
    safe_desc = html.escape(desc or "")
    chip_html = f"<span class=\"yt-chip\">{html.escape(chip)}</span>" if chip else ""
    return (
        "<div class=\"yt-row\">"
        f"<div class=\"yt-row-thumb\">{thumb_html}</div>"
        "<div>"
        f"{chip_html}"
        f"<div class=\"yt-row-title\">{safe_title}</div>"
        f"<div class=\"yt-row-channel\">{safe_channel}</div>"
        f"<div class=\"yt-row-meta\">{safe_meta}</div>"
        f"<div class=\"yt-row-desc\">{safe_desc}</div>"
        "</div>"
        "</div>"
    )

def build_toc(toc: List[Tuple[str, str]]) -> str:
    items = "".join([f"<div><a href=\"#{html.escape(a)}\">{html.escape(t)}</a></div>" for t, a in toc])
    return f"<div class=\"toc\"><div class=\"toc-title\">목차</div>{items}</div>"


def paragraphize_fulltext(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    parts = [p.strip() for p in re.split(r"\n{2,}|\r\n{2,}", text or "") if p.strip()]
    if not parts:
        return ("", [])

    toc: List[Tuple[str, str]] = []
    out: List[str] = []

    def _is_heading(line: str) -> bool:
        if not line:
            return False
        if len(line) > 70:
            return False
        if line.endswith(":"):
            return True
        words = re.sub(r"\s+", " ", line).strip().split(" ")
        if len(words) <= 8 and line.count(".") == 0:
            return True
        if line.isupper() and len(line) <= 60:
            return True
        return False

    for idx, part in enumerate(parts, start=1):
        lines = [l.strip() for l in part.splitlines() if l.strip()]
        if not lines:
            continue

        if all(l.startswith(("- ", "* ", "• ")) for l in lines):
            items = "".join([f"<li>{html.escape(l[2:].strip())}</li>" for l in lines])
            out.append(f"<ul>{items}</ul>")
            continue

        first = lines[0]
        if _is_heading(first):
            heading = first.rstrip(":").strip()
            anchor = f"sec-{idx}"
            toc.append((heading, anchor))
            out.append(f"<h3 id=\"{anchor}\">{html.escape(heading)}</h3>")
            rest = " ".join(lines[1:]).strip()
            if rest:
                out.append(f"<p>{html.escape(rest)}</p>")
            continue

        joined = " ".join(lines).strip()
        if joined.startswith(">"):
            quote_txt = joined.lstrip(">").strip()
            out.append(f"<blockquote>{html.escape(quote_txt)}</blockquote>")
        else:
            out.append(f"<p>{html.escape(joined)}</p>")

    return ("".join(out), toc)
