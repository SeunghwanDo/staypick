from __future__ import annotations

def is_youtube_url(url: str) -> bool:
    u = str(url or "").lower()
    return ("youtube.com/watch" in u) or ("youtu.be/" in u) or ("youtube.com/shorts/" in u)
