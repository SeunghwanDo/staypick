from __future__ import annotations

import re
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import IO, Any, Dict, Iterable, Optional, Tuple, Union

import pandas as pd


# Column aliases you might see in GA exports / internal dashboards
URL_COL_CANDIDATES = ["url", "page", "page_url", "landing_page", "link", "서비스", "페이지", "주소"]
TITLE_COL_CANDIDATES = ["title", "page_title", "name", "콘텐츠", "제목"]
VISITS_COL_CANDIDATES = ["visits", "pageviews", "views", "sessions", "pv", "방문", "조회수", "페이지뷰", "세션"]
DWELL_COL_CANDIDATES = [
    "avg_dwell_sec",
    "avg_time_on_page",
    "avg_engagement_time",
    "avg_engagement_time_sec",
    "avg_time",
    "avg_duration",
    "체류시간",
    "평균체류시간",
    "평균 체류 시간",
]

# Optional: if you already have the page content/text in your export, you can pass it.
CONTENT_COL_CANDIDATES = ["content", "text", "body", "본문", "원문", "article", "page_text"]
CATEGORY_COL_CANDIDATES = ["category", "카테고리", "section", "분류", "topic", "topic_name", "category_name"]


def _pick_col(cols: Iterable[str], candidates: list[str]) -> Optional[str]:
    lower_to_original = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lower_to_original:
            return lower_to_original[cand.lower()]
    return None


def _parse_duration_to_seconds(x: Any) -> Optional[float]:
    """
    Accepts:
      - numeric seconds
      - "mm:ss" or "hh:mm:ss"
      - "12.3s", "1m 20s"
    """
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None

    if isinstance(x, (int, float)):
        return float(x)

    s = str(x).strip()
    if s == "":
        return None

    # mm:ss or hh:mm:ss
    if re.fullmatch(r"\d+:\d{2}(:\d{2})?", s):
        parts = [int(p) for p in s.split(":")]
        if len(parts) == 2:
            mm, ss = parts
            return float(mm * 60 + ss)
        if len(parts) == 3:
            hh, mm, ss = parts
            return float(hh * 3600 + mm * 60 + ss)

    # 1m 20s / 80s / 1h 2m 3s
    total = 0.0
    found = False
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([hms])", s.lower()):
        found = True
        v = float(value)
        if unit == "h":
            total += v * 3600
        elif unit == "m":
            total += v * 60
        elif unit == "s":
            total += v
    if found:
        return total

    # "123.4"
    try:
        return float(s)
    except Exception:
        return None



def _infer_category_from_url(url: str) -> str:
    """Best-effort category inference from URL structure.

    Rules (simple + explainable for hackathons):
    - Prefer hostname/netloc for non-http schemes (e.g., internal://demo/xxx -> demo)
    - For http(s), use the first path segment; if it's a generic bucket like 'blog'/'news',
      use the second segment when available (e.g., /blog/ai/... -> ai)
    - Fallback to '전체'
    """
    u = (url or "").strip()
    if not u:
        return "전체"

    try:
        p = urlparse(u)
    except Exception:
        return "전체"

    # internal://demo/xxx  -> netloc='demo'
    if p.scheme and p.scheme not in ("http", "https"):
        if p.netloc:
            return _slug_to_title(p.netloc)

    # http(s) or no scheme
    path = p.path or ""
    segs = [s for s in path.split("/") if s]
    if not segs:
        # If we have netloc but no path, use it
        if p.netloc:
            return _slug_to_title(p.netloc)
        return "전체"

    first = segs[0].lower()
    generic = {"blog", "news", "post", "posts", "article", "articles", "insight", "insights", "resources", "docs", "help", "category", "topics"}
    if first in generic and len(segs) >= 2:
        return _slug_to_title(segs[1])
    return _slug_to_title(segs[0])


def _slug_to_title(s: str) -> str:
    s = (s or "").strip().strip("/")
    if not s:
        return "전체"
    s = s.replace("-", " ").replace("_", " ")
    # Keep short titles readable
    return s[:1].upper() + s[1:]


