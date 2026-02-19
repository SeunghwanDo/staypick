from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from urllib.parse import urlencode
from urllib.request import ProxyHandler, build_opener


SEARCH_ENDPOINT = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_ENDPOINT = "https://www.googleapis.com/youtube/v3/videos"


def _to_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _request_json(url: str, params: Dict[str, str]) -> Dict:
    q = urlencode(params)
    # Bypass machine-level proxy overrides (e.g. localhost:9) for direct YouTube API access.
    opener = build_opener(ProxyHandler({}))
    with opener.open(f"{url}?{q}", timeout=20) as r:  # nosec B310
        return json.loads(r.read().decode("utf-8"))


def _published_after(days: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=max(int(days), 1))
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _pick_thumbnail(snippet: Dict) -> str:
    thumbs = (snippet or {}).get("thumbnails") or {}
    for k in ("high", "medium", "default"):
        t = thumbs.get(k) or {}
        u = str(t.get("url", "")).strip()
        if u:
            return u
    return ""


def fetch_youtube_videos(
    query: str,
    region: str,
    lang: str,
    max_results: int,
    published_days: int = 7,
    category: str = "",
) -> List[dict]:
    api_key = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY is missing. Set it in .env or environment variables.")

    search_payload = _request_json(
        SEARCH_ENDPOINT,
        {
            "part": "snippet",
            "q": (query or "").strip(),
            "type": "video",
            "order": "relevance",
            "maxResults": str(max(1, min(int(max_results or 10), 50))),
            "publishedAfter": _published_after(published_days),
            "regionCode": (region or "KR").upper(),
            "relevanceLanguage": (lang or "ko"),
            "key": api_key,
        },
    )

    ids: List[str] = []
    for it in (search_payload.get("items") or []):
        vid = (((it or {}).get("id") or {}).get("videoId") or "").strip()
        if vid:
            ids.append(vid)
    if not ids:
        return []

    detail_payload = _request_json(
        VIDEOS_ENDPOINT,
        {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(ids),
            "key": api_key,
        },
    )

    out: List[dict] = []
    for it in (detail_payload.get("items") or []):
        vid = str((it or {}).get("id", "")).strip()
        if not vid:
            continue
        snippet = (it or {}).get("snippet") or {}
        stats = (it or {}).get("statistics") or {}
        views = _to_int(stats.get("viewCount"), 0)
        out.append(
            {
                "url": f"https://www.youtube.com/watch?v={vid}",
                "video_id": vid,
                "title": str(snippet.get("title", "")).strip(),
                "channel_title": str(snippet.get("channelTitle", "")).strip(),
                "thumbnail_url": _pick_thumbnail(snippet),
                "published_at": str(snippet.get("publishedAt", "")).strip(),
                "views": views,
                "like_count": _to_int(stats.get("likeCount"), 0),
                "comment_count": _to_int(stats.get("commentCount"), 0),
                "content": "",
                "description": str(snippet.get("description", "")).strip(),
                "avg_dwell_sec": float(max(60, int(math.log1p(max(views, 0)) * 20))),
                "category": (category or "").strip(),
            }
        )
    return out
