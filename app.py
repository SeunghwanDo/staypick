from __future__ import annotations

import os
import json
import re
import io
import zipfile
from datetime import datetime, timedelta
import time
import random
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import pandas as pd
import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

from modules.metrics import load_metrics_csv
from modules.ai import OpenAIService
from modules.cluster import cluster_summaries
from modules.ads import ensure_ads_storage, load_ads, save_ads, select_ads, log_event, Ad
from modules.i18n import normalize_lang
from modules.seo import SEOPage, render_html, slugify
from modules.ui_article import build_article_header, build_news_row, build_toc, paragraphize_fulltext, build_yt_row

from core.constants import (
    APP_DIR,
    DEFAULT_YT_QUERY_GROUPS,
    FEED_CATEGORY_EMOJI,
    FEED_CATEGORY_ORDER,
    LANDING_PAGE_PATH,
    MONETIZATION_ASSUMPTIONS,
    MONETIZATION_PRICING,
)
from core.data import (
    _load_youtube_snapshot,
    _relative_time_text,
    _save_youtube_snapshot,
    _youtube_query_groups,
    cached_fetch,
    load_demo_df,
    load_youtube_df,
    refresh_scores,
)
from core.state import init_state
from core.subscription import (
    ai_usage_left,
    consume_ai_credit,
    subscription_entitlements,
    subscription_snapshot,
)
from core.upsell import load_upsell_events_df
from ui.app_shell import render_app_shell
from ui.feed import render_feed
from ui.sidebar import render_sidebar
from ui.theme import apply_portal_css
from ui.guide import render_guide
from ui.home import render_home
from ui.make import render_make
from ui.mypage import render_mypage
from ui.landing import render_landing
from admin.data import render_admin_data
from admin.insights import render_admin_insights
from admin.sponsor import render_admin_sponsor
from admin import global_tab

load_dotenv()

st.set_page_config(page_title="StayPick", layout="wide", initial_sidebar_state="collapsed")


apply_portal_css()

# Sidebar state (shared across UI)
_sidebar_state = render_sidebar()
t = _sidebar_state["t"]
admin_mode = _sidebar_state["admin_mode"]
api_key = _sidebar_state["api_key"]
model = _sidebar_state["model"]
embedding_model = _sidebar_state["embedding_model"]
top_n = _sidebar_state["top_n"]
top_k_per_category = _sidebar_state["top_k_per_category"]
weight_visits = _sidebar_state["weight_visits"]
weight_dwell = _sidebar_state["weight_dwell"]
show_ads = _sidebar_state["show_ads"]
show_metrics = _sidebar_state["show_metrics"]
auto_summarize = _sidebar_state["auto_summarize"]
teaser_mode = _sidebar_state["teaser_mode"]
age_group = _sidebar_state["age_group"]
persona = _sidebar_state["persona"]
output_format = _sidebar_state["output_format"]
content_lang = _sidebar_state["content_lang"]
brand_tone = _sidebar_state["brand_tone"]


# ---------------------------
# Paths & demo (moved to core.constants)
# ---------------------------


def _load_landing_html() -> str:
    try:
        if os.path.exists(LANDING_PAGE_PATH):
            with open(LANDING_PAGE_PATH, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        return ""
    return ""




# ads storage (inventory + event logs)
ensure_ads_storage(APP_DIR)


# ---------------------------
# Helpers / State
# ---------------------------
def ensure_ai() -> OpenAIService:
    return OpenAIService(api_key=api_key, model=model, embedding_model=embedding_model)


def _log_reco_click(url: str) -> None:
    counts = st.session_state.get("reco_click_counts", {})
    if not isinstance(counts, dict):
        counts = {}
    u = (url or "").strip()
    if not u:
        return
    counts[u] = int(counts.get(u, 0) or 0) + 1
    st.session_state["reco_click_counts"] = counts


def _log_reco_event(from_url: str, to_url: str, placement: str, category: str = "") -> None:
    try:
        os.makedirs(os.path.join(APP_DIR, "data"), exist_ok=True)
        path = os.path.join(APP_DIR, "data", "reco_events.csv")
        row = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "from_url": (from_url or "").strip(),
            "to_url": (to_url or "").strip(),
            "placement": (placement or "").strip(),
            "category": (category or "").strip(),
        }
        df_row = pd.DataFrame([row])
        if os.path.exists(path):
            df_row.to_csv(path, mode="a", index=False, header=False, encoding="utf-8-sig")
        else:
            df_row.to_csv(path, mode="w", index=False, header=True, encoding="utf-8-sig")
    except Exception:
        pass