def load_metrics_csv(file: Union[str, IO[bytes]]) -> pd.DataFrame:
    """
    Loads a CSV exported from analytics tools.
    Expected minimal columns:
      - url (or equivalent)

    Optional (있으면 더 정확한 랭킹):
      - visits (or equivalent)
      - avg_dwell_sec (or equivalent)
      - title
      - content (page text)

    Returns standardized columns:
      url, title, visits, avg_dwell_sec, content
    """
    df = pd.read_csv(file)

    url_col = _pick_col(df.columns, URL_COL_CANDIDATES)
    visits_col = _pick_col(df.columns, VISITS_COL_CANDIDATES)
    dwell_col = _pick_col(df.columns, DWELL_COL_CANDIDATES)
    title_col = _pick_col(df.columns, TITLE_COL_CANDIDATES)
    content_col = _pick_col(df.columns, CONTENT_COL_CANDIDATES)
    category_col = _pick_col(df.columns, CATEGORY_COL_CANDIDATES)

    missing = []
    if url_col is None:
        missing.append("url")

    if missing:
        raise ValueError(
            "CSV 컬럼을 인식하지 못했습니다. 필요한 컬럼: "
            + ", ".join(missing)
            + "\n예: url 또는 page, landing_page 등"
        )

    # visits/avg_dwell_sec가 없으면 '일반 유저용 간단 입력'을 위해 기본값을 채웁니다.
    # (가능하면 analytics 연동으로 실제 지표를 쓰는 것이 이상적)
    out = pd.DataFrame()
    out["url"] = df[url_col].astype(str).str.strip()

    if visits_col is not None:
        out["visits"] = pd.to_numeric(df[visits_col], errors="coerce").fillna(0).astype(float)
    else:
        out["visits"] = 1.0

    if dwell_col is not None:
        out["avg_dwell_sec"] = df[dwell_col].apply(_parse_duration_to_seconds).fillna(0).astype(float)
    else:
        out["avg_dwell_sec"] = 60.0
    if title_col is not None:
        out["title"] = df[title_col].astype(str).fillna("").str.strip()
    else:
        out["title"] = ""

    if content_col is not None:
        out["content"] = df[content_col].astype(str).fillna("").str.strip()
    else:
        out["content"] = ""

    if category_col is not None:
        out["category"] = df[category_col].astype(str).fillna("").str.strip()
    else:
        out["category"] = out["url"].apply(_infer_category_from_url)

    # Remove empty urls
    out = out[out["url"].str.len() > 0].reset_index(drop=True)

    # Category cleanup
    out["category"] = out["category"].fillna("").astype(str).str.strip()
    out.loc[out["category"].str.len() == 0, "category"] = "전체"

    return out


def compute_engagement_score(
    df: pd.DataFrame,
    weight_visits: float = 0.6,
    weight_dwell: float = 0.4,
) -> pd.DataFrame:
    """
    Adds normalized scores and a final engagement_score.
    Score = w_v * norm(visits) + w_d * norm(avg_dwell_sec)
    """
    if not (0.0 <= weight_visits <= 1.0):
        raise ValueError("weight_visits must be between 0 and 1")
    if not (0.0 <= weight_dwell <= 1.0):
        raise ValueError("weight_dwell must be between 0 and 1")
    if abs((weight_visits + weight_dwell) - 1.0) > 1e-6:
        # Caller usually passes 1-w
        total = weight_visits + weight_dwell
        weight_visits /= total
        weight_dwell /= total

    out = df.copy()

    def norm(series: pd.Series) -> pd.Series:
        s = series.astype(float)
        mn, mx = float(s.min()), float(s.max())
        if mx - mn < 1e-12:
            return s * 0.0
        return (s - mn) / (mx - mn)

    out["visits_norm"] = norm(out["visits"])
    out["dwell_norm"] = norm(out["avg_dwell_sec"])
    out["engagement_score"] = weight_visits * out["visits_norm"] + weight_dwell * out["dwell_norm"]

    # Human-friendly
    out["avg_dwell_min"] = (out["avg_dwell_sec"] / 60.0).round(2)
    out["engagement_score"] = out["engagement_score"].round(6)

    return out


def top_by_score(df_scored: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    return (
        df_scored.sort_values(["engagement_score", "visits", "avg_dwell_sec"], ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )



def topk_per_category(df_scored: pd.DataFrame, top_k: int = 10) -> pd.DataFrame:
    """Return a dataframe containing top_k items for each category by engagement score."""
    if "category" not in df_scored.columns:
        tmp = df_scored.copy()
        tmp["category"] = "전체"
        df_scored = tmp
    return (
        df_scored.sort_values(["category", "engagement_score", "visits", "avg_dwell_sec"], ascending=[True, False, False, False])
        .groupby("category", as_index=False, sort=False)
        .head(top_k)
        .reset_index(drop=True)
    )
