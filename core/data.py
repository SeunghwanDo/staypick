from __future__ import annotations

import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from core.constants import DEFAULT_YT_QUERY_GROUPS, DEMO_CSV_PATH, YOUTUBE_SNAPSHOT_PATH
from modules.fetch import fetch_and_extract
from modules.metrics import compute_engagement_score, top_by_score, topk_per_category
from modules.youtube import fetch_youtube_videos
from modules.metrics import load_metrics_csv


@st.cache_data(show_spinner=False, ttl=60 * 60)
def cached_fetch(url: str) -> Tuple[str, str]:
    return fetch_and_extract(url)


def load_demo_df() -> pd.DataFrame:
    return load_metrics_csv(DEMO_CSV_PATH)


@st.cache_data(show_spinner=False, ttl=15 * 60)
def _cached_youtube_query(
    query: str,
    region: str,
    lang: str,
    max_results: int,
    published_days: int,
    category: str,
    cache_bucket: int,
    query_version: str = "v1",
) -> List[Dict[str, Any]]:
    _ = cache_bucket
    _ = query_version
    return fetch_youtube_videos(
        query=query,
        region=region,
        lang=lang,
        max_results=max_results,
        published_days=published_days,
        category=category,
    )


def _youtube_query_groups() -> Dict[str, List[str]]:
    raw = st.session_state.get("yt_query_groups")
    alias = {
        "게임": "game",
        "연애/썰": "love",
        "연애": "love",
        "재테크": "finance",
        "생활꿀팁": "life",
        "동물": "animal",
        "반려동물": "animal",
        "연예": "celebrity",
        "연예인": "celebrity",
        "테크": "tech",
        "트렌드": "trend",
        "전체": "trend",
    }
    if isinstance(raw, dict) and raw:
        out: Dict[str, List[str]] = {}
        for k, v in raw.items():
            kk = str(k).strip()
            kk = alias.get(kk, kk)
            out[kk] = [str(x) for x in (v or []) if str(x).strip()]
        return out
    return {k: list(v) for k, v in DEFAULT_YT_QUERY_GROUPS.items()}


def _looks_korean_item(item: Dict[str, Any]) -> bool:
    txt = " ".join(
        [
            str(item.get("title", "") or ""),
            str(item.get("channel_title", "") or ""),
            str(item.get("description", "") or ""),
        ]
    )
    return bool(re.search(r"[가-힣]", txt))


def _is_political_item(item: Dict[str, Any]) -> bool:
    txt = " ".join(
        [
            str(item.get("title", "") or ""),
            str(item.get("channel_title", "") or ""),
            str(item.get("description", "") or ""),
        ]
    ).lower()
    blocked = [
        "정치", "선거", "국회", "여야", "정당", "대통령", "탄핵", "총선", "대선",
        "민주당", "국민의힘", "윤석열", "이재명", "조국", "한동훈",
        "trump", "biden", "election", "parliament", "president",
    ]
    return any(k in txt for k in blocked)


