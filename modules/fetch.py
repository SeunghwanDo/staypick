from __future__ import annotations

import re
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "User-Agent": "StayPickBot/0.1 (+https://example.local) requests",
    "Accept-Language": "ko,en;q=0.8",
}


def fetch_html(url: str, timeout: int = 12) -> str:
    resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    # Let requests guess encoding; if wrong, BeautifulSoup will still often work
    return resp.text


def extract_title_and_text(html: str) -> Tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")

    # Title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Remove noisy elements
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside", "form"]):
        tag.decompose()

    # Prefer <article>
    article = soup.find("article")
    if article:
        text = article.get_text("\n", strip=True)
    else:
        # Fallback: join paragraphs
        ps = soup.find_all("p")
        if ps:
            text = "\n".join(p.get_text(" ", strip=True) for p in ps)
        else:
            text = soup.get_text("\n", strip=True)

    # Clean excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    return title, text


def fetch_and_extract(url: str, timeout: int = 12) -> Tuple[str, str]:
    """
    Returns: (title, text)
    """
    html = fetch_html(url, timeout=timeout)
    title, text = extract_title_and_text(html)
    return title, text