def _log_content_event(
    event: str,
    url: str,
    category: str = "",
    placement: str = "",
    dwell_sec: Optional[float] = None,
    reason: str = "",
    variant: str = "",
) -> None:
    try:
        os.makedirs(os.path.join(APP_DIR, "data"), exist_ok=True)
        path = os.path.join(APP_DIR, "data", "content_events.csv")
        row = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": (event or "").strip(),
            "url": (url or "").strip(),
            "category": (category or "").strip(),
            "placement": (placement or "").strip(),
            "dwell_sec": float(dwell_sec) if dwell_sec is not None else "",
            "reason": (reason or "").strip(),
            "variant": (variant or "").strip(),
        }
        df_row = pd.DataFrame([row])
        if os.path.exists(path):
            df_row.to_csv(path, mode="a", index=False, header=False, encoding="utf-8-sig")
        else:
            df_row.to_csv(path, mode="w", index=False, header=True, encoding="utf-8-sig")
    except Exception:
        pass


def _load_content_events_df() -> pd.DataFrame:
    path = os.path.join(APP_DIR, "data", "content_events.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _log_content_impression_once(url: str, category: str, placement: str, variant: str = "") -> None:
    key = f"{placement}|{url}"
    seen = st.session_state.get("content_impressions", set())
    if key in seen:
        return
    _log_content_event("impression", url=url, category=category, placement=placement, variant=variant)
    seen.add(key)
    st.session_state["content_impressions"] = seen


def _load_reco_events_df() -> pd.DataFrame:
    path = os.path.join(APP_DIR, "data", "reco_events.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _decayed_reco_weights(df_events: pd.DataFrame, half_life_hours: float) -> pd.Series:
    if df_events is None or df_events.empty or "ts" not in df_events.columns:
        return pd.Series(dtype=float)
    now = datetime.now()
    hl = max(float(half_life_hours or 24.0), 1.0)
    lam = 0.69314718056 / hl
    ts = pd.to_datetime(df_events["ts"], errors="coerce")
    hours = (now - ts).dt.total_seconds() / 3600.0
    hours = hours.fillna(1e9).clip(lower=0)
    return pd.Series(np.exp(-lam * hours), index=df_events.index)


def _reco_click_boost(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series([0.0] * (len(df) if df is not None else 0), index=(df.index if df is not None else None))
    half_life = float(st.session_state.get("reco_half_life_hours", 24.0) or 24.0)
    ev = _load_reco_events_df()
    if ev.empty or "to_url" not in ev.columns:
        counts = st.session_state.get("reco_click_counts", {})
        if not isinstance(counts, dict):
            counts = {}
        raw = df.get("url", pd.Series(dtype=str)).map(lambda u: float(counts.get(str(u), 0) or 0))
        return (raw / (raw.max() + 1.0)).fillna(0.0) if not raw.empty else raw
    decay = _decayed_reco_weights(ev, half_life)
    weighted = ev.assign(_w=decay).groupby("to_url", dropna=False)["_w"].sum()
    raw = df.get("url", pd.Series(dtype=str)).map(lambda u: float(weighted.get(str(u), 0.0)))
    return (raw / (raw.max() + 1.0)).fillna(0.0) if not raw.empty else raw


def _category_click_boost(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series([0.0] * (len(df) if df is not None else 0), index=(df.index if df is not None else None))
    half_life = float(st.session_state.get("reco_half_life_hours", 24.0) or 24.0)
    ev = _load_reco_events_df()
    if ev.empty or "category" not in ev.columns:
        counts = st.session_state.get("clicked_category_counts", {})
        if not isinstance(counts, dict):
            counts = {}
        raw = df.get("category", pd.Series(dtype=str)).map(lambda c: float(counts.get(str(c), 0) or 0))
        return (raw / (raw.max() + 1.0)).fillna(0.0) if not raw.empty else raw
    decay = _decayed_reco_weights(ev, half_life)
    weighted = ev.assign(_w=decay).groupby("category", dropna=False)["_w"].sum()
    raw = df.get("category", pd.Series(dtype=str)).map(lambda c: float(weighted.get(str(c), 0.0)))
    return (raw / (raw.max() + 1.0)).fillna(0.0) if not raw.empty else raw


def _watch_dwell_boost(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series([0.0] * (len(df) if df is not None else 0), index=(df.index if df is not None else None))
    by_url = st.session_state.get("watch_dwell_by_url", {})
    if not isinstance(by_url, dict) or not by_url:
        return pd.Series([0.0] * len(df), index=df.index)
    raw = df.get("url", pd.Series(dtype=str)).map(lambda u: float(by_url.get(str(u), 0.0)))
    if raw.empty:
        return raw
    return (raw / (raw.max() + 1.0)).fillna(0.0)


def _quality_metrics_by_url() -> pd.DataFrame:
    ev = _load_content_events_df()
    if ev is None or ev.empty:
        return pd.DataFrame(columns=["url", "ctr", "avg_dwell_sec", "skip_rate"])
    ev["event"] = ev.get("event", "").astype(str)
    ev["url"] = ev.get("url", "").astype(str)

    imp = ev[ev["event"] == "impression"].groupby("url")["event"].count().rename("impressions")
    clk = ev[ev["event"] == "click"].groupby("url")["event"].count().rename("clicks")

    view = ev[ev["event"] == "view"].copy()
    if not view.empty and "dwell_sec" in view.columns:
        view["dwell_sec"] = pd.to_numeric(view["dwell_sec"], errors="coerce").fillna(0.0)
        skip_thr = float(st.session_state.get("skip_threshold_sec", 8.0) or 8.0)
        view["is_skip"] = view["dwell_sec"] < skip_thr
        agg_view = view.groupby("url").agg(
            avg_dwell_sec_view=("dwell_sec", "mean"),
            skip_rate=("is_skip", "mean"),
        )
    else:
        agg_view = pd.DataFrame(columns=["avg_dwell_sec_view", "skip_rate"])

    df = pd.concat([imp, clk, agg_view], axis=1).fillna(0.0)
    df["ctr"] = df.apply(lambda r: (float(r.get("clicks", 0)) / float(r.get("impressions", 0))) if float(r.get("impressions", 0)) > 0 else 0.0, axis=1)
    return df.reset_index().rename(columns={"index": "url"})


def _compute_quality_score(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    m = _quality_metrics_by_url()
    if m.empty:
        df = df.copy()
        df["ctr"] = 0.0
        df["avg_dwell_sec_q"] = 0.0
        df["skip_rate"] = 0.0
        df["quality_score"] = 0.0
        return df
    df = df.copy()
    df = df.merge(m, on="url", how="left")
    df["ctr"] = pd.to_numeric(df.get("ctr", 0), errors="coerce").fillna(0.0)
    df["avg_dwell_sec_q"] = pd.to_numeric(df.get("avg_dwell_sec_view", 0), errors="coerce").fillna(0.0)
    df["skip_rate"] = pd.to_numeric(df.get("skip_rate", 0), errors="coerce").fillna(0.0)

    ctr_norm = (df["ctr"] / (df["ctr"].max() + 1e-9)).fillna(0.0)
    dwell_norm = (df["avg_dwell_sec_q"] / (df["avg_dwell_sec_q"].max() + 1e-9)).fillna(0.0)
    skip_norm = df["skip_rate"].clip(lower=0.0, upper=1.0)

    w_ctr = float(st.session_state.get("quality_ctr_w", 0.45) or 0.45)
    w_dwell = float(st.session_state.get("quality_dwell_w", 0.35) or 0.35)
    w_skip = float(st.session_state.get("quality_skip_w", 0.20) or 0.20)
    w_sum = max(w_ctr + w_dwell + w_skip, 1e-9)
    w_ctr, w_dwell, w_skip = w_ctr / w_sum, w_dwell / w_sum, w_skip / w_sum

    df["quality_score"] = (ctr_norm * w_ctr) + (dwell_norm * w_dwell) + ((1.0 - skip_norm) * w_skip)
    return df


def _resolve_rank_variant() -> str:
    mode = str(st.session_state.get("rank_ab_mode", "baseline") or "baseline")
    prev = str(st.session_state.get("_rank_ab_mode_prev", mode) or mode)
    if prev != mode:
        st.session_state["_rank_ab_mode_prev"] = mode
        if mode == "ab":
            if st.session_state.get("rank_variant") not in {"control", "quality"}:
                seed = float(st.session_state.get("_ab_seed", random.random()) or random.random())
                st.session_state["_ab_seed"] = seed
                st.session_state["rank_variant"] = "quality" if seed >= 0.5 else "control"
        else:
            st.session_state["rank_variant"] = "quality" if mode == "quality" else "control"

    if mode == "baseline":
        st.session_state["rank_variant"] = "control"
    elif mode == "quality":
        st.session_state["rank_variant"] = "quality"
    elif mode == "ab":
        if st.session_state.get("rank_variant") not in {"control", "quality"}:
            seed = float(st.session_state.get("_ab_seed", random.random()) or random.random())
            st.session_state["_ab_seed"] = seed
            st.session_state["rank_variant"] = "quality" if seed >= 0.5 else "control"

    return str(st.session_state.get("rank_variant", "control"))


def _views_text(v: Any) -> str:
    n = float(v or 0)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M views"
    if n >= 1_000:
        return f"{n/1_000:.1f}K views"
    return f"{int(n)} views"


def get_row_by_url(url: str) -> Optional[Dict[str, Any]]:
    df_scored: pd.DataFrame = st.session_state.get("df_scored")
    if df_scored is None or df_scored.empty:
        return None
    m = df_scored[df_scored["url"] == url]
    if len(m) == 0:
        return None
    return m.iloc[0].to_dict()


def snippet_from_content(text: str, max_chars: int = 120) -> str:
    t = (text or "").strip().replace("\r", "\n")
    t = "\n".join([line.strip() for line in t.split("\n") if line.strip()])
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1].rstrip() + "…"


def build_demo_summary(
    *,
    url: str,
    title: str,
    content: str,
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Local fallback summary builder for demo mode (no API calls)."""
    metrics = metrics or {}
    base = (content or title or url or "").strip()
    title = (title or snippet_from_content(base, 60) or url).strip()
    localized_title = title
    # Prefer sentence-like chunks for better demo quality
    cleaned = re.sub(r"\s+", " ", base).strip()
    sents = [s.strip() for s in re.split(r"[.!?\n]+", base) if s.strip()]
    if len(sents) >= 2:
        hook_src = sents[0]
        one_src = sents[1]
    else:
        hook_src = cleaned
        one_src = cleaned

    hook = snippet_from_content(hook_src, 70).replace("?", ".")
    one_liner = snippet_from_content(one_src, 120)

    points: List[str] = []
    for p in sents:
        if len(points) >= 3:
            break
        points.append(snippet_from_content(p, 80))
    if not points:
        points = [
            snippet_from_content(cleaned, 80) or "핵심 내용을 빠르게 요약했습니다.",
            "한 문장 요약과 포인트를 제공합니다.",
            "이 내용을 기반으로 새로운 콘텐츠를 만들 수 있습니다.",
        ]
    visits = float(metrics.get("visits", 0) or 0)
    dwell = float(metrics.get("avg_dwell_sec", 0) or 0)
    raw_score = metrics.get("engagement_score")
    score_txt = (
        f"{float(raw_score):.2f}"
        if raw_score is not None and str(raw_score).strip() != ""
        else "?"
    )
    why = f"왜 뜨는가: 방문 {visits:.0f}회, 평균 체류 {dwell:.1f}초. 참여도 {score_txt}로 관심이 유지된 주제입니다."
    tags = []
    for w in re.split(r"[^0-9A-Za-z가-힣]+", cleaned):
        w = w.strip()
        if len(w) >= 2 and w not in tags:
            tags.append(w)
        if len(tags) >= 6:
            break
    if not tags:
        tags = ["demo", "summary", "staypick"]
    return {
        "url": url,
        "title": title,
        "localized_title": localized_title,
        "hook": hook,
        "one_liner": one_liner,
        "key_points": points[:3],
        "why_trending": why,
        "discussion_prompt": "이 주제에서 가장 궁금한 한 가지는 무엇인가요?",
        "summary": snippet_from_content(base, 240),
        "tags": tags,
        "sources": [url],
    }


def build_demo_content(
    *,
    summary: Dict[str, Any],
    persona: str,
    output_format: str,
    tone: str = "",
) -> str:
    """Local fallback content generator for demo mode."""
    title = summary.get("localized_title") or summary.get("title") or "StayPick Demo"
    hook = summary.get("hook") or summary.get("one_liner") or ""
    kps = summary.get("key_points") or []
    body = summary.get("summary") or ""
    tone_note = f"\n\nTone: {tone.strip()}" if tone.strip() else ""
    bullets = "\n".join([f"- {str(k)}" for k in kps[:3]]) or "- 핵심 포인트를 요약했습니다."
    takeaways = [
        "오늘 당장 적용 가능한 한 가지를 고르세요.",
        "핵심 문장을 1줄로 요약해 공유하세요.",
        "댓글/리액션을 유도할 질문을 덧붙이세요.",
    ]
    takeaways_txt = "\n".join([f"- {t}" for t in takeaways])
    return (
        f"# {title}\n\n"
        f"**Hook**: {hook}\n\n"
        f"**독자**: {persona}\n\n"
        f"**포맷**: {output_format}\n\n"
        f"## 핵심 포인트\n{bullets}\n\n"
        f"## 3초 요약\n{body}\n"
        f"{tone_note}\n\n"
        f"## 실행 체크리스트\n{takeaways_txt}\n"
    )


def _finalize_current_view(reason: str = "switch") -> None:
    current_url = (st.session_state.get("selected_url") or "").strip()
    started = st.session_state.get("item_opened_at")
    if not current_url or started is None:
        return
    try:
        elapsed = max(float(time.time() - float(started)), 0.0)
    except Exception:
        return
    if elapsed < 1.0:
        return

    row = get_row_by_url(current_url) or {}
    title = (row.get("title") or current_url).strip()
    cat = (row.get("category") or "").strip()
    event = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "url": current_url,
        "title": title,
        "category": cat,
        "thumbnail_url": str(row.get("thumbnail_url", "") or "").strip(),
        "channel_title": str(row.get("channel_title", "") or "").strip(),
        "dwell_sec": round(elapsed, 2),
        "reason": reason,
    }
    hist = st.session_state.get("watch_history", [])
    if not isinstance(hist, list):
        hist = []
    hist.append(event)
    st.session_state["watch_history"] = hist[-100:]

    by_url = st.session_state.get("watch_dwell_by_url", {})
    if not isinstance(by_url, dict):
        by_url = {}
    by_url[current_url] = float(by_url.get(current_url, 0.0) or 0.0) + elapsed
    st.session_state["watch_dwell_by_url"] = by_url

    by_cat = st.session_state.get("watch_dwell_by_cat", {})
    if not isinstance(by_cat, dict):
        by_cat = {}
    if cat:
        by_cat[cat] = float(by_cat.get(cat, 0.0) or 0.0) + elapsed
    st.session_state["watch_dwell_by_cat"] = by_cat

    placement = str(st.session_state.get("last_open_source", "") or "")
    variant = str(st.session_state.get("last_open_variant", "") or "")
    _log_content_event(
        "view",
        url=current_url,
        category=cat,
        placement=placement,
        dwell_sec=round(elapsed, 2),
        reason=reason,
        variant=variant,
    )

    st.session_state["item_opened_at"] = time.time()


def _today_watch_seconds() -> float:
    hist = st.session_state.get("watch_history", [])
    if not isinstance(hist, list) or not hist:
        return 0.0
    today = datetime.now().date()
    total = 0.0
    for ev in hist:
        try:
            ts = datetime.fromisoformat(str(ev.get("ts", "")).strip())
            if ts.date() == today:
                total += float(ev.get("dwell_sec", 0.0) or 0.0)
        except Exception:
            continue
    return total


def _watch_streak_count(max_gap_min: int = 30, min_dwell_sec: float = 10.0) -> int:
    hist = st.session_state.get("watch_history", [])
    if not isinstance(hist, list) or not hist:
        return 0
    rows = []
    for ev in hist:
        try:
            ts = datetime.fromisoformat(str(ev.get("ts", "")).strip())
            dwell = float(ev.get("dwell_sec", 0.0) or 0.0)
            rows.append((ts, dwell))
        except Exception:
            continue
    if not rows:
        return 0
    rows.sort(key=lambda x: x[0], reverse=True)
    streak = 0
    prev_ts: Optional[datetime] = None
    for ts, dwell in rows:
        if dwell < min_dwell_sec:
            break
        if prev_ts is not None:
            gap = (prev_ts - ts).total_seconds() / 60.0
            if gap > max_gap_min:
                break
        streak += 1
        prev_ts = ts
    return streak


def open_item(url: str, source: str = "feed") -> None:
    prev_url = (st.session_state.get("selected_url") or "").strip()
    if prev_url and prev_url != (url or "").strip():
        _finalize_current_view("switch")
    st.session_state["selected_url"] = url
    st.session_state["item_opened_at"] = time.time()
    st.session_state["last_open_source"] = source
    st.session_state["last_open_variant"] = str(st.session_state.get("rank_variant", "control") or "control")
    row = get_row_by_url(url) or {}
    cat = (row.get("category") or "").strip()
    _log_content_event(
        "click",
        url=url,
        category=cat,
        placement=source,
        reason="open",
        variant=str(st.session_state.get("rank_variant", "control") or "control"),
    )
    st.session_state["open_dialog"] = True
    st.rerun()


def _is_shorts_item(row: Dict[str, Any]) -> bool:
    t = str(row.get("title", "") or "").lower()
    d = float(row.get("duration_sec", 0) or 0)
    u = str(row.get("url", "") or "").lower()
    desc = str(row.get("description", "") or "").lower()
    return (
        bool(row.get("is_short", False))
        or (d > 0 and d <= 180)
        or ("shorts" in t)
        or ("/shorts/" in u)
        or ("#shorts" in t)
        or ("#shorts" in desc)
    )


def mark_not_interested(url: str, title: str = "") -> None:
    u = (url or "").strip()
    if not u:
        return
    hidden = st.session_state.get("hidden_urls", [])
    if not isinstance(hidden, list):
        hidden = []
    if u not in hidden:
        hidden.append(u)
        st.session_state["hidden_urls"] = hidden
    recent = st.session_state.get("hidden_recent", [])
    if not isinstance(recent, list):
        recent = []
    recent.append({"url": u, "title": (title or u).strip(), "ts": datetime.now().isoformat(timespec="seconds")})
    st.session_state["hidden_recent"] = recent[-30:]


def undo_not_interested() -> bool:
    recent = st.session_state.get("hidden_recent", [])
    if not isinstance(recent, list) or not recent:
        return False
    last = recent.pop()
    st.session_state["hidden_recent"] = recent
    u = str((last or {}).get("url", "")).strip()
    hidden = st.session_state.get("hidden_urls", [])
    if isinstance(hidden, list) and u in hidden:
        hidden = [x for x in hidden if x != u]
        st.session_state["hidden_urls"] = hidden
        return True
    return False


def current_summary_language() -> str:
    return normalize_lang(st.session_state.get("content_lang") or st.session_state.get("ui_lang", "ko"))


def make_cache_key(url: str, lang: Optional[str], age: Optional[str]) -> str:
    lang = normalize_lang(lang or current_summary_language())
    age = (age or st.session_state.get("age_group", "general") or "general").strip()
    return f"{(url or '').strip()}||{lang}||{age}"


def get_cached_summary(
    cache: Dict[str, Dict[str, Any]],
    url: str,
    lang: Optional[str] = None,
    age: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    key = make_cache_key(url, lang, age)
    return cache.get(key)


def set_cached_summary(
    cache: Dict[str, Dict[str, Any]],
    url: str,
    summary: Dict[str, Any],
    lang: Optional[str] = None,
    age: Optional[str] = None,
) -> None:
    key = make_cache_key(url, lang, age)
    cache[key] = summary


def add_to_selection(summary: Dict[str, Any]) -> None:
    selected: List[Dict[str, Any]] = st.session_state.get("selected_summaries", [])
    urls = {x.get("url") for x in selected}
    sub = subscription_snapshot()
    save_limit = subscription_entitlements(sub)["save_limit"]
    if len(selected) >= save_limit and summary.get("url") not in urls:
        st.warning(f"Save limit reached ({save_limit}). Upgrade plan to save more items.")
        return
    if summary.get("url") not in urls:
        selected.append(summary)
        st.session_state["selected_summaries"] = selected


def compute_trending_keywords(df: pd.DataFrame, top_k: int = 10) -> List[str]:
    """Lightweight keyword extraction from titles (no OpenAI)."""
    titles = [str(x) for x in df.get("title", pd.Series(dtype=str)).fillna("").tolist()]
    # very small tokenization: split on spaces; keep 2+ chars
    freq: Dict[str, int] = {}
    stop = {"the", "and", "for", "with", "this", "that", "from", "your", "you", "있", "없", "하는", "하기", "그", "것", "수", "들", "좀"}
    for t in titles:
        for tok in re.split(r"[\s\|\-_/·•,.\(\)\[\]{}:;!?\"“”'’]+", t.lower()):
            tok = tok.strip()
            if len(tok) < 2:
                continue
            if tok in stop:
                continue
            if tok.isdigit():
                continue
            freq[tok] = freq.get(tok, 0) + 1
    # sort by frequency then alphabetically
    items = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    return [w for w, _ in items[:top_k]]




# ---------------------------
# Home / App routing
# ---------------------------

def _set_route_state(route: str) -> None:
    st.session_state["route"] = route


def _route_toggle() -> None:
    st.session_state.setdefault("route", "home")
    labels = ["Home", "App"]
    current = "App" if st.session_state.get("route") == "app" else "Home"
    if hasattr(st, "segmented_control"):
        choice = st.segmented_control(
            "Route",
            options=labels,
            default=current,
            label_visibility="collapsed",
            key="route_toggle",
        )
    else:
        choice = st.radio(
            "Route",
            options=labels,
            index=labels.index(current),
            horizontal=True,
            label_visibility="collapsed",
            key="route_toggle",
        )
    new_route = "app" if choice == "App" else "home"
    if new_route != st.session_state.get("route"):
        _set_route_state(new_route)
        st.rerun()


def render_app() -> None:
    tab_map = render_app_shell(t, admin_mode)
    tab_feed = tab_map.get("feed")
    tab_guide = tab_map.get("guide")
    tab_make = tab_map.get("make")
    tab_mypage = tab_map.get("mypage")
    tab_landing = tab_map.get("landing")
    tab_data = tab_map.get("data") if admin_mode else None
    tab_insights = tab_map.get("insights") if admin_mode else None
    tab_sponsor = tab_map.get("sponsor") if admin_mode else None
    tab_global = tab_map.get("global") if admin_mode else None


    # ---------------------------
    # Feed tab (portal-like)
    # ---------------------------
    with tab_feed:
        render_feed({
            't': t,
            'admin_mode': admin_mode,
            'FEED_CATEGORY_ORDER': FEED_CATEGORY_ORDER,
            'FEED_CATEGORY_EMOJI': FEED_CATEGORY_EMOJI,
            '_youtube_query_groups': _youtube_query_groups,
            'load_youtube_df': load_youtube_df,
            '_save_youtube_snapshot': _save_youtube_snapshot,
            '_load_youtube_snapshot': _load_youtube_snapshot,
            'refresh_scores': refresh_scores,
            'undo_not_interested': undo_not_interested,
            '_log_content_impression_once': _log_content_impression_once,
            '_today_watch_seconds': _today_watch_seconds,
            '_watch_streak_count': _watch_streak_count,
            'open_item': open_item,
            '_log_content_event': _log_content_event,
            '_log_reco_event': _log_reco_event,
            '_log_reco_click': _log_reco_click,
            '_relative_time_text': _relative_time_text,
            '_views_text': _views_text,
            '_category_click_boost': _category_click_boost,
            '_watch_dwell_boost': _watch_dwell_boost,
            '_compute_quality_score': _compute_quality_score,
            '_resolve_rank_variant': _resolve_rank_variant,
            '_reco_click_boost': _reco_click_boost,
            '_is_shorts_item': _is_shorts_item,
            'compute_trending_keywords': compute_trending_keywords,            'build_news_row': build_news_row,
            'build_yt_row': build_yt_row,
            'build_article_header': build_article_header,
            'build_toc': build_toc,
            'paragraphize_fulltext': paragraphize_fulltext,
            'snippet_from_content': snippet_from_content,
            'get_row_by_url': get_row_by_url,
            'get_cached_summary': get_cached_summary,
            'set_cached_summary': set_cached_summary,
            'current_summary_language': current_summary_language,
            'build_demo_summary': build_demo_summary,
            'cached_fetch': cached_fetch,
            'ensure_ai': ensure_ai,
            'ai_usage_left': ai_usage_left,
            'consume_ai_credit': consume_ai_credit,
            'subscription_snapshot': subscription_snapshot,
            'subscription_entitlements': subscription_entitlements,
            'select_ads': select_ads,
            'load_ads': load_ads,
            'log_event': log_event,
            'Ad': Ad,
            'APP_DIR': APP_DIR,
            'api_key': api_key,
            'model': model,
            'embedding_model': embedding_model,
            'teaser_mode': teaser_mode,
            'show_metrics': show_metrics,
            'show_ads': show_ads,
            'add_to_selection': add_to_selection,
            'make_cache_key': make_cache_key,
            'persona': persona,
            'mark_not_interested': mark_not_interested,
            '_finalize_current_view': _finalize_current_view,
        })

    # ---------------------------
    # Guide tab
    # ---------------------------
    with tab_guide:
        render_guide()


    # ---------------------------
        # ---------------------------
    # Make tab (batch generate from saved list)
    # ---------------------------
    with tab_make:
        render_make({
            't': t,
            'ensure_ai': ensure_ai,
            'get_row_by_url': get_row_by_url,
            'add_to_selection': add_to_selection,
            'build_demo_summary': build_demo_summary,
            'cached_fetch': cached_fetch,
            'get_cached_summary': get_cached_summary,
            'set_cached_summary': set_cached_summary,
            'current_summary_language': current_summary_language,
            'subscription_snapshot': subscription_snapshot,
            'subscription_entitlements': subscription_entitlements,
            'ai_usage_left': ai_usage_left,
            'consume_ai_credit': consume_ai_credit,
            'OpenAIService': OpenAIService,
            'api_key': api_key,
            'model': model,
            'embedding_model': embedding_model,
        })

    # ---------------------------
        # ---------------------------
    # ---------------------------
    # My Page tab
    # ---------------------------
    with tab_mypage:
        render_mypage({
            'subscription_snapshot': subscription_snapshot,
        })

    # ---------------------------
    # Landing tab
    # ---------------------------
    with tab_landing:
        render_landing({
            '_load_landing_html': _load_landing_html,
            'LANDING_PAGE_PATH': LANDING_PAGE_PATH,
        })

    # ---------------------------
    # Admin: Data tab
    # ---------------------------
    if admin_mode and tab_data is not None:
        with tab_data:
            render_admin_data(
                {
                "load_metrics_csv": load_metrics_csv,
                "load_demo_df": load_demo_df,
                "refresh_scores": refresh_scores,
                }
            )


    # ---------------------------
    # Admin: Insights tab (bulk summarize + cluster)
    # ---------------------------
    if admin_mode and tab_insights is not None:
        with tab_insights:
            render_admin_insights(
                {
                "ensure_ai": ensure_ai,
                "cached_fetch": cached_fetch,
                "cluster_summaries": cluster_summaries,
                "get_cached_summary": get_cached_summary,
                "set_cached_summary": set_cached_summary,
                "current_summary_language": current_summary_language,
                "build_demo_summary": build_demo_summary,
                "_load_reco_events_df": _load_reco_events_df,
                "_load_upsell_events_df": load_upsell_events_df,
                "_load_content_events_df": _load_content_events_df,
                }
            )



    # ---------------------------
    # Admin: Sponsor/Ads tab
    # ---------------------------
    if admin_mode and tab_sponsor is not None:
        with tab_sponsor:
            render_admin_sponsor(
                {
                    "ensure_ai": ensure_ai,
                    "load_ads": load_ads,
                    "save_ads": save_ads,
                    "log_event": log_event,
                    "Ad": Ad,
                    "api_key": api_key,
                    "model": model,
                    "_load_upsell_events_df": load_upsell_events_df,
                }
            )


    # ---------------------------
    # Admin: Global / SEO tab
    # ---------------------------
    if admin_mode and tab_global is not None:
        with tab_global:
            global_tab.render_admin_global(
                {
                    "t": t,
                    "api_key": api_key,
                    "normalize_lang": normalize_lang,
                    "SEOPage": SEOPage,
                    "render_html": render_html,
                    "slugify": slugify,
                    "cached_fetch": cached_fetch,
                    "build_demo_summary": build_demo_summary,
                    "snippet_from_content": snippet_from_content,
                    "ensure_ai": ensure_ai,
                }
            )


# ---------------------------
# App entry
# ---------------------------
_route_toggle()
if st.session_state.get("route") == "home":
    intent = render_home()
    if intent in {"make", "feed"}:
        st.session_state["route"] = "app"
        st.session_state["_jump_to_make"] = intent == "make"
        st.session_state["_jump_to_feed"] = intent == "feed"
        st.rerun()
else:
    init_state()
    render_app()