def load_youtube_df(selected_category: Optional[str] = None) -> pd.DataFrame:
    region = str(st.session_state.get("yt_region", "KR") or "KR").upper()
    lang = str(st.session_state.get("yt_lang", "ko") or "ko")
    ttl_min = int(st.session_state.get("yt_cache_ttl_min", 15) or 15)
    ttl_min = min(max(ttl_min, 10), 30)
    max_per_query = int(st.session_state.get("yt_max_per_query", 8) or 8)
    max_per_query = min(max(max_per_query, 3), 20)
    published_days = int(st.session_state.get("yt_published_days", 7) or 7)
    groups = _youtube_query_groups()
    cache_bucket = int(time.time() // (ttl_min * 60))

    rows: List[Dict[str, Any]] = []
    if selected_category and selected_category in groups:
        active_groups = {selected_category: groups.get(selected_category, [])}
    else:
        active_groups = groups
    # Default sourcing mix: KR 70% + overseas 30% (US)
    kr_ratio = float(st.session_state.get("yt_kr_ratio", 0.7) or 0.7)
    kr_ratio = min(max(kr_ratio, 0.5), 0.9)
    for cat, queries in active_groups.items():
        queries_to_use = [str(x).strip() for x in (queries or []) if str(x).strip()][:2]
        if selected_category and cat == selected_category and queries_to_use:
            booster = f"{queries_to_use[0]} 쇼츠"
            if booster not in queries_to_use:
                queries_to_use.append(booster)
        for q in queries_to_use:
            kr_n = max(1, int(round(max_per_query * kr_ratio)))
            gl_n = max(1, max_per_query - kr_n)
            fetch_plan = [
                ("KR", "ko", kr_n),
                (region if region != "KR" else "US", (lang if lang != "ko" else "en"), gl_n),
            ]
            for rg, lg, take_n in fetch_plan:
                fetch_n = min(20, (take_n * 2) if str(rg).upper() == "KR" else take_n)
                items = _cached_youtube_query(
                    query=q,
                    region=rg,
                    lang=lg,
                    max_results=fetch_n,
                    published_days=published_days,
                    category=cat,
                    cache_bucket=cache_bucket,
                    query_version="v2_kr_priority",
                )
                if str(rg).upper() == "KR" and items:
                    ko_first = [it for it in items if _looks_korean_item(it)]
                    rest = [it for it in items if not _looks_korean_item(it)]
                    picked_items = (ko_first + rest)[:take_n]
                else:
                    picked_items = items[:take_n]
                for it in picked_items:
                    if _is_political_item(it):
                        continue
                    views_v = float(it.get("views", 0) or 0)
                    rows.append(
                        {
                            "url": it.get("url", ""),
                            "video_id": it.get("video_id", ""),
                            "title": it.get("title", ""),
                            "visits": views_v,
                            "kr_views": views_v if str(rg).upper() == "KR" else 0.0,
                            "avg_dwell_sec": float(it.get("avg_dwell_sec", 60) or 60),
                            "content": it.get("description", "") or "",
                            "description": it.get("description", "") or "",
                            "duration_sec": float(it.get("duration_sec", 0) or 0),
                            "is_short": bool(it.get("is_short", False)),
                            "category": it.get("category", cat),
                            "thumbnail_url": it.get("thumbnail_url", ""),
                            "channel_title": it.get("channel_title", ""),
                            "published_at": it.get("published_at", ""),
                            "like_count": float(it.get("like_count", 0) or 0),
                            "comment_count": float(it.get("comment_count", 0) or 0),
                        }
                    )

    if not rows:
        return pd.DataFrame(columns=["url", "title", "visits", "avg_dwell_sec", "content", "category"])
    df = pd.DataFrame(rows)
    # Merge duplicated urls from KR/global pulls while preserving KR view signal.
    df = (
        df.sort_values(["kr_views", "visits"], ascending=False)
        .groupby("url", as_index=False, dropna=False)
        .agg(
            video_id=("video_id", "first"),
            title=("title", "first"),
            visits=("visits", "max"),
            kr_views=("kr_views", "sum"),
            avg_dwell_sec=("avg_dwell_sec", "max"),
            content=("content", "first"),
            description=("description", "first"),
            duration_sec=("duration_sec", "max"),
            is_short=("is_short", "max"),
            category=("category", "first"),
            thumbnail_url=("thumbnail_url", "first"),
            channel_title=("channel_title", "first"),
            published_at=("published_at", "first"),
            like_count=("like_count", "max"),
            comment_count=("comment_count", "max"),
        )
    )
    hours = df.get("published_at", pd.Series(dtype=str)).apply(_hours_since_published)
    recency = hours.apply(lambda h: 1.0 / (1.0 + (h / 36.0)) if h is not None else 0.25)
    reaction = (
        pd.to_numeric(df.get("comment_count", 0), errors="coerce").fillna(0.0) * 2.0
        + pd.to_numeric(df.get("like_count", 0), errors="coerce").fillna(0.0) * 0.25
    )
    reaction_norm = (reaction / (reaction.max() + 1.0)).fillna(0.0)
    visits = pd.to_numeric(df.get("visits", 0), errors="coerce").fillna(0.0)
    visits_norm = (visits / (visits.max() + 1.0)).fillna(0.0)
    df["raw_rank"] = (visits_norm * 0.70) + (reaction_norm * 0.20) + (recency * 0.10)
    df = df.sort_values(["raw_rank", "visits", "avg_dwell_sec"], ascending=False).drop_duplicates(subset=["url"], keep="first")
    return df.reset_index(drop=True)


def _relative_time_text(iso_dt: str) -> str:
    try:
        s = str(iso_dt or "").replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        delta = datetime.now(dt.tzinfo) - dt
        hours = int(delta.total_seconds() // 3600)
        if hours < 1:
            return "just now"
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        return f"{days}d ago"
    except Exception:
        return ""


def _hours_since_published(iso_dt: str) -> Optional[float]:
    try:
        s = str(iso_dt or "").replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        delta = now - dt
        return max(float(delta.total_seconds() / 3600.0), 0.0)
    except Exception:
        return None


def _compute_portal_score(df: pd.DataFrame) -> pd.Series:
    """Hybrid ranking score: engagement + recency + reaction."""
    if df is None or df.empty:
        return pd.Series(dtype=float)

    def _num_col(name: str) -> pd.Series:
        if name in df.columns:
            s = df[name]
        else:
            s = pd.Series([0.0] * len(df), index=df.index)
        return pd.to_numeric(s, errors="coerce").fillna(0.0)

    base = _num_col("engagement_score")
    comments = _num_col("comment_count")
    likes = _num_col("like_count")
    reactions = ((comments * 2.0) + (likes * 0.25)).clip(lower=0.0)
    react_norm = (reactions / (reactions.max() + 1.0)).fillna(0.0)
    hours = df.get("published_at", pd.Series(dtype=str)).apply(_hours_since_published)
    recency = hours.apply(lambda h: 1.0 / (1.0 + (h / 36.0)) if h is not None else 0.25)
    wb = float(st.session_state.get("portal_base_w", 0.72) or 0.72)
    wr = float(st.session_state.get("portal_react_w", 0.18) or 0.18)
    wc = float(st.session_state.get("portal_recency_w", 0.10) or 0.10)
    return (base * wb) + (react_norm * wr) + (recency * wc)


def refresh_scores() -> None:
    """Recompute df_scored/top tables when weights or dataset changes."""
    if "df_raw" not in st.session_state or st.session_state["df_raw"] is None:
        return
    df_raw: pd.DataFrame = st.session_state["df_raw"]
    weight_visits = float(st.session_state.get("weight_visits", 0.6) or 0.6)
    weight_dwell = 1.0 - weight_visits
    top_n = int(st.session_state.get("top_n", 8) or 8)
    top_k_per_category = int(st.session_state.get("top_k_per_category", 10) or 10)
    df_scored = compute_engagement_score(df_raw, weight_visits=weight_visits, weight_dwell=weight_dwell)
    if "kr_views" not in df_scored.columns:
        df_scored["kr_views"] = 0.0
    df_scored["kr_views"] = pd.to_numeric(df_scored.get("kr_views", 0), errors="coerce").fillna(0.0)
    df_scored["portal_score"] = _compute_portal_score(df_scored)
    st.session_state["df_scored"] = df_scored
    st.session_state["top_df"] = top_by_score(df_scored, top_n=top_n)
    st.session_state["topk_cat_df"] = topk_per_category(df_scored, top_k=top_k_per_category)


def _save_youtube_snapshot(df: pd.DataFrame) -> None:
    try:
        if df is None or df.empty:
            return
        os.makedirs(os.path.dirname(YOUTUBE_SNAPSHOT_PATH), exist_ok=True)
        df.to_csv(YOUTUBE_SNAPSHOT_PATH, index=False, encoding="utf-8-sig")
    except Exception:
        pass


def _load_youtube_snapshot() -> pd.DataFrame:
    try:
        if os.path.exists(YOUTUBE_SNAPSHOT_PATH):
            df = pd.read_csv(YOUTUBE_SNAPSHOT_PATH)
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
    except Exception:
        pass
    return pd.DataFrame()
