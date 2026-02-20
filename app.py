from __future__ import annotations

import os
import json
import re
import html
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

from modules.metrics import load_metrics_csv, compute_engagement_score, top_by_score, topk_per_category
from modules.fetch import fetch_and_extract
from modules.ai import OpenAIService
from modules.cluster import cluster_summaries
from modules.ads import ensure_ads_storage, load_ads, save_ads, select_ads, log_event, Ad
from modules.i18n import get_translator, normalize_lang
from modules.seo import SEOPage, render_html, slugify
from modules.youtube import fetch_youtube_videos
from modules.ui_article import build_article_header, build_news_row, build_toc, paragraphize_fulltext, build_yt_row

load_dotenv()

st.set_page_config(page_title="StayPick", layout="wide", initial_sidebar_state="collapsed")


# ---------------------------
# Style (portal-ish + dopamine)
# ---------------------------
PORTAL_CSS = """
<style>
/* Hide Streamlit chrome (better for demo videos) */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {visibility: hidden; height: 0px;}
div[data-testid="stToolbar"] {visibility: hidden; height: 0px;}
div[data-testid="stDeployButton"] {display: none;}
html { scroll-behavior: smooth; }

/* App background */
.stApp { background: #f6f7fb; }

/* Compact vertical spacing for denser feed */
.block-container { padding-top: 0.7rem; padding-bottom: 1.1rem; }

/* Sidebar */
section[data-testid="stSidebar"] > div {
  background: linear-gradient(180deg, rgba(255, 99, 71, 0.12), rgba(255,255,255,1) 240px);
  border-right: 1px solid rgba(49, 51, 63, 0.10);
}
.sp-side-brand {
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(49, 51, 63, 0.10);
  background: rgba(255,255,255,0.80);
}
.sp-side-title { font-weight: 900; font-size: 18px; letter-spacing: -0.4px; }
.sp-side-sub { color: rgba(49, 51, 63, 0.70); font-size: 12px; margin-top: 4px; }

/* Top header */
.staypick-header {
  display:flex; align-items:center; gap:10px;
  padding: 8px 12px;
  border:1px solid rgba(49, 51, 63, 0.12);
  border-radius: 14px;
  background: rgba(255,255,255,0.85);
  box-shadow: 0 4px 16px rgba(20, 20, 40, 0.06);
}
.staypick-logo { font-weight: 900; font-size: 20px; letter-spacing: -0.3px; }
.staypick-pill {
  font-size: 12px; padding: 3px 10px; border-radius: 999px;
  border: 1px solid rgba(49, 51, 63, 0.18);
  background: rgba(255,255,255,0.9);
}
.small-muted { color: rgba(49, 51, 63, 0.65); font-size: 12px; }

/* Cards */
.sp-card {
  border: 1px solid rgba(49, 51, 63, 0.12);
  border-radius: 16px;
  padding: 8px 10px;
  background: rgba(255,255,255,0.90);
  box-shadow: 0 6px 18px rgba(20, 20, 40, 0.06);
  transition: transform 120ms ease, box-shadow 120ms ease;
}
.sp-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 28px rgba(20, 20, 40, 0.10);
}
.sp-row { display:flex; gap: 12px; align-items:flex-start; }
.sp-thumb {
  width: 64px; height: 64px; border-radius: 16px;
  display:flex; align-items:center; justify-content:center;
  font-size: 26px; font-weight: 900;
  color: rgba(255,255,255,0.92);
  flex: 0 0 auto;
}
.sp-meta { flex: 1 1 auto; min-width: 0; }
.sp-kicker { font-size: 12px; font-weight: 800; color: rgba(49, 51, 63, 0.65); }
.sp-title { font-weight: 900; font-size: 14px; line-height: 1.22; margin-top: 1px; }
.sp-snippet { font-size: 12px; color: rgba(49, 51, 63, 0.88); line-height: 1.32; margin-top: 4px; }
.hot-title {
  font-size: 13px;
  font-weight: 800;
  line-height: 1.28;
  color: #191b22;
  margin-bottom: 1px;
}
.hot-meta {
  font-size: 11px;
  color: rgba(49, 51, 63, 0.72);
  margin-bottom: 2px;
}
.hot-row {
  display: grid;
  grid-template-columns: 84px 1fr;
  gap: 8px;
  align-items: start;
  margin-bottom: 8px;
}
.hot-row-thumb {
  width: 84px;
  height: 47px;
  border-radius: 8px;
  overflow: hidden;
  background: #eceff3;
}
.hot-row-thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.hot-row-body { min-width: 0; }
.hot-row .hot-title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.sp-chips { margin-top: 8px; }
.sp-chip {
  display:inline-block; padding: 3px 8px; margin: 4px 6px 0 0;
  border-radius: 999px; border: 1px solid rgba(49, 51, 63, 0.16);
  background: rgba(255,255,255,0.7);
  font-size: 12px;
}
.rank-badge {
  font-size: 12px; font-weight: 900;
  padding: 2px 8px; border-radius: 10px;
  border: 1px solid rgba(49, 51, 63, 0.18);
  display: inline-block;
}

/* News-style feed rows */
.news-row {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 14px;
  padding: 14px;
  border: 1px solid rgba(49, 51, 63, 0.12);
  border-radius: 16px;
  background: rgba(255,255,255,0.95);
  box-shadow: 0 6px 18px rgba(20, 20, 40, 0.06);
  margin-bottom: 12px;
}
.news-thumb {
  width: 100%;
  height: 110px;
  border-radius: 12px;
  overflow: hidden;
  background: #eee;
}
.news-thumb img { width: 100%; height: 100%; object-fit: cover; display:block; }
.news-title { font-weight: 900; font-size: 16px; line-height: 1.25; }
.news-meta { color: rgba(49, 51, 63, 0.65); font-size: 12px; margin-top: 4px; }
.news-excerpt { color: rgba(49, 51, 63, 0.92); font-size: 13px; margin-top: 8px; line-height: 1.45; }

/* YouTube-style feed rows */
.yt-row {
  display: grid;
  grid-template-columns: 210px 1fr;
  gap: 10px;
  padding: 10px;
  border: 1px solid rgba(49, 51, 63, 0.10);
  border-radius: 14px;
  background: rgba(255,255,255,0.96);
  box-shadow: 0 6px 18px rgba(20, 20, 40, 0.05);
  margin-bottom: 7px;
}
.yt-row-thumb {
  width: 100%;
  height: 104px;
  border-radius: 10px;
  overflow: hidden;
  background: #eee;
}
.yt-row-thumb img { width: 100%; height: 100%; object-fit: cover; display:block; }
.yt-row-title { font-weight: 900; font-size: 15px; line-height: 1.24; }
.yt-row-channel { font-size: 12px; color: rgba(49, 51, 63, 0.72); margin-top: 5px; }
.yt-row-meta { font-size: 11px; color: rgba(49, 51, 63, 0.66); margin-top: 2px; }
.yt-row-desc { font-size: 12px; color: rgba(49, 51, 63, 0.90); margin-top: 5px; line-height: 1.35; }
.yt-chip {
  display:inline-block; font-size: 11px; font-weight: 800;
  padding: 2px 8px; border-radius: 999px;
  border: 1px solid rgba(49, 51, 63, 0.12);
  background: rgba(255,255,255,0.85);
  margin-right: 6px;
}

/* Article view */
.article-header { margin-bottom: 10px; }
.article-title { font-weight: 900; font-size: 20px; line-height: 1.25; }
.article-meta { color: rgba(49, 51, 63, 0.65); font-size: 12px; margin-top: 6px; }
.article-body {
  padding: 14px;
  border: 1px solid rgba(49, 51, 63, 0.12);
  border-radius: 14px;
  background: rgba(255,255,255,0.95);
  line-height: 1.7;
  max-width: 760px;
}
.article-body p { margin: 0 0 10px 0; }
.article-body h3 {
  font-size: 15px;
  font-weight: 900;
  margin: 16px 0 8px 0;
}
.article-body blockquote {
  margin: 12px 0;
  padding: 10px 12px;
  border-left: 4px solid rgba(49, 51, 63, 0.25);
  background: rgba(49, 51, 63, 0.04);
  border-radius: 8px;
  color: rgba(49, 51, 63, 0.85);
}
.article-body strong { font-weight: 900; }
.article-body em { font-style: italic; }
.toc {
  border: 1px solid rgba(49, 51, 63, 0.12);
  background: rgba(255,255,255,0.9);
  border-radius: 12px;
  padding: 10px 12px;
  margin-bottom: 10px;
  max-width: 760px;
}
.toc-title { font-weight: 900; font-size: 12px; margin-bottom: 6px; }
.toc a { text-decoration: none; font-size: 12px; color: rgba(49, 51, 63, 0.85); }

.yt-detail-card {
  border: 1px solid rgba(49, 51, 63, 0.10);
  border-radius: 14px;
  padding: 12px;
  background: rgba(255,255,255,0.95);
  margin-bottom: 10px;
}
.yt-channel-row { display:flex; gap:10px; align-items:center; }
.yt-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  background: rgba(49, 51, 63, 0.12);
  display:flex; align-items:center; justify-content:center;
  font-weight: 900;
}
.yt-actions { display:flex; gap:8px; flex-wrap:wrap; margin-top: 8px; }
.yt-action-btn {
  display:inline-block; font-size: 12px; font-weight: 800;
  padding: 6px 10px; border-radius: 999px;
  border: 1px solid rgba(49, 51, 63, 0.12);
  background: rgba(255,255,255,0.9);
}

/* Sponsored */
.sp-ad { border: 1px solid rgba(255, 149, 0, 0.35); }
.sp-ad-badge {
  display:inline-block;
  font-size: 11px; font-weight: 900;
  padding: 2px 8px; border-radius: 999px;
  border: 1px solid rgba(255, 149, 0, 0.35);
  background: rgba(255, 236, 179, 0.65);
  margin-right: 6px;
}
.sp-hook {
  font-size: 12px; font-weight: 900;
  color: rgba(49, 51, 63, 0.82);
  margin-top: 2px;
}

/* Buttons a bit rounder */
div.stButton > button {
  border-radius: 12px;
}

/* YouTube-like cards */
.yt-card {
  border: 1px solid rgba(49, 51, 63, 0.10);
  border-radius: 16px;
  background: #fff;
  overflow: hidden;
  box-shadow: 0 4px 14px rgba(20, 20, 40, 0.06);
}
.yt-thumb-wrap {
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #e9eef5;
  position: relative;
  overflow: hidden;
}
.yt-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 180ms ease;
}
.yt-card:hover .yt-thumb-img { transform: scale(1.04); }
.yt-thumb-wrap::after {
  content: "▶";
  position: absolute;
  right: 10px;
  bottom: 8px;
  width: 26px;
  height: 26px;
  border-radius: 999px;
  background: rgba(0,0,0,0.58);
  color: #fff;
  font-size: 12px;
  font-weight: 900;
  display: flex;
  align-items: center;
  justify-content: center;
}
.yt-body {
  padding: 10px 12px 12px;
}
.yt-title {
  font-size: 15px;
  font-weight: 900;
  line-height: 1.3;
  color: #15161b;
  margin: 0;
}
.yt-meta {
  font-size: 12px;
  color: rgba(49, 51, 63, 0.72);
  margin-top: 6px;
}
.yt-channel-line {
  display:flex;
  align-items:center;
  gap: 6px;
  margin-top: 6px;
}
.yt-channel-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #ff3d00;
  display: inline-block;
}
.yt-sub {
  font-size: 12px;
  color: rgba(49, 51, 63, 0.86);
  margin-top: 8px;
}
.yt-topline {
  display:flex;
  align-items:center;
  gap: 6px;
  margin-bottom: 6px;
}

/* Shorts rail */
.short-card {
  border: none;
  border-radius: 12px;
  overflow: hidden;
  background: transparent;
  box-shadow: none;
}
.short-thumb-wrap {
  width: 100%;
  aspect-ratio: 9 / 16;
  background: transparent;
  overflow: hidden;
  position: relative;
  border-radius: 12px;
}
.short-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
  transform: scale(1.0);
  transition: transform 180ms ease;
}
.short-card:hover .short-thumb-img { transform: scale(1.02); }
.short-info {
  padding: 6px 2px 5px;
  background: transparent;
}
.short-title {
  font-size: 12px;
  font-weight: 900;
  line-height: 1.32;
  margin: 0;
  color: #12141a;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.short-meta {
  font-size: 10px;
  color: rgba(49, 51, 63, 0.75);
  margin-top: 5px;
}
.short-link { text-decoration: none; color: inherit; display: block; }
.yt-generated-box {
  border: 1px solid rgba(49, 51, 63, 0.14);
  border-radius: 12px;
  background: #fff;
  padding: 10px 12px;
}
.cat-top-card {
  border: 1px solid rgba(49, 51, 63, 0.12);
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
  box-shadow: 0 3px 10px rgba(20, 20, 40, 0.05);
}
.cat-top-thumb {
  width: 100%;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  display: block;
}
.cat-top-body {
  padding: 8px 10px;
}

/* Mobile: stack columns to 1 */
@media (max-width: 900px) {
  div[data-testid="stHorizontalBlock"] { flex-direction: column !important; }
  div[data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; }
}
</style>
"""
st.markdown(PORTAL_CSS, unsafe_allow_html=True)


# ---------------------------
# Paths & demo
# ---------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEMO_CSV_PATH = os.path.join(APP_DIR, "sample_data", "metrics_sample_fun_with_content.csv")
SUBSCRIPTION_STATE_PATH = os.path.join(APP_DIR, "data", "subscription_state.json")
YOUTUBE_SNAPSHOT_PATH = os.path.join(APP_DIR, "data", "youtube_last_success.csv")
UPSELL_EVENTS_PATH = os.path.join(APP_DIR, "data", "upsell_events.csv")
LANDING_PAGE_PATH = os.path.join(APP_DIR, "StayPick_OnePager_Package", "StayPick_Landing.html")
DEFAULT_YT_QUERY_GROUPS: Dict[str, List[str]] = {
    "game": ["게임 추천", "스팀 게임", "모바일 게임"],
    "finance": ["재테크", "주식 입문", "절약"],
    "love": ["연애 썰", "썸", "이별"],
    "life": ["생활 꿀팁", "청소 꿀팁", "요리 꿀팁"],
    "tech": ["테크 트렌드", "AI 툴", "가젯 리뷰"],
    "trend": ["실시간 이슈", "요즘 화제", "급상승 영상"],
}
FEED_CATEGORY_ORDER = ["game", "finance", "love", "life", "tech", "trend"]
FEED_CATEGORY_EMOJI = {
    "game": "🎮",
    "finance": "💰",
    "love": "💕",
    "life": "🧩",
    "tech": "🤖",
    "trend": "🔥",
}
MONETIZATION_ASSUMPTIONS = {
    # A: conversion-first (more conservative)
    "A": {"paid_rate": 0.018, "pro_share": 0.25},
    # B: value-first (higher conversion/value expectation)
    "B": {"paid_rate": 0.030, "pro_share": 0.38},
}
MONETIZATION_PRICING = {
    # A: lower entry price for conversion
    "A": {"basic": 4900, "pro": 9900},
    # B: higher value capture
    "B": {"basic": 5900, "pro": 12900},
}
ANNUAL_DISCOUNT_RATE = 0.20


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


def _load_landing_html() -> str:
    try:
        if os.path.exists(LANDING_PAGE_PATH):
            with open(LANDING_PAGE_PATH, "r", encoding="utf-8") as f:
                return f.read()
    except Exception:
        return ""
    return ""


def _save_subscription_state() -> None:
    try:
        os.makedirs(os.path.dirname(SUBSCRIPTION_STATE_PATH), exist_ok=True)
        data = {
            "plan_tier": st.session_state.get("plan_tier", "free"),
            "billing_cycle": st.session_state.get("billing_cycle", "monthly"),
            "trial_started_at": st.session_state.get("trial_started_at"),
        }
        with open(SUBSCRIPTION_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _log_upsell_event(event: str, target_plan: str = "", source: str = "sidebar") -> None:
    try:
        os.makedirs(os.path.join(APP_DIR, "data"), exist_ok=True)
        sub = subscription_snapshot()
        row = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": (event or "").strip(),
            "source": (source or "").strip(),
            "from_plan": str(sub.get("tier", "free") or "free"),
            "target_plan": (target_plan or "").strip(),
            "billing_cycle": str(st.session_state.get("billing_cycle", "monthly") or "monthly"),
            "in_trial": bool(sub.get("in_trial", False)),
            "days_left": int(sub.get("days_left", 0) or 0),
            "profile": str(st.session_state.get("monetization_profile", "A") or "A"),
        }
        df_row = pd.DataFrame([row])
        if os.path.exists(UPSELL_EVENTS_PATH):
            df_row.to_csv(UPSELL_EVENTS_PATH, mode="a", index=False, header=False, encoding="utf-8-sig")
        else:
            df_row.to_csv(UPSELL_EVENTS_PATH, mode="w", index=False, header=True, encoding="utf-8-sig")
    except Exception:
        pass


def _load_upsell_events_df() -> pd.DataFrame:
    if not os.path.exists(UPSELL_EVENTS_PATH):
        return pd.DataFrame()
    try:
        return pd.read_csv(UPSELL_EVENTS_PATH)
    except Exception:
        return pd.DataFrame()


def subscription_snapshot() -> Dict[str, Any]:
    trial_days = 14
    started = st.session_state.get("trial_started_at")
    if not started:
        started = datetime.now().date().isoformat()
        st.session_state["trial_started_at"] = started
    try:
        started_dt = datetime.fromisoformat(str(started)).date()
    except Exception:
        started_dt = datetime.now().date()
        st.session_state["trial_started_at"] = started_dt.isoformat()
    trial_ends = started_dt + timedelta(days=trial_days)
    today = datetime.now().date()
    tier = str(st.session_state.get("plan_tier", "free") or "free").lower()
    if tier not in {"free", "basic", "pro"}:
        tier = "free"
    cycle = str(st.session_state.get("billing_cycle", "monthly") or "monthly").lower()
    if cycle not in {"monthly", "annual"}:
        cycle = "monthly"
    in_trial = today <= trial_ends
    paid = tier in {"basic", "pro"}
    premium = paid
    profile = str(st.session_state.get("monetization_profile", "A") or "A").upper()
    pricing = MONETIZATION_PRICING.get(profile, MONETIZATION_PRICING["A"])
    price_basic = int(pricing.get("basic", 4900) or 4900)
    price_pro = int(pricing.get("pro", 9900) or 9900)
    annual_mult = max(0.0, 1.0 - float(ANNUAL_DISCOUNT_RATE))
    return {
        "tier": tier,
        "cycle": cycle,
        "in_trial": in_trial,
        "paid": paid,
        "premium": premium,
        "days_left": max((trial_ends - today).days, 0),
        "trial_ends": trial_ends.isoformat(),
        "price_basic": price_basic,
        "price_pro": price_pro,
        "price_basic_year": int(price_basic * 12 * annual_mult),
        "price_pro_year": int(price_pro * 12 * annual_mult),
    }


def subscription_entitlements(sub: Dict[str, Any]) -> Dict[str, int]:
    profile = str(st.session_state.get("monetization_profile", "A") or "A").upper()
    if profile == "B":
        if str(sub.get("tier", "free") or "free").lower() == "pro":
            return {"save_limit": 1500, "make_limit": 150, "ai_daily_limit": 1500}
        if str(sub.get("tier", "free") or "free").lower() == "basic":
            return {"save_limit": 500, "make_limit": 50, "ai_daily_limit": 500}
        if sub.get("in_trial"):
            return {"save_limit": 80, "make_limit": 20, "ai_daily_limit": 80}
        return {"save_limit": 20, "make_limit": 5, "ai_daily_limit": 10}

    tier = str(sub.get("tier", "free") or "free").lower()
    if tier == "pro":
        return {"save_limit": 1000, "make_limit": 100, "ai_daily_limit": 1000}
    if tier == "basic":
        return {"save_limit": 300, "make_limit": 30, "ai_daily_limit": 300}
    if sub.get("in_trial"):
        return {"save_limit": 50, "make_limit": 10, "ai_daily_limit": 50}
    return {"save_limit": 20, "make_limit": 5, "ai_daily_limit": 10}


def ai_usage_left() -> int:
    sub = subscription_snapshot()
    ent = subscription_entitlements(sub)
    day = datetime.now().strftime("%Y-%m-%d")
    usage = st.session_state.get("ai_usage", {})
    if not isinstance(usage, dict):
        usage = {}
    used = int(usage.get(day, 0) or 0)
    return max(int(ent["ai_daily_limit"]) - used, 0)

# ads storage (inventory + event logs)
ensure_ads_storage(APP_DIR)


# ---------------------------
# i18n (UI language)
# ---------------------------
def _get_query_param(name: str) -> str:
    """Best-effort query param getter across Streamlit versions."""
    try:
        v = st.query_params.get(name)
        if isinstance(v, list):
            return str(v[0]) if v else ""
        return str(v or "")
    except Exception:
        try:
            qp = st.experimental_get_query_params()  # type: ignore[attr-defined]
            v2 = qp.get(name, [""])
            return str(v2[0]) if v2 else ""
        except Exception:
            return ""


def _detect_lang_auto() -> str:
    """Detect UI language.

    Priority:
    1) URL param ?lang=ko|en|ja|es
    2) HTTP Accept-Language header (when deployed)
    3) Default to Korean
    """
    q = (_get_query_param("lang") or "").strip()
    if q:
        return normalize_lang(q)

    # Streamlit provides headers when deployed behind a server.
    try:
        accept = (st.context.headers.get("accept-language") or st.context.headers.get("Accept-Language") or "")  # type: ignore[attr-defined]
    except Exception:
        accept = ""
    if accept:
        first = accept.split(",")[0].strip()
        code = first.split(";")[0].strip()
        return normalize_lang(code)
    return "ko"


# Initialize translator early so the whole app can use it.
_initial_lang = normalize_lang(st.session_state.get("ui_lang") or _detect_lang_auto())
_tr = get_translator(_initial_lang)
t = _tr.t




# ---------------------------
# Sidebar: general users first (cleaner)
# ---------------------------
with st.sidebar:
    # UI language selector (auto / manual)
    ui_lang_choice = st.selectbox(
        t("lang_selector"),
        options=["auto", "ko", "en", "ja", "es"],
        format_func=lambda x: {
            "auto": t("lang_auto"),
            "ko": "한국어",
            "en": "English",
            "ja": "日本語",
            "es": "Español",
        }.get(x, x),
        index=["auto", "ko", "en", "ja", "es"].index(st.session_state.get("ui_lang_choice", "ko")),
        key="ui_lang_choice",
    )

    ui_lang = _detect_lang_auto() if ui_lang_choice == "auto" else normalize_lang(ui_lang_choice)
    if st.session_state.get("ui_lang") != ui_lang:
        st.session_state["ui_lang"] = ui_lang
        # Simple approach: reset language-dependent caches
        st.session_state["summary_cache"] = {}
        st.session_state["selected_summaries"] = []
        st.session_state["open_dialog"] = False
        st.rerun()

    # Update translator after potential rerun
    _tr = get_translator(ui_lang)
    t = _tr.t

    st.markdown(
        f"""
<div class="sp-side-brand">
  <div class="sp-side-title">StayPick</div>
  <div class="sp-side-sub">{html.escape(t('sidebar_sub'))}</div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.write("")

    # Admin mode is hidden by default. Enable only via ?admin=1.
    admin_enabled = (_get_query_param("admin") or "").strip() == "1"
    if admin_enabled:
        try:
            admin_mode = st.toggle(t("admin_toggle"), value=True)
        except Exception:
            admin_mode = st.checkbox(t("admin_toggle"), value=True)
    else:
        admin_mode = False

    # API key: in production, set OPENAI_API_KEY as an environment variable.
    # We hide the input for non-admin users if the env var is present.
    env_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if env_key and not admin_mode:
        api_key = env_key
        st.caption(t("api_key_hidden"))
    else:
        api_key = st.text_input(
            t("api_key"),
            type="password",
            value=env_key,
            help=t("api_key_help"),
        )
    if admin_mode and st.session_state.get("youtube_error"):
        st.warning(f"YouTube source fallback: {st.session_state.get('youtube_error')}")

    # Defaults (safe)
    model = "gpt-4o-mini"
    embedding_model = "text-embedding-3-small"
    top_n = 8
    top_k_per_category = 10
    st.session_state.setdefault("weight_visits", 0.6)
    st.session_state.setdefault("portal_base_w", 0.72)
    st.session_state.setdefault("portal_react_w", 0.18)
    st.session_state.setdefault("portal_recency_w", 0.10)
    st.session_state.setdefault("personal_base_w", 0.9)
    st.session_state.setdefault("personal_cat_w", 0.1)
    st.session_state.setdefault("reco_base_w", 0.9)
    st.session_state.setdefault("reco_click_w", 0.1)
    st.session_state.setdefault("reco_half_life_hours", 24.0)
    st.session_state.setdefault("monetization_profile", "A")
    weight_visits = float(st.session_state.get("weight_visits", 0.6))
    weight_dwell = 1.0 - weight_visits
    sub = subscription_snapshot()

    # User-facing settings (folded)
    with st.expander(t("exp_user"), expanded=True):
        st.caption(
            f"Plan: {sub['tier'].upper()} ({sub['cycle']}) ? Trial left: {sub['days_left']} days ? "
            f"Basic {sub['price_basic']:,}/mo ({sub['price_basic_year']:,}/yr) ? "
            f"Pro {sub['price_pro']:,}/mo ({sub['price_pro_year']:,}/yr)"
        )
        if admin_mode:
            prof = st.selectbox(
                "Monetization profile (A/B)",
                options=["A", "B"],
                format_func=lambda x: "A · Conversion-first" if x == "A" else "B · Value-first",
                index=0 if st.session_state.get("monetization_profile", "A") == "A" else 1,
            )
            st.session_state["monetization_profile"] = prof
        if (not sub.get("paid", False)) and (not sub["in_trial"]):
            st.info("Trial ended. Ads stay on in free plan. Upgrade to remove ads and raise limits.")
        bill_cycle = st.selectbox(
            "Billing",
            options=["monthly", "annual"],
            index=0 if st.session_state.get("billing_cycle", "monthly") == "monthly" else 1,
            key="billing_cycle",
        )
        c_plan0, c_plan1, c_plan2 = st.columns(3)
        with c_plan0:
            if st.button("Use Free"):
                st.session_state["plan_tier"] = "free"
                st.session_state["billing_cycle"] = bill_cycle
                _save_subscription_state()
                st.rerun()
        with c_plan1:
            if st.button("Use Basic"):
                st.session_state["plan_tier"] = "basic"
                st.session_state["billing_cycle"] = bill_cycle
                _save_subscription_state()
                st.rerun()
        with c_plan2:
            if st.button("Use Pro"):
                st.session_state["plan_tier"] = "pro"
                st.session_state["billing_cycle"] = bill_cycle
                _save_subscription_state()
                st.rerun()
        ent_now = subscription_entitlements(sub)
        st.caption(
            f"Current limits · Save {ent_now['save_limit']} · Make {ent_now['make_limit']} · AI/day {ent_now['ai_daily_limit']}"
        )
        st.caption(f"AI credits left today: {ai_usage_left()}")
        if not sub.get("paid", False):
            upsell_msg = "Upgrade to remove ads and raise daily AI credits."
            if sub.get("in_trial"):
                upsell_msg = "You are in trial. Upgrading now keeps higher limits and removes ads after trial."
            st.info(upsell_msg)
            today_key = datetime.now().strftime("%Y-%m-%d")
            if st.session_state.get("_upsell_view_logged_day") != today_key:
                _log_upsell_event("upsell_view", target_plan="")
                st.session_state["_upsell_view_logged_day"] = today_key
            c_up1, c_up2 = st.columns(2)
            with c_up1:
                if st.button("Upgrade to Basic", type="primary"):
                    _log_upsell_event("upsell_click_basic", target_plan="basic")
                    st.session_state["plan_tier"] = "basic"
                    st.session_state["billing_cycle"] = bill_cycle
                    _save_subscription_state()
                    _log_upsell_event("upgrade_applied_basic", target_plan="basic")
                    st.success("Basic plan applied.")
                    st.rerun()
            with c_up2:
                if st.button("Upgrade to Pro"):
                    _log_upsell_event("upsell_click_pro", target_plan="pro")
                    st.session_state["plan_tier"] = "pro"
                    st.session_state["billing_cycle"] = bill_cycle
                    _save_subscription_state()
                    _log_upsell_event("upgrade_applied_pro", target_plan="pro")
                    st.success("Pro plan applied.")
                    st.rerun()
        if st.session_state.get("plan_tier", "free") in {"free", "basic", "pro"}:
            if st.button("Reset trial (demo)"):
                st.session_state["trial_started_at"] = datetime.now().date().isoformat()
                _save_subscription_state()
                st.success("Trial reset.")
                st.rerun()

        try:
            show_ads = st.toggle(t("toggle_ads"), value=True)
            show_metrics = st.toggle(t("toggle_metrics"), value=False)
            # For general users: make "View" instantly satisfying.
            auto_summarize = st.toggle(t("toggle_auto_summary"), value=True)
        except Exception:
            show_ads = st.checkbox(t("toggle_ads"), value=True)
            show_metrics = st.checkbox(t("toggle_metrics"), value=False)
            auto_summarize = st.checkbox(t("toggle_auto_summary"), value=True)
        if not sub.get("paid", False):
            show_ads = True

        teaser_mode = st.selectbox(
            t("teaser_mode"),
            options=["snippet", "ai"],
            format_func=lambda x: t("teaser_opt_snippet") if x == "snippet" else t("teaser_opt_ai"),
            index=0,
            help="AI 한줄요약은 ‘상세 보기’에서 1회 생성(캐시됨).",
        )

    # Make settings can feel "expert" for first-time users.
    # Keep the essentials visible and tuck advanced controls away.
    with st.expander(t("exp_make"), expanded=False):
        age_group = st.selectbox(
            t("age_group"),
            options=["general", "elem", "mid", "high", "uni", "20s", "30s"],
            format_func=lambda x: {
                "general": t("age_general"),
                "elem": t("age_elem"),
                "mid": t("age_mid"),
                "high": t("age_high"),
                "uni": t("age_uni"),
                "20s": t("age_20s"),
                "30s": t("age_30s"),
            }.get(x, x),
            index=["general", "elem", "mid", "high", "uni", "20s", "30s"].index(st.session_state.get("age_group", "general")),
            key="age_group",
            help="연령/라이프스테이지에 맞춰 요약/훅/새 콘텐츠 난이도를 조절합니다.",
        )
        # If age group changes, clear cached summaries (they are tailored to the audience)
        if st.session_state.get("_prev_age_group") not in (None, age_group):
            st.session_state["summary_cache"] = {}
        st.session_state["_prev_age_group"] = age_group

        persona = st.selectbox(
            t("persona"),
            options=[
                "일반 유저(입문자)",
                "직장인(가볍게 읽기)",
                "스타트업 마케터",
                "PM/PO",
                "개발자/데이터",
            ],
            index=0,
        )
        output_format = st.selectbox(
            t("output_format"),
            options=[
                "친구에게 보내는 추천글(짧게)",
                "3줄 요약(초간단)",
                "블로그 포스트(1200~1600자)",
                "X(트위터) 스레드(8~10개)",
                "숏폼 영상 대본(60초)",
            ],
            index=0,
        )
        content_lang_choice = st.selectbox(
            t("output_lang"),
            options=["auto", "ko", "en", "ja", "es"],
            format_func=lambda x: {
                "auto": t("lang_auto"),
                "ko": "한국어",
                "en": "English",
                "ja": "日本語",
                "es": "Español",
            }.get(x, x),
            index=["auto", "ko", "en", "ja", "es"].index(st.session_state.get("content_lang_choice", "auto")),
            key="content_lang_choice",
            help="생성되는 요약/새 콘텐츠 언어를 고릅니다. Auto는 화면 언어를 따릅니다.",
        )
        content_lang = ui_lang if content_lang_choice == "auto" else normalize_lang(content_lang_choice)
        st.session_state["content_lang"] = content_lang

        with st.expander(t("exp_make_advanced"), expanded=False):
            brand_tone = st.text_area(
                t("tone"),
                placeholder="예: 훅은 세게, 밈은 과하지 않게, 마지막에 한줄 결론",
                height=90,
            )
    # Defaults when advanced expander is collapsed (keeps app stable)
    persona = locals().get("persona", "일반 유저(입문자)")
    output_format = locals().get("output_format", "친구에게 보내는 추천글(짧게)")
    brand_tone = locals().get("brand_tone", "")

    if admin_mode:
        with st.expander(t("exp_admin"), expanded=True):
            model_choice = st.selectbox(
                "텍스트 생성 모델",
                options=[
                    "gpt-4o-mini",
                    "gpt-4o",
                    "gpt-4.1-mini",
                    "gpt-4.1",
                    "custom",
                ],
                index=0,
            )
            if model_choice == "custom":
                model = st.text_input("커스텀 모델 ID", value="gpt-4o-mini")
            else:
                model = model_choice

            embedding_model = st.selectbox(
                "임베딩 모델(클러스터링)",
                options=["text-embedding-3-small", "text-embedding-3-large"],
                index=0,
            )

            top_n = st.slider("일괄 요약할 Top N", min_value=1, max_value=20, value=8)
            top_k_per_category = st.slider("카테고리별 Top K(홈)", min_value=3, max_value=30, value=10)

            weight_visits = st.slider(
                "스코어 가중치: 방문수",
                min_value=0.0,
                max_value=1.0,
                value=float(st.session_state.get("weight_visits", 0.6)),
                step=0.05,
            )
            st.session_state["weight_visits"] = float(weight_visits)
            weight_dwell = 1.0 - weight_visits
            st.caption(f"체류시간 가중치 = {weight_dwell:.2f}")

            st.markdown("#### Recommendation tuning")
            pb = st.slider("portal base", min_value=0.0, max_value=1.0, value=float(st.session_state.get("portal_base_w", 0.72)), step=0.01)
            pr = st.slider("portal reactions", min_value=0.0, max_value=1.0, value=float(st.session_state.get("portal_react_w", 0.18)), step=0.01)
            pc = st.slider("portal recency", min_value=0.0, max_value=1.0, value=float(st.session_state.get("portal_recency_w", 0.10)), step=0.01)
            s = max(pb + pr + pc, 1e-9)
            st.session_state["portal_base_w"] = pb / s
            st.session_state["portal_react_w"] = pr / s
            st.session_state["portal_recency_w"] = pc / s
            st.caption(
                f"normalized: {st.session_state['portal_base_w']:.2f} / "
                f"{st.session_state['portal_react_w']:.2f} / {st.session_state['portal_recency_w']:.2f}"
            )
            st.session_state["personal_base_w"] = st.slider("feed base score", min_value=0.0, max_value=1.0, value=float(st.session_state.get("personal_base_w", 0.9)), step=0.05)
            st.session_state["personal_cat_w"] = st.slider("feed category preference", min_value=0.0, max_value=1.0, value=float(st.session_state.get("personal_cat_w", 0.1)), step=0.05)
            st.session_state["reco_base_w"] = st.slider("reco base score", min_value=0.0, max_value=1.0, value=float(st.session_state.get("reco_base_w", 0.9)), step=0.05)
            st.session_state["reco_click_w"] = st.slider("reco click boost", min_value=0.0, max_value=1.0, value=float(st.session_state.get("reco_click_w", 0.1)), step=0.05)
            st.session_state["reco_half_life_hours"] = st.slider("reco decay half-life (hours)", min_value=6.0, max_value=168.0, value=float(st.session_state.get("reco_half_life_hours", 24.0)), step=1.0)

            st.markdown("#### Quality ranking (A/B)")
            st.session_state["rank_ab_mode"] = st.selectbox(
                "ranking mode",
                options=["baseline", "quality", "ab"],
                format_func=lambda x: {"baseline": "baseline (control)", "quality": "quality score", "ab": "A/B split"}[x],
                index=["baseline", "quality", "ab"].index(st.session_state.get("rank_ab_mode", "baseline")),
            )
            st.session_state["quality_mix_w"] = st.slider("quality mix weight", min_value=0.0, max_value=1.0, value=float(st.session_state.get("quality_mix_w", 0.35)), step=0.05)
            st.session_state["quality_ctr_w"] = st.slider("quality CTR weight", min_value=0.0, max_value=1.0, value=float(st.session_state.get("quality_ctr_w", 0.45)), step=0.05)
            st.session_state["quality_dwell_w"] = st.slider("quality dwell weight", min_value=0.0, max_value=1.0, value=float(st.session_state.get("quality_dwell_w", 0.35)), step=0.05)
            st.session_state["quality_skip_w"] = st.slider("quality skip weight", min_value=0.0, max_value=1.0, value=float(st.session_state.get("quality_skip_w", 0.20)), step=0.05)
            st.session_state["skip_threshold_sec"] = st.slider("skip threshold (sec)", min_value=3.0, max_value=30.0, value=float(st.session_state.get("skip_threshold_sec", 8.0)), step=1.0)

            st.markdown("#### YouTube source")
            st.session_state["yt_region"] = st.text_input("YT region", value=st.session_state.get("yt_region", "KR")).upper()
            st.session_state["yt_lang"] = st.text_input("YT language", value=st.session_state.get("yt_lang", "ko"))
            st.session_state["yt_kr_ratio"] = st.slider("KR mix ratio", min_value=0.5, max_value=0.9, value=float(st.session_state.get("yt_kr_ratio", 0.7)), step=0.05)
            st.session_state["yt_cache_ttl_min"] = st.slider("YT cache TTL (min)", min_value=10, max_value=30, value=int(st.session_state.get("yt_cache_ttl_min", 15)))
            st.session_state["yt_max_per_query"] = st.slider("YT max/query", min_value=3, max_value=20, value=int(st.session_state.get("yt_max_per_query", 8)))
            raw_groups = json.dumps(st.session_state.get("yt_query_groups", DEFAULT_YT_QUERY_GROUPS), ensure_ascii=False, indent=2)
            groups_txt = st.text_area("YT category queries (JSON)", value=raw_groups, height=180)
            if st.button("Apply YT query config"):
                try:
                    parsed = json.loads(groups_txt)
                    if isinstance(parsed, dict) and parsed:
                        st.session_state["yt_query_groups"] = parsed
                        st.session_state["_yt_reload_requested"] = True
                        st.success("YouTube query config saved.")
                        st.rerun()
                    else:
                        st.error("Invalid JSON object")
                except Exception as e:
                    st.error(f"Invalid JSON: {e}")


# ---------------------------
# Helpers / State
# ---------------------------
@st.cache_data(show_spinner=False, ttl=60 * 60)
def cached_fetch(url: str) -> Tuple[str, str]:
    return fetch_and_extract(url)


def ensure_ai() -> OpenAIService:
    return OpenAIService(api_key=api_key, model=model, embedding_model=embedding_model)


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


def _is_shorts_item(row: Dict[str, Any]) -> bool:
    t = str(row.get("title", "") or "").lower()
    d = float(row.get("duration_sec", 0) or 0)
    u = str(row.get("url", "") or "").lower()
    desc = str(row.get("description", "") or "").lower()
    return bool(row.get("is_short", False)) or (d > 0 and d <= 180) or ("shorts" in t) or ("/shorts/" in u) or ("#shorts" in t) or ("#shorts" in desc)


def refresh_scores() -> None:
    """Recompute df_scored/top tables when weights or dataset changes."""
    if "df_raw" not in st.session_state or st.session_state["df_raw"] is None:
        return
    df_raw: pd.DataFrame = st.session_state["df_raw"]
    df_scored = compute_engagement_score(df_raw, weight_visits=weight_visits, weight_dwell=weight_dwell)
    if "kr_views" not in df_scored.columns:
        df_scored["kr_views"] = 0.0
    df_scored["kr_views"] = pd.to_numeric(df_scored.get("kr_views", 0), errors="coerce").fillna(0.0)
    df_scored["portal_score"] = _compute_portal_score(df_scored)
    st.session_state["df_scored"] = df_scored
    st.session_state["top_df"] = top_by_score(df_scored, top_n=top_n)
    st.session_state["topk_cat_df"] = topk_per_category(df_scored, top_k=top_k_per_category)


def _load_subscription_state() -> Dict[str, Any]:
    try:
        if os.path.exists(SUBSCRIPTION_STATE_PATH):
            with open(SUBSCRIPTION_STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {}


def _save_subscription_state() -> None:
    try:
        os.makedirs(os.path.dirname(SUBSCRIPTION_STATE_PATH), exist_ok=True)
        data = {
            "plan_tier": st.session_state.get("plan_tier", "free"),
            "billing_cycle": st.session_state.get("billing_cycle", "monthly"),
            "trial_started_at": st.session_state.get("trial_started_at"),
        }
        with open(SUBSCRIPTION_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def init_state() -> None:
    query_profile_version = "v2_kr_priority"
    if st.session_state.get("_yt_query_profile_version") != query_profile_version:
        st.session_state["_yt_query_profile_version"] = query_profile_version
        st.session_state["_yt_reload_requested"] = True

    st.session_state.setdefault("feed_category", "trend")
    if "df_raw" not in st.session_state:
        try:
            st.session_state["df_raw"] = load_youtube_df(selected_category=st.session_state.get("feed_category", "trend"))
            _save_youtube_snapshot(st.session_state["df_raw"])
            st.session_state["data_source"] = "youtube"
            st.session_state["youtube_error"] = ""
        except Exception as e:
            snap = _load_youtube_snapshot()
            if not snap.empty:
                st.session_state["df_raw"] = snap
                st.session_state["data_source"] = "youtube_snapshot"
                st.session_state["youtube_error"] = f"{e} (fallback: last successful snapshot)"
            else:
                st.session_state["df_raw"] = pd.DataFrame(columns=["url", "title", "visits", "avg_dwell_sec", "content", "category"])
                st.session_state["data_source"] = "youtube"
                st.session_state["youtube_error"] = str(e)

    st.session_state.setdefault("summary_cache", {})  # url -> summary dict
    st.session_state.setdefault("ad_impressions", set())  # (ad|placement|context)
    st.session_state.setdefault("reco_click_counts", {})  # url -> recommendation clicks
    st.session_state.setdefault("clicked_category_counts", {})  # category -> recommendation clicks
    st.session_state.setdefault("watch_history", [])  # recent viewed items with dwell
    st.session_state.setdefault("watch_dwell_by_url", {})  # url -> total dwell seconds
    st.session_state.setdefault("watch_dwell_by_cat", {})  # category -> total dwell seconds
    st.session_state.setdefault("fulltext_cache", {})
    st.session_state.setdefault("content_impressions", set())
    st.session_state.setdefault("skip_threshold_sec", 8.0)
    st.session_state.setdefault("quality_ctr_w", 0.45)
    st.session_state.setdefault("quality_dwell_w", 0.35)
    st.session_state.setdefault("quality_skip_w", 0.20)
    st.session_state.setdefault("quality_mix_w", 0.35)
    st.session_state.setdefault("rank_ab_mode", "baseline")
    st.session_state.setdefault("rank_variant", "control")
    st.session_state.setdefault("_ab_seed", random.random())
    st.session_state.setdefault("_rank_ab_mode_prev", st.session_state.get("rank_ab_mode", "baseline"))
    st.session_state.setdefault("last_open_source", "")
    st.session_state.setdefault("last_open_variant", "")
    st.session_state.setdefault("item_opened_at", None)  # current dialog start timestamp
    st.session_state.setdefault("autoplay_next", True)
    st.session_state.setdefault("autoplay_delay_sec", 3)
    st.session_state.setdefault("_dlg_next_url", "")
    st.session_state.setdefault("hidden_urls", [])
    st.session_state.setdefault("hidden_recent", [])
    st.session_state.setdefault("selected_summaries", [])  # list of summary dicts
    st.session_state.setdefault("generated_by_url", {})  # url -> generated markdown + meta
    st.session_state.setdefault("last_generated_content", {})  # quick access for make tab
    st.session_state.setdefault("generated_history", [])  # my page history
    st.session_state.setdefault("selected_url", "")
    st.session_state.setdefault("open_dialog", False)
    st.session_state.setdefault("search_query", "")
    st.session_state.setdefault("interest_cats", [])
    st.session_state.setdefault("yt_region", "KR")
    st.session_state.setdefault("yt_lang", "ko")
    st.session_state.setdefault("yt_kr_ratio", 0.7)
    st.session_state.setdefault("yt_published_days", 7)
    st.session_state.setdefault("yt_cache_ttl_min", 15)
    st.session_state.setdefault("yt_max_per_query", 8)
    st.session_state.setdefault("yt_query_groups", {k: list(v) for k, v in DEFAULT_YT_QUERY_GROUPS.items()})
    ttl_min = min(max(int(st.session_state.get("yt_cache_ttl_min", 15) or 15), 10), 30)
    bucket = int(time.time() // (ttl_min * 60))
    prev_bucket = st.session_state.get("_yt_bucket")
    if st.session_state.get("data_source") == "youtube" and prev_bucket != bucket and not st.session_state.get("_yt_reload_requested"):
        try:
            st.session_state["df_raw"] = load_youtube_df(selected_category=st.session_state.get("feed_category", "trend"))
            _save_youtube_snapshot(st.session_state["df_raw"])
            st.session_state["youtube_error"] = ""
        except Exception as e:
            st.session_state["youtube_error"] = str(e)
    st.session_state["_yt_bucket"] = bucket
    if st.session_state.get("_yt_reload_requested"):
        try:
            st.session_state["df_raw"] = load_youtube_df(selected_category=st.session_state.get("feed_category", "trend"))
            _save_youtube_snapshot(st.session_state["df_raw"])
            st.session_state["data_source"] = "youtube"
            st.session_state["youtube_error"] = ""
        except Exception as e:
            snap = _load_youtube_snapshot()
            if not snap.empty:
                st.session_state["df_raw"] = snap
                st.session_state["data_source"] = "youtube_snapshot"
                st.session_state["youtube_error"] = f"{e} (fallback: last successful snapshot)"
            else:
                st.session_state["youtube_error"] = str(e)
        st.session_state["_yt_reload_requested"] = False
    if "_subscription_loaded" not in st.session_state:
        ss = _load_subscription_state()
        if ss:
            st.session_state.setdefault("plan_tier", str(ss.get("plan_tier", "free") or "free"))
            st.session_state.setdefault("billing_cycle", str(ss.get("billing_cycle", "monthly") or "monthly"))
            if ss.get("trial_started_at"):
                st.session_state.setdefault("trial_started_at", str(ss.get("trial_started_at")))
        st.session_state["_subscription_loaded"] = True
    st.session_state.setdefault("plan_tier", "free")
    st.session_state.setdefault("billing_cycle", "monthly")
    refresh_scores()


init_state()


def subscription_snapshot() -> Dict[str, Any]:
    trial_days = 14
    started = st.session_state.get("trial_started_at")
    if not started:
        started = datetime.now().date().isoformat()
        st.session_state["trial_started_at"] = started
        _save_subscription_state()
    try:
        started_dt = datetime.fromisoformat(str(started)).date()
    except Exception:
        started_dt = datetime.now().date()
        st.session_state["trial_started_at"] = started_dt.isoformat()
        _save_subscription_state()

    trial_ends = started_dt + timedelta(days=trial_days)
    today = datetime.now().date()
    in_trial = today <= trial_ends

    tier = str(st.session_state.get("plan_tier", "free") or "free").lower()
    if tier not in {"free", "basic", "pro"}:
        tier = "free"
    cycle = str(st.session_state.get("billing_cycle", "monthly") or "monthly").lower()
    if cycle not in {"monthly", "annual"}:
        cycle = "monthly"
    paid = tier in {"basic", "pro"}
    premium = paid
    days_left = max((trial_ends - today).days, 0)
    profile = str(st.session_state.get("monetization_profile", "A") or "A").upper()
    pricing = MONETIZATION_PRICING.get(profile, MONETIZATION_PRICING["A"])
    price_basic = int(pricing.get("basic", 4900) or 4900)
    price_pro = int(pricing.get("pro", 9900) or 9900)
    annual_mult = max(0.0, 1.0 - float(ANNUAL_DISCOUNT_RATE))
    price_basic_year = int(price_basic * 12 * annual_mult)
    price_pro_year = int(price_pro * 12 * annual_mult)
    return {
        "tier": tier,
        "cycle": cycle,
        "in_trial": in_trial,
        "paid": paid,
        "premium": premium,
        "days_left": days_left,
        "trial_ends": trial_ends.isoformat(),
        "price_basic": price_basic,
        "price_pro": price_pro,
        "price_basic_year": price_basic_year,
        "price_pro_year": price_pro_year,
    }


def subscription_entitlements(sub: Dict[str, Any]) -> Dict[str, int]:
    profile = str(st.session_state.get("monetization_profile", "A") or "A").upper()
    if profile == "B":
        if str(sub.get("tier", "free") or "free").lower() == "pro":
            return {"save_limit": 1500, "make_limit": 150, "ai_daily_limit": 1500}
        if str(sub.get("tier", "free") or "free").lower() == "basic":
            return {"save_limit": 500, "make_limit": 50, "ai_daily_limit": 500}
        if sub.get("in_trial"):
            return {"save_limit": 80, "make_limit": 20, "ai_daily_limit": 80}
        return {"save_limit": 20, "make_limit": 5, "ai_daily_limit": 10}

    tier = str(sub.get("tier", "free") or "free").lower()
    if tier == "pro":
        return {"save_limit": 1000, "make_limit": 100, "ai_daily_limit": 1000}
    if tier == "basic":
        return {"save_limit": 300, "make_limit": 30, "ai_daily_limit": 300}
    if sub.get("in_trial"):
        return {"save_limit": 50, "make_limit": 10, "ai_daily_limit": 50}
    return {"save_limit": 20, "make_limit": 5, "ai_daily_limit": 10}


def _today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def ai_usage_left() -> int:
    sub = subscription_snapshot()
    ent = subscription_entitlements(sub)
    day = _today_key()
    usage = st.session_state.get("ai_usage", {})
    if not isinstance(usage, dict):
        usage = {}
    used = int(usage.get(day, 0) or 0)
    return max(int(ent["ai_daily_limit"]) - used, 0)


def consume_ai_credit() -> bool:
    left = ai_usage_left()
    if left <= 0:
        return False
    day = _today_key()
    usage = st.session_state.get("ai_usage", {})
    if not isinstance(usage, dict):
        usage = {}
    usage[day] = int(usage.get(day, 0) or 0) + 1
    st.session_state["ai_usage"] = usage
    return True


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


def emoji_for_category(cat: str) -> str:
    c = (cat or "").lower()
    mapping = {
        "ai": "🤖",
        "tech": "🧠",
        "product": "🧩",
        "startup": "🚀",
        "career": "💼",
        "travel": "🧳",
        "food": "🍜",
        "game": "🎮",
        "fun": "😂",
        "ent": "🎬",
        "love": "💘",
        "sports": "⚽",
        "finance": "💰",
        "news": "🗞️",
        "전체": "🔥",
    }
    for k, v in mapping.items():
        if k in c:
            return v
    return "✨"


def gradient_for_seed(seed: str) -> str:
    """Return a nice gradient background style from a stable seed."""
    palettes = [
        ("#ff5f6d", "#ffc371"),
        ("#36d1dc", "#5b86e5"),
        ("#a18cd1", "#fbc2eb"),
        ("#f953c6", "#b91d73"),
        ("#43cea2", "#185a9d"),
        ("#ff9966", "#ff5e62"),
        ("#7f7fd5", "#86a8e7"),
    ]
    idx = abs(hash(seed or "seed")) % len(palettes)
    a, b = palettes[idx]
    return f"background: linear-gradient(135deg, {a}, {b});"


def chips_to_html(chips: List[str], max_items: int = 3) -> str:
    items = [c for c in (chips or []) if str(c).strip()][:max_items]
    if not items:
        return ""
    return "".join([f"<span class='sp-chip'>{html.escape(str(x))}</span>" for x in items])


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


def _is_youtube_url(url: str) -> bool:
    u = str(url or "").lower()
    return ("youtube.com/watch" in u) or ("youtu.be/" in u) or ("youtube.com/shorts/" in u)


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
# Header
# ---------------------------
header_left, header_right = st.columns([1.2, 3.8], vertical_alignment="center")
with header_left:
    st.markdown(
        f"""
<div class="staypick-header">
  <div class="staypick-logo">StayPick</div>
  <div class="staypick-pill">{html.escape(t('header_pill'))}</div>
</div>
""",
        unsafe_allow_html=True,
    )
with header_right:
    st.session_state["search_query"] = st.text_input(
        "검색",
        value=st.session_state.get("search_query", ""),
        placeholder="검색: 카테고리/제목/키워드",
        label_visibility="collapsed",
    )

st.caption(t("header_caption"))


# ---------------------------
# Tabs (general users first)
# ---------------------------
tab_names = [t("tab_feed"), "활용법", t("tab_make"), "마이페이지", "랜딩"]
if admin_mode:
    tab_names += [t("tab_data"), t("tab_insights"), t("tab_sponsor"), t("tab_global")]
tabs = st.tabs(tab_names)

_ti = 0
tab_feed = tabs[_ti]
_ti += 1
tab_guide = tabs[_ti]
_ti += 1
tab_make = tabs[_ti]
_ti += 1
tab_mypage = tabs[_ti]
_ti += 1
tab_landing = tabs[_ti]
_ti += 1
tab_data = tabs[_ti] if admin_mode else None
if admin_mode:
    _ti += 1
tab_insights = tabs[_ti] if admin_mode else None
if admin_mode:
    _ti += 1
tab_sponsor = tabs[_ti] if admin_mode else None
if admin_mode:
    _ti += 1
tab_global = tabs[_ti] if admin_mode else None


# ---------------------------
# Feed tab (portal-like)
# ---------------------------
with tab_feed:
    df_scored: pd.DataFrame = st.session_state.get("df_scored", pd.DataFrame())
    topk_cat_df: pd.DataFrame = st.session_state.get("topk_cat_df", pd.DataFrame())
    search_q = (st.session_state.get("search_query") or "").strip().lower()

    feed_options = [c for c in FEED_CATEGORY_ORDER if c in _youtube_query_groups()]
    if not feed_options:
        feed_options = FEED_CATEGORY_ORDER
    current_feed_cat = st.session_state.get("feed_category", "trend")
    if current_feed_cat not in feed_options:
        current_feed_cat = feed_options[0]
        st.session_state["feed_category"] = current_feed_cat
    feed_cat = current_feed_cat
    cat_pick_cols = st.columns(len(feed_options), gap="small")
    for idx, opt in enumerate(feed_options, start=1):
        with cat_pick_cols[idx - 1]:
            label = f"{FEED_CATEGORY_EMOJI.get(opt, '🔥')} {opt}"
            is_active = opt == current_feed_cat
            if st.button(label, key=f"feed_cat_btn_{opt}_{idx}", type=("primary" if is_active else "secondary"), use_container_width=True):
                feed_cat = opt
    c_auto1, c_auto2, c_auto3 = st.columns([1.2, 1.2, 1.2])
    with c_auto1:
        st.toggle("Autoplay next", key="autoplay_next", help="상세 모달에서 닫기를 누르면 다음 추천으로 자동 이동합니다.")
    with c_auto2:
        delay_opt = st.selectbox("Autoplay delay", options=[3, 5, 8], index=[3, 5, 8].index(int(st.session_state.get("autoplay_delay_sec", 3))), key="autoplay_delay_selector")
        st.session_state["autoplay_delay_sec"] = int(delay_opt)
    with c_auto3:
        if st.button("Undo not interested", key="undo_not_interested_btn"):
            if undo_not_interested():
                st.rerun()
    if feed_cat != st.session_state.get("feed_category"):
        st.session_state["feed_category"] = feed_cat
        try:
            st.session_state["df_raw"] = load_youtube_df(selected_category=feed_cat)
            _save_youtube_snapshot(st.session_state["df_raw"])
            st.session_state["data_source"] = "youtube"
            st.session_state["youtube_error"] = ""
            refresh_scores()
        except Exception as e:
            snap = _load_youtube_snapshot()
            if not snap.empty:
                st.session_state["df_raw"] = snap
                st.session_state["data_source"] = "youtube_snapshot"
                st.session_state["youtube_error"] = f"{e} (fallback: last successful snapshot)"
                refresh_scores()
            else:
                st.session_state["youtube_error"] = str(e)
        st.rerun()

    yt_err = str(st.session_state.get("youtube_error", "") or "")
    if yt_err:
        if "YOUTUBE_API_KEY" in yt_err:
            st.warning("YouTube API key가 없어 실데이터를 불러오지 못했습니다. 운영자에게 YOUTUBE_API_KEY 설정을 요청하세요.")
        elif "10061" in yt_err or "Connection refused" in yt_err or "연결을 거부" in yt_err:
            st.warning("YouTube API 연결이 차단되었습니다(네트워크/방화벽/프록시). 연결 허용 후 자동으로 실데이터로 복귀합니다.")
        else:
            st.warning(f"YouTube 실데이터 로드 실패: {yt_err}")

    if df_scored.empty:
        st.warning("데이터가 없습니다. (운영자 모드 → 데이터 탭에서 넣을 수 있어요)")
        st.stop()

    # Category stats for menu
    cat_stats = (
        df_scored.groupby("category", as_index=False)
        .agg(items=("url", "count"), total_score=("portal_score", "sum"))
        .sort_values(["total_score", "items"], ascending=False)
    )
    categories = cat_stats["category"].tolist()
    if not categories:
        categories = ["전체"]

    interest_cats = [st.session_state.get("feed_category", feed_cat)]
    st.session_state["interest_cats"] = interest_cats
    st.session_state.setdefault("shorts_show_n", 12)
    st.session_state.setdefault("long_show_n", 9)

    watch_hist = st.session_state.get("watch_history", [])
    today_sec = _today_watch_seconds()
    streak_n = _watch_streak_count()
    s1, s2, s3 = st.columns([1, 1, 1])
    with s1:
        st.caption(f"Today watched: {int(today_sec // 60)}m {int(today_sec % 60)}s")
    with s2:
        st.caption(f"Watch streak: {streak_n}")
    with s3:
        if st.button("Clear history", key="clear_watch_history_btn"):
            st.session_state["watch_history"] = []
            st.session_state["watch_dwell_by_url"] = {}
            st.session_state["watch_dwell_by_cat"] = {}
            st.rerun()
    if isinstance(watch_hist, list) and watch_hist:
        recent = pd.DataFrame(watch_hist)
        if not recent.empty and "url" in recent.columns:
            recent = recent.sort_values("ts", ascending=False).drop_duplicates(subset=["url"], keep="first").head(5)
            st.markdown("### Continue watching")
            cols_cw = st.columns(5, gap="small")
            for i, rec in enumerate(recent.to_dict(orient="records"), start=1):
                with cols_cw[(i - 1) % 5]:
                    u = str(rec.get("url", "") or "").strip()
                    t0 = str(rec.get("title", "") or u).strip()
                    ch0 = str(rec.get("channel_title", "") or "").strip()
                    th0 = str(rec.get("thumbnail_url", "") or "").strip()
                    cat0 = str(rec.get("category", "") or "").strip() or "전체"
                    d0 = float(rec.get("dwell_sec", 0) or 0)
                    _log_content_impression_once(u, cat0, "continue", variant=str(st.session_state.get("rank_variant", "control") or "control"))
                    if th0:
                        st.image(th0, use_container_width=True)
                    lbl = f"{t0[:26]}{'...' if len(t0) > 26 else ''}\n{int(d0)}s watched"
                    if ch0:
                        st.caption(ch0[:28] + ("..." if len(ch0) > 28 else ""))
                    if st.button(lbl, key=f"cw_{i}_{abs(hash(u)) % 100000}"):
                        open_item(u, source="continue")

    # Filter base
    df_overall = df_scored.copy()
    hidden_urls = set(st.session_state.get("hidden_urls", []) or [])
    if hidden_urls:
        df_overall = df_overall[~df_overall["url"].isin(list(hidden_urls))]

    if search_q:
        mask = (
            df_overall["title"].astype(str).str.lower().str.contains(search_q, na=False)
            | df_overall["url"].astype(str).str.lower().str.contains(search_q, na=False)
            | df_overall["content"].astype(str).str.lower().str.contains(search_q, na=False)
        )
        df_overall = df_overall[mask]

    df_overall["cat_pref_boost"] = _category_click_boost(df_overall)
    df_overall["watch_boost"] = _watch_dwell_boost(df_overall)
    feed_base_w = float(st.session_state.get("personal_base_w", 0.9) or 0.9)
    feed_cat_w = float(st.session_state.get("personal_cat_w", 0.1) or 0.1)
    feed_watch_w = max(0.0, 1.0 - (feed_base_w + feed_cat_w))
    df_overall["personal_score"] = (
        pd.to_numeric(df_overall.get("portal_score", 0), errors="coerce").fillna(0.0) * feed_base_w
        + df_overall["cat_pref_boost"] * feed_cat_w
        + df_overall["watch_boost"] * feed_watch_w
    )
    df_overall = _compute_quality_score(df_overall)
    rank_variant = _resolve_rank_variant()
    quality_mix_w = float(st.session_state.get("quality_mix_w", 0.35) or 0.35)
    df_overall["rank_score"] = (
        pd.to_numeric(df_overall.get("personal_score", 0), errors="coerce").fillna(0.0) * (1.0 - quality_mix_w)
        + pd.to_numeric(df_overall.get("quality_score", 0), errors="coerce").fillna(0.0) * quality_mix_w
    )
    df_overall["kr_views"] = pd.to_numeric(df_overall.get("kr_views", 0), errors="coerce").fillna(0.0)
    if rank_variant == "quality":
        df_overall = df_overall.sort_values(["kr_views", "rank_score", "personal_score", "portal_score", "engagement_score", "visits"], ascending=False)
    else:
        df_overall = df_overall.sort_values(["kr_views", "personal_score", "portal_score", "engagement_score", "visits"], ascending=False)
    if admin_mode:
        st.caption(f"Ranking variant: {rank_variant} (mode: {st.session_state.get('rank_ab_mode', 'baseline')})")

    df_view = df_overall.copy()
    if interest_cats:
        df_view = df_view[df_view["category"].isin(interest_cats)]

    main_col, side_col = st.columns([4.0, 1.0], gap="medium")

    # ---- Ads (native sponsored cards) ----
    ads_inv = load_ads(APP_DIR)
    ctx_keywords = compute_trending_keywords(df_overall.head(50), top_k=12)
    ctx_categories = interest_cats or categories[:3]

    def _log_impression_once(ad_id: str, placement: str, content_url: str = "", content_category: str = "") -> None:
        key = f"{ad_id}|{placement}|{content_url}|{content_category}"
        seen = st.session_state.get("ad_impressions", set())
        if key in seen:
            return
        try:
            log_event(
                APP_DIR,
                event="impression",
                ad_id=ad_id,
                placement=placement,
                content_url=content_url,
                content_category=content_category,
                persona=persona,
                query=search_q,
            )
        except Exception:
            pass
        seen.add(key)
        st.session_state["ad_impressions"] = seen

    def render_ad(ad: Ad, placement: str, content_url: str = "", content_category: str = "") -> None:
        if (not show_ads) or (ad is None):
            return
        _log_impression_once(ad.id, placement, content_url, content_category)
        # Dopamine-ish native sponsored card (still clearly labeled as ad)
        cat = (ad.categories[0] if (ad.categories or []) else "전체")
        emoji = emoji_for_category(cat)

        # thumbnail style: image_url if provided, otherwise gradient
        thumb_style = ""
        if getattr(ad, "image_url", ""):
            safe_url = html.escape(str(ad.image_url))
            thumb_style = f"background-image:url('{safe_url}'); background-size:cover; background-position:center;"
        else:
            thumb_style = gradient_for_seed(ad.id + "|" + placement)

        hook = (getattr(ad, "hook", "") or "").strip()
        if not hook:
            # fallback: a curiosity-ish line based on top keyword (keeps meaning)
            if (ad.keywords or []):
                hook = f"🔥 지금 뜨는 키워드: {ad.keywords[0]}"
            else:
                hook = "🔥 스폰서 추천"

        chips = []
        chips.append(f"{emoji} {cat}")
        for kw in (ad.keywords or [])[:2]:
            chips.append(f"#{kw}")
        chips_html = chips_to_html(chips, max_items=3)

        st.markdown(
            f"""
<div class="sp-card sp-ad">
  <div class="sp-row">
    <div class="sp-thumb" style="{thumb_style}">{html.escape(emoji)}</div>
    <div class="sp-meta">
      <div>
        <span class="sp-ad-badge">스폰서</span>
        <span class="sp-kicker">{html.escape(ad.brand)} · 광고</span>
      </div>
      <div class="sp-hook">{html.escape(hook)}</div>
      <div class="sp-title">{html.escape(ad.title)}</div>
      <div class="sp-snippet">{html.escape(ad.description or '')}</div>
      <div class="sp-chips">{chips_html}</div>
    </div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

        # CTA (kept as a Streamlit button so we can log clicks)
        c1, c2 = st.columns([1.2, 1])
        with c1:
            if st.button(f"👉 {ad.cta}", key=f"ad_click_{placement}_{ad.id}_{content_url}"):
                try:
                    log_event(
                        APP_DIR,
                        event=("affiliate_click" if str((ad.pricing or {}).get("type", "CPC") or "CPC").upper() in {"CPA", "CPS", "AFFILIATE"} else "click"),
                        ad_id=ad.id,
                        placement=placement,
                        content_url=content_url,
                        content_category=content_category,
                        persona=persona,
                        query=search_q,
                    )
                except Exception:
                    pass
                st.toast("스폰서 클릭이 기록됐어요")
                base_link = (ad.landing_url or "").strip()
                if base_link:
                    sep = "&" if "?" in base_link else "?"
                    tracked_link = (
                        f"{base_link}{sep}"
                        f"utm_source=staypick&utm_medium=native_ad"
                        f"&utm_campaign={quote_plus(ad.id)}"
                        f"&utm_content={quote_plus(placement)}"
                    )
                else:
                    tracked_link = base_link
                st.markdown(f"[🔗 스폰서 링크 열기]({tracked_link or ad.landing_url})")
        with c2:
            st.caption("※ 스폰서/광고")

    with main_col:
        shorts_items = [r for r in df_overall.head(80).to_dict(orient="records") if _is_shorts_item(r)]
        if shorts_items:
            st.subheader("Shorts")
            st.caption("유튜브형 밀도: 한 화면에 더 많은 Shorts를 배치합니다.")
            short_show = int(st.session_state.get("shorts_show_n", 12) or 12)
            short_cols = st.columns(6, gap="small")
            for i, row in enumerate(shorts_items[:short_show], start=1):
                s_url = str(row.get("url", "") or "").strip()
                s_title = str(row.get("title", "") or s_url).strip()
                s_thumb = str(row.get("thumbnail_url", "") or "").strip()
                s_cat = str(row.get("category", "") or "").strip() or "전체"
                s_channel = str(row.get("channel_title", "") or "").strip()
                _log_content_impression_once(s_url, s_cat, "shorts", variant=str(st.session_state.get("rank_variant", "control") or "control"))
                with short_cols[(i - 1) % 6]:
                    if s_thumb:
                        thumb_block = f"<img class='short-thumb-img' src='{html.escape(s_thumb)}' alt='short thumbnail'/>"
                    else:
                        thumb_block = (
                            f"<div class='sp-thumb' style='{gradient_for_seed(s_url)}; width:100%; height:100%; border-radius:0;'>"
                            f"{html.escape(emoji_for_category(s_cat))}</div>"
                        )
                    short_title = (s_title[:52] + "...") if len(s_title) > 52 else s_title
                    short_meta = " · ".join([x for x in [s_channel, _views_text(row.get("visits", 0))] if x]).strip(" ·")
                    st.markdown(
                        f"""
  <div class="short-card">
    <div class="short-thumb-wrap">
      {thumb_block}
    </div>
    <div class="short-info">
      <div class="short-title">{html.escape(short_title)}</div>
      <div class="short-meta">{html.escape(short_meta)}</div>
    </div>
  </div>
""",
                        unsafe_allow_html=True,
                    )
                    sc1, sc2 = st.columns([1.1, 0.9], gap="small")
                    with sc1:
                        if st.button("요약 보기", key=f"short_summary_{abs(hash(s_url)) % 100000}_{i}", use_container_width=True):
                            open_item(s_url, source="shorts")
                    with sc2:
                        if st.button("공유", key=f"short_share_{abs(hash(s_url)) % 100000}_{i}", use_container_width=True):
                            st.code(s_url)
                            st.caption("링크를 복사해서 공유하세요.")
            if len(shorts_items) > short_show:
                if st.button("Shorts 더보기", key="btn_more_shorts"):
                    st.session_state["shorts_show_n"] = short_show + 6
                    st.rerun()

        st.subheader("Longform")
        long_items = [r for r in df_overall.to_dict(orient="records") if not _is_shorts_item(r)]
        long_show = int(st.session_state.get("long_show_n", 9) or 9)
        best = long_items[:long_show]

        if not best:
            st.caption("조건에 맞는 콘텐츠가 없어요. 관심 카테고리를 늘리거나 검색을 지워보세요.")
        else:
            for i, row in enumerate(best, start=1):
                source_title = (row.get("title") or "").strip() or row.get("url")
                url = row.get("url", "")
                cat = row.get("category", "전체")
                content = (row.get("content") or "").strip()
                cache: Dict[str, Dict[str, Any]] = st.session_state.get("summary_cache", {})
                s = get_cached_summary(cache, url)
                display_title = (s.get("localized_title") or s.get("title") or source_title) if s else source_title
                if teaser_mode == "ai" and s:
                    teaser = (s.get("hook") or s.get("one_liner") or "")
                else:
                    teaser = snippet_from_content(content, 140)

                emoji = emoji_for_category(cat)
                thumb_url = str(row.get("thumbnail_url", "") or "").strip()
                if thumb_url:
                    thumb_block = f"<img src='{html.escape(thumb_url)}' alt='thumbnail'/>"
                else:
                    thumb_style = gradient_for_seed(url)
                    thumb_block = f"<div class='sp-thumb' style='{thumb_style}; width:100%; height:100%; border-radius:0;'>{html.escape(emoji)}</div>"
                yt_meta = " · ".join(
                    [
                        str(row.get("channel_title", "") or "").strip(),
                        _relative_time_text(str(row.get("published_at", "") or "")),
                        _views_text(row.get("visits", 0)),
                    ]
                ).strip(" ·")

                _log_content_impression_once(str(url or "").strip(), str(cat or "전체").strip() or "전체", "longform", variant=str(st.session_state.get("rank_variant", "control") or "control"))
                st.markdown(
                    build_yt_row(
                        title=display_title,
                        channel=str(row.get("channel_title", "") or "").strip(),
                        meta=yt_meta,
                        desc=teaser or "눌러서 전문/요약 보기",
                        thumb_html=thumb_block,
                        chip=cat,
                    ),
                    unsafe_allow_html=True,
                )

                if show_metrics:
                    ctr_pct = float(row.get("ctr", 0) or 0) * 100.0
                    skip_pct = float(row.get("skip_rate", 0) or 0) * 100.0
                    dwell_q = float(row.get("avg_dwell_sec_q", 0) or 0)
                    st.caption(
                        f"방문 {float(row.get('visits', 0)):.0f} · 체류 {float(row.get('avg_dwell_min', 0)):.2f}분 · "
                        f"CTR {ctr_pct:.1f}% · Skip {skip_pct:.1f}% · qDwell {dwell_q:.0f}s"
                    )

                c1, c2 = st.columns([1, 1])
                with c1:
                    if st.button("시청", key=f"best_open_{i}"):
                        open_item(url, source="longform")
                with c2:
                    if s and st.button("저장", key=f"best_save_{i}"):
                        add_to_selection(s)
                        st.toast("저장됨(선택 목록)")
            if len(long_items) > long_show:
                if st.button("롱폼 더보기", key="btn_more_long"):
                    st.session_state["long_show_n"] = long_show + 9
                    st.rerun()

        # ---- Sponsored banner (native ad) ----
        if show_ads:
            sponsor_banner = select_ads(
                ads_inv,
                context_categories=ctx_categories,
                context_keywords=ctx_keywords,
                n=1,
                seed=7,
            )
            if sponsor_banner:
                st.subheader(t("sponsor_reco"))
                render_ad(sponsor_banner[0], placement="banner")
                st.caption("※ 스폰서는 광고입니다")

        st.divider()
        st.subheader("카테고리 TOP10")
        cat_cols = st.columns(3, gap="small")
        for ci, selected_cat in enumerate(categories[:6], start=1):
            cat_items = topk_cat_df[topk_cat_df["category"] == selected_cat].copy()
            cat_items = cat_items.sort_values(["portal_score", "engagement_score", "visits", "avg_dwell_sec"], ascending=False).head(10)
            if cat_items.empty:
                continue
            top1 = cat_items.iloc[0].to_dict()
            top1_url = str(top1.get("url", "") or "").strip()
            top1_title = str(top1.get("title", "") or top1_url).strip()
            top1_thumb = str(top1.get("thumbnail_url", "") or "").strip()
            top1_meta = " · ".join(
                [
                    str(top1.get("channel_title", "") or "").strip(),
                    _views_text(top1.get("visits", 0)),
                ]
            ).strip(" ·")
            with cat_cols[(ci - 1) % 3]:
                st.markdown(f"**{emoji_for_category(selected_cat)} {selected_cat}**")
                _log_content_impression_once(top1_url, selected_cat, "cat_top1", variant=str(st.session_state.get("rank_variant", "control") or "control"))
                if top1_thumb:
                    st.markdown(
                        f"""
<div class="cat-top-card">
  <img class="cat-top-thumb" src="{html.escape(top1_thumb)}" alt="cat top thumbnail"/>
  <div class="cat-top-body">
    <div class="rank-badge">TOP 1</div>
    <div class="yt-title">{html.escape(top1_title[:56] + ('...' if len(top1_title) > 56 else ''))}</div>
    <div class="yt-meta">{html.escape(top1_meta)}</div>
  </div>
</div>
""",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption(top1_title)
                if st.button("TOP1 시청", key=f"cat_top1_{selected_cat}_{ci}"):
                    open_item(top1_url, source="cat_top1")
                with st.expander(f"{selected_cat} TOP10 보기", expanded=False):
                    for rank, row in enumerate(cat_items.to_dict(orient="records"), start=1):
                        url = str(row.get("url", "") or "").strip()
                        title_txt = str(row.get("title", "") or url).strip()
                        meta_txt = " · ".join(
                            [
                                str(row.get("channel_title", "") or "").strip(),
                                _views_text(row.get("visits", 0)),
                            ]
                        ).strip(" ·")
                        _log_content_impression_once(url, selected_cat, "cat_top10", variant=str(st.session_state.get("rank_variant", "control") or "control"))
                        b1, b2 = st.columns([4.4, 1.1])
                        with b1:
                            if st.button(f"{rank}. {title_txt[:48]}{'...' if len(title_txt) > 48 else ''}", key=f"cat_top10_open_{selected_cat}_{rank}_{ci}"):
                                open_item(url, source="cat_top10")
                        with b2:
                            st.caption(meta_txt if meta_txt else "-")

    with side_col:
        st.subheader(t("hot"))
        hot = df_overall.head(10).to_dict(orient="records")
        for i, row in enumerate(hot, start=1):
            source_title = (row.get("title") or "").strip() or row.get("url")
            url = row.get("url", "")
            cat_hot = str(row.get("category", "") or "").strip() or "전체"
            cache: Dict[str, Dict[str, Any]] = st.session_state.get("summary_cache", {})
            s = get_cached_summary(cache, url)
            display_title = (s.get("localized_title") or s.get("title") or source_title) if s else source_title
            meta = " · ".join(
                [
                    str(row.get("channel_title", "") or "").strip(),
                    _views_text(row.get("visits", 0)),
                ]
            ).strip(" ·")
            hot_thumb = str(row.get("thumbnail_url", "") or "").strip()
            _log_content_impression_once(str(url or "").strip(), cat_hot, "hot", variant=str(st.session_state.get("rank_variant", "control") or "control"))
            thumb_html = (
                f"<img src='{html.escape(hot_thumb)}' alt='thumb'/>"
                if hot_thumb
                else f"<div class='sp-thumb' style='{gradient_for_seed(str(url or ''))}; width:100%; height:100%; border-radius:0;'>{html.escape(emoji_for_category(cat_hot))}</div>"
            )
            st.markdown(
                f"""
<a href="{html.escape(str(url or ''))}" target="_blank" rel="noopener" style="text-decoration:none;">
  <div class="hot-row">
    <div class="hot-row-thumb">{thumb_html}</div>
    <div class="hot-row-body">
      <div class="hot-title">{i}. {html.escape(display_title)}</div>
      <div class="hot-meta">{html.escape(meta)}</div>
    </div>
  </div>
</a>
""",
                unsafe_allow_html=True,
            )

        st.divider()
        st.subheader(t("keywords"))
        kw = compute_trending_keywords(df_overall.head(50), top_k=12)
        if kw:
            # show as chips
            chips = st.container()
            with chips:
                for w in kw:
                    if st.button(f"#{w}", key=f"kw_{w}"):
                        st.session_state["search_query"] = w
                        st.rerun()
        else:
            st.caption("키워드를 만들 데이터가 부족해요.")

        if show_ads:
            st.divider()
            st.subheader(t("sponsor"))
            sponsor_side = select_ads(
                ads_inv,
                context_categories=ctx_categories,
                context_keywords=ctx_keywords,
                n=2,
                seed=13,
            )
            for ad in sponsor_side:
                render_ad(ad, placement="sidebar")

        st.divider()
        st.subheader(t("saved"))
        selected_list: List[Dict[str, Any]] = st.session_state.get("selected_summaries", [])
        st.caption(f"{len(selected_list)}개 저장됨")
        if selected_list:
            if st.button("만들기 탭으로 이동"):
                st.session_state["_jump_to_make"] = True
                st.rerun()

    # Dialog (detail)
    @st.dialog(t("dialog_title"))
    def item_dialog():
        selected_url = (st.session_state.get("selected_url") or "").strip()
        if not selected_url:
            st.write("선택된 항목이 없습니다.")
            return
        st.session_state["_dlg_next_url"] = ""

        row = get_row_by_url(selected_url) or {"url": selected_url, "title": selected_url, "category": "전체"}
        source_title = (row.get("title") or "").strip() or selected_url
        cat = row.get("category", "전체")

        cache: Dict[str, Dict[str, Any]] = st.session_state.get("summary_cache", {})
        current_lang = current_summary_language()
        current_age = st.session_state.get("age_group", "general")
        cache_key = make_cache_key(selected_url, current_lang, current_age)
        existing = get_cached_summary(cache, selected_url, lang=current_lang, age=current_age)

        display_title = (existing.get("localized_title") or existing.get("title") or source_title) if existing else source_title

        channel = str(row.get("channel_title", "") or "").strip()
        published = _relative_time_text(str(row.get("published_at", "") or ""))
        views = _views_text(row.get("visits", 0))
        meta_bits = " · ".join([x for x in [cat, channel, published, views] if x]).strip(" ·")
        st.markdown(build_article_header(display_title, meta_bits, selected_url), unsafe_allow_html=True)
        if source_title and source_title != display_title:
            st.caption(f"source title: {source_title}")

        generated_map = st.session_state.get("generated_by_url", {}) or {}
        generated_item = generated_map.get(selected_url)
        if isinstance(generated_item, dict) and str(generated_item.get("content", "")).strip():
            st.markdown("**방금 만든 콘텐츠**")
            st.markdown(
                f"""
<div class="yt-generated-box">
  <div class="small-muted">{html.escape(str(generated_item.get("meta", "")))}</div>
</div>
""",
                unsafe_allow_html=True,
            )
            st.markdown(str(generated_item.get("content", "")))
            if st.button("만들기 탭에서 이어서 보기", key=f"dlg_jump_make::{cache_key}"):
                st.session_state["_jump_to_make"] = True
                st.rerun()

        content_from_csv = (row.get("content", "") or "").strip()
        content_desc = (row.get("description", "") or "").strip()

        def _get_full_text() -> str:
            cache_ft = st.session_state.get("fulltext_cache", {})
            if isinstance(cache_ft, dict) and selected_url in cache_ft:
                return str(cache_ft.get(selected_url) or "")
            text = content_from_csv or content_desc
            if (not text) and (not _is_youtube_url(selected_url)):
                try:
                    is_http = bool(re.match(r"^https?://", selected_url, flags=re.I))
                    if is_http:
                        _, fetched_text = cached_fetch(selected_url)
                        text = (fetched_text or "").strip()
                except Exception:
                    text = ""
            if isinstance(cache_ft, dict):
                cache_ft[selected_url] = text
                st.session_state["fulltext_cache"] = cache_ft
            return text


        # (cache/existing already loaded above)

        def _render_summary(s: Dict[str, Any]) -> None:
            """Consumer-friendly detail view: hook first, then 3-sec summary."""
            hook = (s.get("hook") or "").strip()
            if hook:
                st.markdown(f"**{t('label_hook')}**")
                st.info(hook)

            st.markdown("**3초 요약**")
            st.write((s.get("one_liner") or "").strip())

            kps = (s.get("key_points") or [])
            if kps:
                st.markdown("**핵심 포인트**")
                st.write("\n".join([f"- {x}" for x in kps[:5]]))

            # Full summary (optional)
            full = (s.get("summary") or "").strip()
            if full:
                with st.expander("자세히(요약)", expanded=False):
                    st.write(full)

            tags = (s.get("tags") or [])
            if tags:
                st.markdown("**태그**")
                st.write(", ".join(tags))

        def _render_summary_v2(s: Dict[str, Any]) -> None:
            hook = (s.get("hook") or "").strip().replace("?", "").replace("?", "")
            if hook:
                st.markdown("**Hook**")
                st.info(hook)

            st.markdown("**3-second summary**")
            st.write((s.get("one_liner") or "").strip())

            kps = [str(x).strip() for x in (s.get("key_points") or []) if str(x).strip()][:3]
            if kps:
                st.markdown("**Key points**")
                st.write("\\n".join([f"- {x}" for x in kps]))

            why = (s.get("why_trending") or "").strip()
            if not why:
                visits_v = float(row.get("visits", 0) or 0)
                dwell_s = float(row.get("avg_dwell_sec", 0) or 0)
                score_v = row.get("engagement_score", None)
                recency = _relative_time_text(str(row.get("published_at", "") or ""))
                comments_v = float(row.get("comment_count", 0) or 0)
                if visits_v <= 0 and dwell_s <= 0 and score_v is None:
                    why = "Core metrics are limited, so this item is treated as generally relevant without over-claiming."
                else:
                    why = (
                        f"Published {recency or 'recently'} with {_views_text(visits_v)} and comment activity ({comments_v:.0f}) shows active response. "
                        f"Engagement score {float(score_v or 0):.3f} and dwell proxy {dwell_s:.1f}s suggest sustained interest."
                    )
            st.markdown("**Why trending**")
            st.write(why)

            discussion = (s.get("discussion_prompt") or "").strip()
            if not discussion:
                discussion = "???? ???? ? ?? ??? ? ??? ?????"
            st.markdown("**Discussion prompt**")
            st.write(discussion)

        def _render_recommendations() -> None:
            rec_base = df_scored.copy()
            rec_base["reco_boost"] = _reco_click_boost(rec_base)
            reco_base_w = float(st.session_state.get("reco_base_w", 0.9) or 0.9)
            reco_click_w = float(st.session_state.get("reco_click_w", 0.1) or 0.1)
            rec_base["reco_rank"] = (
                pd.to_numeric(rec_base.get("portal_score", 0), errors="coerce").fillna(0.0) * reco_base_w
                + rec_base["reco_boost"] * reco_click_w
            )
            rec_base = rec_base.sort_values(
                ["reco_rank", "portal_score", "engagement_score", "visits"],
                ascending=False,
            )
            hidden_urls = set(st.session_state.get("hidden_urls", []) or [])
            if hidden_urls:
                rec_base = rec_base[~rec_base["url"].isin(list(hidden_urls))]
            rec_base = rec_base[rec_base["url"] != selected_url].drop_duplicates(subset=["url"], keep="first")

            same_cat = rec_base[rec_base["category"] == cat]
            others = rec_base[rec_base["category"] != cat]
            people_df = pd.concat([same_cat, others], ignore_index=True).head(5)

            st.markdown("**People also viewed**")
            if not people_df.empty:
                for i, rec in enumerate(people_df.to_dict(orient="records"), start=1):
                    rec_url = rec.get("url", "")
                    rec_title = (rec.get("title") or rec_url).strip()
                    c_also_1, c_also_2 = st.columns([5, 2])
                    with c_also_1:
                        clicked_open = st.button(f"{i}. {rec_title}", key=f"also_{selected_url}_{i}")
                    with c_also_2:
                        clicked_hide = st.button("Not interested", key=f"ni_also_{selected_url}_{i}")
                    if clicked_hide and rec_url:
                        mark_not_interested(rec_url, rec_title)
                        st.rerun()
                    if clicked_open:
                        rec_cat = str(rec.get("category", "") or "").strip()
                        ccounts = st.session_state.get("clicked_category_counts", {})
                        if not isinstance(ccounts, dict):
                            ccounts = {}
                        if rec_cat:
                            ccounts[rec_cat] = int(ccounts.get(rec_cat, 0) or 0) + 1
                            st.session_state["clicked_category_counts"] = ccounts
                        _log_reco_click(rec_url)
                        _log_reco_event(selected_url, rec_url, "people_also_viewed", rec_cat)
                        open_item(rec_url, source="people_also_viewed")
            else:
                st.caption("?? ??? ????.")

            interest_set = set(st.session_state.get("interest_cats", []) or [])
            focus_set = set(interest_set)
            focus_set.add(cat)
            top_interest = rec_base[rec_base["category"].isin(focus_set)] if focus_set else rec_base
            top_interest = top_interest.head(50)
            next_top = top_interest.head(4)
            rand_pool = rec_base.head(20)
            used = set(next_top["url"].tolist()) if not next_top.empty else set()
            rand_pool = rand_pool[~rand_pool["url"].isin(used)]
            rand_pick = rand_pool.sample(n=1, random_state=(abs(hash(cache_key)) % 100000)) if len(rand_pool) > 0 else rand_pool
            next_df = pd.concat([next_top, rand_pick], ignore_index=True).drop_duplicates(subset=["url"], keep="first")
            if len(next_df) < 5:
                extra = rec_base[~rec_base["url"].isin(next_df["url"].tolist())].head(5 - len(next_df))
                next_df = pd.concat([next_df, extra], ignore_index=True)
            next_df = next_df.head(5)

            st.markdown("**Next up**")
            if not next_df.empty:
                next_first = next_df.iloc[0].to_dict()
                next_first_url = str(next_first.get("url", "") or "").strip()
                next_first_title = str(next_first.get("title", "") or next_first_url).strip()
                st.session_state["_dlg_next_url"] = next_first_url
                if next_first_url:
                    if st.button(f"▶ Play next: {next_first_title[:42]}", key=f"play_next_{selected_url}", type="primary"):
                        rec_cat = str(next_first.get("category", "") or "").strip()
                        ccounts = st.session_state.get("clicked_category_counts", {})
                        if not isinstance(ccounts, dict):
                            ccounts = {}
                        if rec_cat:
                            ccounts[rec_cat] = int(ccounts.get(rec_cat, 0) or 0) + 1
                            st.session_state["clicked_category_counts"] = ccounts
                        _log_reco_click(next_first_url)
                        _log_reco_event(selected_url, next_first_url, "play_next", rec_cat)
                        open_item(next_first_url, source="play_next")
                for i, rec in enumerate(next_df.to_dict(orient="records"), start=1):
                    rec_url = rec.get("url", "")
                    rec_title = (rec.get("title") or rec_url).strip()
                    c_next_1, c_next_2 = st.columns([5, 2])
                    with c_next_1:
                        clicked_open = st.button(f"{i}. {rec_title}", key=f"next_{selected_url}_{i}")
                    with c_next_2:
                        clicked_hide = st.button("Not interested", key=f"ni_next_{selected_url}_{i}")
                    if clicked_hide and rec_url:
                        mark_not_interested(rec_url, rec_title)
                        st.rerun()
                    if clicked_open:
                        rec_cat = str(rec.get("category", "") or "").strip()
                        ccounts = st.session_state.get("clicked_category_counts", {})
                        if not isinstance(ccounts, dict):
                            ccounts = {}
                        if rec_cat:
                            ccounts[rec_cat] = int(ccounts.get(rec_cat, 0) or 0) + 1
                            st.session_state["clicked_category_counts"] = ccounts
                        _log_reco_click(rec_url)
                        _log_reco_event(selected_url, rec_url, "next_up", rec_cat)
                        open_item(rec_url, source="next_up")
            else:
                st.caption("?? ??? ????.")

        def _build_summary() -> Optional[Dict[str, Any]]:
            """Fetch content (if needed) and build a summary. Returns summary dict or None."""
            if not consume_ai_credit():
                st.warning("Daily AI credit limit reached for current plan.")
                return None
            try:
                ai = ensure_ai()
            except Exception as e:
                st.error(str(e))
                return None

            metrics = {
                "visits": float(row.get("visits", 0)),
                "avg_dwell_sec": float(row.get("avg_dwell_sec", 0)),
                "engagement_score": float(row.get("engagement_score", 0)),
                "comment_count": float(row.get("comment_count", 0) or 0),
                "published_at": str(row.get("published_at", "") or ""),
            }
            # Prefer CSV content; otherwise fetch. If fetch fails, fall back to title/snippet.
            with st.spinner("원문 준비 중..."):
                page_title = source_title or selected_url
                text = content_from_csv or content_desc
                if not text:
                    try:
                        # Skip fetch for non-http URLs and YouTube watch pages (use description/title fallback).
                        is_http = bool(re.match(r"^https?://", selected_url, flags=re.I))
                        is_yt = ("youtube.com/watch" in selected_url.lower()) or ("youtu.be/" in selected_url.lower())
                        if is_http and (not is_yt):
                            fetched_title, fetched_text = cached_fetch(selected_url)
                            page_title = (fetched_title or page_title).strip()
                            text = (fetched_text or "").strip()
                    except Exception as e:
                        st.warning(f"원문을 가져오지 못해 제목/미리보기로 요약합니다. ({e})")
                        text = text or page_title

                # Final fallback
                if not text:
                    text = page_title

            with st.spinner("3초 요약 생성 중..."):
                try:
                    summary = ai.summarize(
                        url=selected_url,
                        title=page_title,
                        content=text,
                        metrics=metrics,
                        # Use output language (Auto => UI language)
                        language=st.session_state.get("content_lang") or st.session_state.get("ui_lang", "ko"),
                        age_group=st.session_state.get("age_group", "general"),
                    )
                    return summary
                except Exception as e:
                    st.error(f"요약 실패: {e}")
                    return None

        api_ready = bool(api_key)
        tab_full, tab_summary, tab_reco = st.tabs(["전문", "요약", "추천"])

        with tab_full:
            if _is_youtube_url(selected_url):
                st.video(selected_url)
            else:
                thumb_url = str(row.get("thumbnail_url", "") or "").strip()
                if thumb_url:
                    st.image(thumb_url, use_container_width=True)
            channel_title = str(row.get("channel_title", "") or "").strip()
            chan_initial = (channel_title[:1] or "C").upper()
            views = _views_text(row.get("visits", 0))
            comments = float(row.get("comment_count", 0) or 0)
            likes = float(row.get("like_count", 0) or 0)
            st.markdown(
                f"""
<div class="yt-detail-card">
  <div class="yt-channel-row">
    <div class="yt-avatar">{html.escape(chan_initial)}</div>
    <div>
      <div><strong>{html.escape(channel_title or 'Channel')}</strong></div>
      <div class="article-meta">{html.escape(views)} · 댓글 {int(comments):,} · 좋아요 {int(likes):,}</div>
    </div>
  </div>
  <div class="yt-actions">
    <span class="yt-action-btn">👍 좋아요</span>
    <span class="yt-action-btn">➕ 구독</span>
    <span class="yt-action-btn">공유</span>
    <span class="yt-action-btn">저장</span>
  </div>
</div>
""",
                unsafe_allow_html=True,
            )
            full_text = _get_full_text()
            if full_text:
                body_html, toc = paragraphize_fulltext(full_text)
                if toc:
                    st.markdown(build_toc(toc[:8]), unsafe_allow_html=True)
                with st.expander("설명 보기", expanded=False):
                    st.markdown(f"<div class='article-body'>{body_html}</div>", unsafe_allow_html=True)
            else:
                st.info("전문을 불러오지 못했습니다. 요약 탭에서 AI 요약을 확인하세요.")

        with tab_summary:
            if existing:
                st.success("요약이 이미 준비돼 있어요.")
                _render_summary_v2(existing)
            else:
                if not api_ready:
                    st.info("OPENAI_API_KEY가 없어 요약을 만들 수 없습니다.")
                    fallback_base = content_from_csv or source_title
                    fallback = {
                        "url": selected_url,
                        "title": source_title,
                        "localized_title": source_title,
                        "hook": snippet_from_content(fallback_base, 80).replace("?", "."),
                        "one_liner": snippet_from_content(fallback_base, 120),
                        "key_points": [
                            snippet_from_content(fallback_base, 70),
                            "핵심 포인트를 요약해 보여줍니다.",
                            "필요하면 요약을 생성해 주세요.",
                        ],
                        "why_trending": "",
                        "discussion_prompt": "A와 B 중 뭐가 더 설득력 있나요?",
                        "summary": snippet_from_content(fallback_base, 240),
                        "tags": [],
                        "sources": [selected_url],
                    }
                    _render_summary_v2(fallback)

                did_flag = f"_auto_summary_done::{cache_key}"
                if auto_summarize and api_ready and not st.session_state.get(did_flag, False):
                    st.session_state[did_flag] = True
                    summary = _build_summary()
                    if summary is None:
                        st.session_state[did_flag] = False
                    else:
                        set_cached_summary(cache, selected_url, summary, lang=current_lang, age=current_age)
                        st.session_state["summary_cache"] = cache
                        st.rerun()

                st.warning("요약이 아직 없습니다. 생성 버튼을 눌러주세요.")
                if st.button("3초 요약 생성", type="primary", disabled=not api_ready, key=f"dlg_make_summary::{cache_key}"):
                    st.session_state[did_flag] = True
                    summary = _build_summary()
                    if summary:
                        set_cached_summary(cache, selected_url, summary, lang=current_lang, age=current_age)
                        st.session_state["summary_cache"] = cache
                        st.success("요약 생성 완료")
                        st.rerun()

        with tab_reco:
            _render_recommendations()

        # 9) Actions area
        cache = st.session_state.get("summary_cache", {})
        s = get_cached_summary(cache, selected_url, lang=current_lang, age=current_age)
        if s:
            st.markdown("**Actions**")
            a1, a2, a3, a4 = st.columns([1.1, 1, 1, 0.8])
            with a1:
                if st.button("Save", key=f"dlg_save::{cache_key}", type="primary"):
                    add_to_selection(s)
                    st.success("Saved.")
            with a2:
                if st.button("Copy link", key=f"dlg_copy::{cache_key}"):
                    st.code(selected_url)
                    st.caption("Link ready to copy.")
            with a3:
                st.markdown(f"[Open source]({selected_url})")
            with a4:
                if st.button("Close", key=f"dlg_close::{cache_key}"):
                    next_url = str(st.session_state.get("_dlg_next_url", "") or "").strip()
                    if st.session_state.get("autoplay_next", True) and next_url and next_url != selected_url:
                        delay_sec = int(st.session_state.get("autoplay_delay_sec", 3) or 3)
                        st.info(f"Playing next in {delay_sec} seconds...")
                        time.sleep(delay_sec)
                        _finalize_current_view("autoplay_close")
                        open_item(next_url, source="autoplay")
                    else:
                        _finalize_current_view("close")
                        st.session_state["open_dialog"] = False
                        st.rerun()

            st.divider()
            st.markdown("### ✍️ 이 글로 새 콘텐츠 만들기")
            # quick overrides inside dialog
            age_group_local = st.selectbox(
                t("age_group"),
                options=["general", "elem", "mid", "high", "uni", "20s", "30s"],
                format_func=lambda x: {
                    "general": t("age_general"),
                    "elem": t("age_elem"),
                    "mid": t("age_mid"),
                    "high": t("age_high"),
                    "uni": t("age_uni"),
                    "20s": t("age_20s"),
                    "30s": t("age_30s"),
                }.get(x, x),
                index=["general", "elem", "mid", "high", "uni", "20s", "30s"].index(st.session_state.get("age_group", "general")),
                key="age_group_local",
            )

            persona_local = st.selectbox(
                "독자 타입(이 창에서만)",
                options=[
                    "일반 유저(입문자)",
                    "직장인(가볍게 읽기)",
                    "스타트업 마케터",
                    "PM/PO",
                    "개발자/데이터",
                ],
                index=[
                    "일반 유저(입문자)",
                    "직장인(가볍게 읽기)",
                    "스타트업 마케터",
                    "PM/PO",
                    "개발자/데이터",
                ].index(persona),
            )
            format_local = st.selectbox(
                "결과물(이 창에서만)",
                options=[
                    "친구에게 보내는 추천글(짧게)",
                    "3줄 요약(초간단)",
                    "블로그 포스트(1200~1600자)",
                    "X(트위터) 스레드(8~10개)",
                    "숏폼 영상 대본(60초)",
                ],
                index=[
                    "친구에게 보내는 추천글(짧게)",
                    "3줄 요약(초간단)",
                    "블로그 포스트(1200~1600자)",
                    "X(트위터) 스레드(8~10개)",
                    "숏폼 영상 대본(60초)",
                ].index(output_format),
            )
            tone_local = st.text_area("톤/추가 지시(선택)", value=brand_tone, height=70)

            if st.button(t("btn_make"), type="primary", key="dlg_gen"):
                if not consume_ai_credit():
                    st.warning("Daily AI credit limit reached for current plan.")
                    return
                try:
                    ai = ensure_ai()
                except Exception as e:
                    st.error(str(e))
                    return

                with st.spinner("새 콘텐츠 생성 중..."):
                    try:
                        output_md = ai.generate_content(
                            summaries=[s],
                            persona=persona_local,
                            output_format=format_local,
                            additional_context=tone_local,
                            external_trends="",
                            language=st.session_state.get("content_lang") or st.session_state.get("ui_lang", "ko"),
                            age_group=age_group_local,
                        )
                    except Exception as e:
                        st.error(str(e))
                        return

                st.markdown("#### 결과")
                st.markdown(output_md)
                generated_map = st.session_state.get("generated_by_url", {})
                if not isinstance(generated_map, dict):
                    generated_map = {}
                generated_map[selected_url] = {
                    "content": output_md,
                    "meta": f"{datetime.now().strftime('%Y-%m-%d %H:%M')} · {persona_local} · {format_local}",
                }
                st.session_state["generated_by_url"] = generated_map
                st.session_state["last_generated_content"] = {
                    "url": selected_url,
                    "title": display_title,
                    "content": output_md,
                    "meta": generated_map[selected_url]["meta"],
                }
                gen_hist = st.session_state.get("generated_history", [])
                if not isinstance(gen_hist, list):
                    gen_hist = []
                gen_hist.append(
                    {
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "title": display_title,
                        "url": selected_url,
                        "format": format_local,
                        "persona": persona_local,
                        "content": output_md,
                    }
                )
                st.session_state["generated_history"] = gen_hist[-200:]
                st.success("생성 결과를 바로 저장했습니다.")
                st.download_button(
                    "Markdown 다운로드",
                    data=output_md,
                    file_name=f"staypick_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                    mime="text/markdown",
                )

    if st.session_state.get("open_dialog"):
        item_dialog()


# ---------------------------
# Guide tab
# ---------------------------
with tab_guide:
    st.subheader("🚀 StayPick 활용법")
    st.caption("유튜브처럼 계속 보게 만들고, 바로 내 콘텐츠로 전환하는 가장 빠른 루트")

    st.markdown("### 1) 10초 온보딩")
    st.markdown(
        """
- 상단 카테고리 박스를 눌러 관심 주제를 고릅니다.
- `Shorts`에서 가볍게 훑고, `Longform`에서 깊게 봅니다.
- 오른쪽 `HOT 랭킹`과 `인기검색`으로 지금 뜨는 흐름을 빠르게 잡습니다.
"""
    )

    st.markdown("### 2) 도파민 루프(계속 클릭하게 만드는 루틴)")
    st.markdown(
        """
- 먼저 `Shorts` 3개만 연속 시청해서 감을 잡습니다.
- 마음에 드는 1개를 눌러 상세 모달로 들어갑니다.
- 모달의 `사람들이 같이 본 글`과 `다음 추천`을 타고 3~5개 연속 이동합니다.
- 좋아 보이는 건 `저장`해서 만들기 탭으로 넘깁니다.
"""
    )

    st.markdown("### 3) 상세 모달 100% 활용")
    st.markdown(
        """
- `3초 요약`으로 핵심 파악
- `핵심 3개`로 메시지 추출
- `왜 뜨는가`로 조회/체류/반응 근거 확인
- `논쟁 포인트`로 댓글/커뮤니티 반응 포인트 확보
"""
    )

    st.markdown("### 4) 바로 재가공(만들기 탭)")
    st.markdown(
        """
- 피드에서 저장한 항목을 묶어 한 번에 새 글/스크립트 생성
- 독자 타입(입문자/직장인/마케터)과 출력 포맷을 바꿔 여러 버전 실험
- 방금 만든 결과를 다시 피드 아이템과 연결해 반복 개선
"""
    )

    st.markdown("### 5) 해커톤 데모용 3분 시나리오")
    st.markdown(
        """
1. 카테고리 1개 선택 후 Shorts 2개 시청
2. Longform TOP1 클릭 → 요약 확인
3. 저장 후 만들기 탭에서 결과 생성
4. 생성 결과를 즉시 공유(복사/다운로드)
"""
    )

    st.info("팁: 검색창에 키워드 1개만 넣어도 피드가 즉시 재정렬됩니다. `짧게 훑기 → 깊게 보기 → 바로 만들기` 순서가 가장 전환율이 높습니다.")


# ---------------------------
# Make tab (batch generate from saved list)
# ---------------------------
with tab_make:
    st.subheader("✍️ 저장한 목록으로 콘텐츠 만들기")
    selected_list: List[Dict[str, Any]] = st.session_state.get("selected_summaries", [])
    sub_make = subscription_snapshot()
    make_limit = 100 if sub_make["premium"] else 5
    selected_for_make = selected_list[:make_limit]
    if len(selected_list) > make_limit:
        st.warning(f"Current plan allows up to {make_limit} saved items for batch generation.")
    st.caption("피드에서 마음에 드는 글을 **저장**하면, 여기서 묶어서 만들 수 있어요.")
    last_generated = st.session_state.get("last_generated_content", {}) or {}
    if isinstance(last_generated, dict) and str(last_generated.get("content", "")).strip():
        with st.expander("최근 생성 결과", expanded=True):
            st.caption(str(last_generated.get("meta", "")))
            if last_generated.get("title"):
                st.markdown(f"**{last_generated.get('title')}**")
            st.markdown(str(last_generated.get("content", "")))

    if not selected_list:
        st.info("아직 저장한 항목이 없습니다. 피드에서 '저장'을 눌러보세요.")
    else:
        for i, s in enumerate(selected_list, start=1):
            with st.expander(f"{i}. {s.get('title','(no title)')}", expanded=False):
                st.write(f"URL: {s.get('url')}")
                st.write(f"한줄: {s.get('one_liner')}")
                st.write("태그: " + ", ".join(s.get("tags") or []))

        st.divider()
        st.markdown("### 만들기 옵션")
        age_group2 = st.selectbox(
            t("age_group"),
            options=["general", "elem", "mid", "high", "uni", "20s", "30s"],
            format_func=lambda x: {
                "general": t("age_general"),
                "elem": t("age_elem"),
                "mid": t("age_mid"),
                "high": t("age_high"),
                "uni": t("age_uni"),
                "20s": t("age_20s"),
                "30s": t("age_30s"),
            }.get(x, x),
            index=["general", "elem", "mid", "high", "uni", "20s", "30s"].index(st.session_state.get("age_group", "general")),
            key="age_group_make",
        )

        persona2 = st.selectbox("독자 타입", options=[
            "일반 유저(입문자)",
            "직장인(가볍게 읽기)",
            "스타트업 마케터",
            "PM/PO",
            "개발자/데이터",
        ], index=0)
        format2 = st.selectbox("결과물", options=[
            "뉴스레터(5분 읽기)",
            "블로그 포스트(1500~2000자)",
            "X(트위터) 스레드(10개 트윗)",
            "숏폼 영상 대본(60초)",
            "카루셀/슬라이드 스크립트(8장)",
        ], index=0)
        tone2 = st.text_area("톤/추가 지시(선택)", placeholder="예: 훅 강하게, 불릿 많게, 마지막에 CTA", height=90)

        if st.button("저장 목록으로 새 콘텐츠 생성", type="primary"):
            if not consume_ai_credit():
                st.warning("Daily AI credit limit reached for current plan.")
                st.stop()
            try:
                ai = ensure_ai()
            except Exception as e:
                st.error(str(e))
                st.stop()

            with st.spinner("새 콘텐츠 생성 중..."):
                try:
                    output_md = ai.generate_content(
                        summaries=selected_for_make,
                        persona=persona2,
                        output_format=format2,
                        additional_context=tone2,
                        external_trends="",
                        language=st.session_state.get("content_lang") or st.session_state.get("ui_lang", "ko"),
                        age_group=age_group2,
                    )
                except Exception as e:
                    st.error(str(e))
                    st.stop()

            st.markdown("### 결과")
            st.markdown(output_md)
            gen_hist = st.session_state.get("generated_history", [])
            if not isinstance(gen_hist, list):
                gen_hist = []
            lead_title = str((selected_for_make[0] or {}).get("localized_title") or (selected_for_make[0] or {}).get("title") or "저장 목록 결과")
            gen_hist.append(
                {
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "title": f"{lead_title} 외 {max(len(selected_for_make)-1, 0)}개",
                    "url": "",
                    "format": format2,
                    "persona": persona2,
                    "content": output_md,
                }
            )
            st.session_state["generated_history"] = gen_hist[-200:]
            st.session_state["last_generated_content"] = {
                "url": "",
                "title": lead_title,
                "content": output_md,
                "meta": f"{datetime.now().strftime('%Y-%m-%d %H:%M')} · {persona2} · {format2}",
            }
            st.download_button(
                "Markdown 다운로드",
                data=output_md,
                file_name=f"staypick_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                mime="text/markdown",
            )


# ---------------------------
# My Page tab
# ---------------------------
with tab_mypage:
    st.subheader("👤 마이페이지")
    st.caption("내가 만든 콘텐츠 기록")
    gen_hist = st.session_state.get("generated_history", [])
    if not isinstance(gen_hist, list) or not gen_hist:
        st.info("아직 만든 콘텐츠가 없습니다. 피드 상세에서 만들거나, 만들기 탭에서 생성해보세요.")
    else:
        st.caption(f"총 {len(gen_hist)}개")
        c_m1, c_m2 = st.columns([1, 1])
        with c_m1:
            if st.button("최근순 정렬", key="mypage_sort_recent"):
                st.session_state["_mypage_sort"] = "recent"
        with c_m2:
            if st.button("기록 비우기", key="mypage_clear_history"):
                st.session_state["generated_history"] = []
                st.session_state["last_generated_content"] = {}
                st.rerun()
        items = list(gen_hist)
        items = list(reversed(items))
        for i, it in enumerate(items, start=1):
            created_at = str(it.get("created_at", "") or "")
            title_txt = str(it.get("title", "") or f"콘텐츠 {i}")
            format_txt = str(it.get("format", "") or "")
            persona_txt = str(it.get("persona", "") or "")
            url_txt = str(it.get("url", "") or "")
            content_txt = str(it.get("content", "") or "")
            with st.expander(f"{i}. {title_txt}", expanded=(i == 1)):
                st.caption(f"{created_at} · {persona_txt} · {format_txt}")
                if url_txt:
                    st.markdown(f"[원문 보기]({url_txt})")
                st.markdown(content_txt)
                st.download_button(
                    "Markdown 다운로드",
                    data=content_txt,
                    file_name=f"staypick_mypage_{i}_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                    mime="text/markdown",
                    key=f"mypage_dl_{i}",
                )


# ---------------------------
# Landing tab
# ---------------------------
with tab_landing:
    st.subheader("🧾 랜딩페이지")
    st.caption("서비스/요금/수익모델 원페이지")
    landing_html = _load_landing_html()
    if not landing_html:
        st.warning("랜딩 HTML 파일을 찾지 못했습니다.")
        st.code(LANDING_PAGE_PATH)
    else:
        c_l1, c_l2 = st.columns([1, 1])
        with c_l1:
            st.download_button(
                "Landing HTML 다운로드",
                data=landing_html.encode("utf-8"),
                file_name="StayPick_Landing.html",
                mime="text/html",
            )
        with c_l2:
            preview_on = st.toggle("앱 내 미리보기", value=True, key="landing_preview_on")
        if preview_on:
            components.html(landing_html, height=980, scrolling=True)


# ---------------------------
# Admin: Data tab
# ---------------------------
if admin_mode and tab_data is not None:
    with tab_data:
        st.subheader("📥 데이터 넣기(운영자)")
        st.markdown(
            """
일반 유저에게는 데이터 입력을 숨기고, 운영자가 아래 방식으로 데이터 소스를 유지하는 구조가 가장 좋아요.

- **CSV 업로드**(GA4/Amplitude export) — 자동 컬럼 인식  
- **URL 리스트**(초간단) — 데모/테스트용  
- (차후) Analytics API 연동 — 자동 수집
"""
        )

        col1, col2 = st.columns([1, 1], gap="large")
        with col1:
            st.markdown("#### 1) CSV 업로드")
            uploaded = st.file_uploader("CSV 파일", type=["csv"], key="uploader_csv")
            if uploaded is not None:
                try:
                    df = load_metrics_csv(uploaded)
                    st.session_state["df_raw"] = df
                    st.session_state["data_source"] = "upload"
                    refresh_scores()
                    st.success(f"업로드 완료! {len(df)}개 행을 읽었습니다.")
                except Exception as e:
                    st.error(str(e))

            st.caption("최소 컬럼: url (visits/avg_dwell_sec가 없으면 기본값으로 채웁니다). title/content/category는 선택.")

            if st.button("데모 데이터로 되돌리기"):
                st.session_state["df_raw"] = load_demo_df()
                st.session_state["data_source"] = "demo"
                refresh_scores()
                st.success("데모 데이터로 복원했습니다.")

        with col2:
            st.markdown("#### 2) URL 리스트로 시작(초간단)")
            urls_text = st.text_area("URL을 한 줄에 하나씩", height=180)
            if st.button("URL 리스트 불러오기"):
                urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
                if not urls:
                    st.warning("URL을 1개 이상 입력하세요.")
                else:
                    df = pd.DataFrame(
                        {
                            "url": urls,
                            "title": ["" for _ in urls],
                            "visits": [1.0 for _ in urls],
                            "avg_dwell_sec": [60.0 for _ in urls],
                            "content": ["" for _ in urls],
                            "category": ["" for _ in urls],
                        }
                    )
                    st.session_state["df_raw"] = df
                    st.session_state["data_source"] = "urls"
                    refresh_scores()
                    st.success(f"URL {len(urls)}개 로드 완료!")

        st.divider()
        df_scored = st.session_state.get("df_scored", pd.DataFrame())
        st.markdown("#### 현재 데이터 미리보기")
        if df_scored.empty:
            st.warning("데이터가 없습니다.")
        else:
            st.caption(f"데이터 소스: **{st.session_state.get('data_source')}** · rows: {len(df_scored)}")
            st.dataframe(
                df_scored[["category", "title", "url", "visits", "avg_dwell_sec", "avg_dwell_min", "engagement_score"]].head(50),
                use_container_width=True,
            )


# ---------------------------
# Admin: Insights tab (bulk summarize + cluster)
# ---------------------------
if admin_mode and tab_insights is not None:
    with tab_insights:
        st.subheader("🔎 Top 콘텐츠 요약 & 트렌드 클러스터(운영자)")

        top_df = st.session_state.get("top_df", pd.DataFrame())
        if top_df.empty:
            st.warning("데이터가 없습니다. 데이터 탭에서 먼저 넣어주세요.")
            st.stop()

        st.write("스코어 기준 Top 콘텐츠:")
        st.dataframe(top_df[["category", "title", "url", "visits", "avg_dwell_min", "engagement_score"]], use_container_width=True)

        if st.button("Top 콘텐츠 일괄 요약 생성", type="primary"):
            try:
                ai = ensure_ai()
            except Exception as e:
                st.error(str(e))
                st.stop()

            summaries: List[Dict[str, Any]] = []
            cache: Dict[str, Dict[str, Any]] = st.session_state.get("summary_cache", {})

            progress = st.progress(0, text="시작...")
            rows = top_df.to_dict(orient="records")
            for i, row in enumerate(rows, start=1):
                url = row["url"]
                title_hint = row.get("title", "") or url
                metrics = {
                    "visits": float(row.get("visits", 0)),
                    "avg_dwell_sec": float(row.get("avg_dwell_sec", 0)),
                    "engagement_score": float(row.get("engagement_score", 0)),
                    "comment_count": float(row.get("comment_count", 0) or 0),
                    "published_at": str(row.get("published_at", "") or ""),
                }
                content_from_csv = (row.get("content", "") or "").strip()

                cached = get_cached_summary(
                    cache,
                    url,
                    lang=current_summary_language(),
                    age=st.session_state.get("age_group", "general"),
                )
                if cached:
                    summaries.append(cached)
                    progress.progress(i / len(rows), text="진행 중...")
                    continue

                with st.spinner(f"[{i}/{len(rows)}] 원문 가져오는 중..."):
                    try:
                        if content_from_csv:
                            page_title, text = title_hint, content_from_csv
                        else:
                            fetched_title, text = cached_fetch(url)
                            page_title = fetched_title or title_hint
                    except Exception as e:
                        st.warning(f"가져오기 실패: {url} · {e}")
                        progress.progress(i / len(rows), text="진행 중...")
                        continue

                with st.spinner("요약 생성 중..."):
                    try:
                        summary = ai.summarize(
                            url=url,
                            title=page_title,
                            content=text,
                            metrics=metrics,
                            language=current_summary_language(),
                            age_group=st.session_state.get("age_group", "general"),
                        )
                        set_cached_summary(
                            cache,
                            url,
                            summary,
                            lang=current_summary_language(),
                            age=st.session_state.get("age_group", "general"),
                        )
                        summaries.append(summary)
                    except Exception as e:
                        st.warning(f"요약 실패: {url} · {e}")

                progress.progress(i / len(rows), text="진행 중...")

            progress.empty()
            st.session_state["summary_cache"] = cache
            st.session_state["summaries"] = summaries

            if summaries:
                try:
                    vectors = ai.embed_texts([s.get("summary", "") for s in summaries])
                    clusters = cluster_summaries(vectors, summaries, max_clusters=3)
                    st.session_state["clusters"] = clusters
                except Exception as e:
                    st.warning(f"클러스터링 실패(무시 가능): {e}")

                st.success(f"완료! 요약 {len(summaries)}개 생성.")
            else:
                st.error("요약 결과가 없습니다. URL 접근/키/모델을 확인해주세요.")

        clusters = st.session_state.get("clusters", [])
        if clusters:
            st.markdown("### 트렌드 클러스터")
            for c in clusters:
                with st.expander(f"{c['label']} (n={len(c['items'])})", expanded=False):
                    for it in c["items"]:
                        st.write(f"- {it.get('title')} ({it.get('url')})")

        st.divider()
        st.markdown("### Recommendation Loop Metrics")
        reco_df = _load_reco_events_df()
        if reco_df.empty:
            st.caption("No recommendation click events yet.")
        else:
            st.caption(f"events: {len(reco_df)}")
            a1, a2 = st.columns([1, 1])
            with a1:
                st.download_button(
                    "Download reco events CSV",
                    data=reco_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"staypick_reco_events_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                )
            with a2:
                if st.button("Reset reco events", key="reset_reco_events"):
                    try:
                        path = os.path.join(APP_DIR, "data", "reco_events.csv")
                        if os.path.exists(path):
                            os.remove(path)
                    except Exception:
                        pass
                    st.session_state["reco_click_counts"] = {}
                    st.session_state["clicked_category_counts"] = {}
                    st.rerun()
            c1, c2, c3 = st.columns(3)
            c1.metric("People also viewed", int((reco_df["placement"] == "people_also_viewed").sum()) if "placement" in reco_df.columns else 0)
            c2.metric("Next up", int((reco_df["placement"] == "next_up").sum()) if "placement" in reco_df.columns else 0)
            c3.metric("Unique targets", int(reco_df["to_url"].nunique()) if "to_url" in reco_df.columns else 0)
            if "placement" in reco_df.columns:
                top_place = reco_df.groupby("placement", as_index=False).size().sort_values("size", ascending=False)
                st.dataframe(top_place, use_container_width=True)
            if "category" in reco_df.columns:
                top_cat = reco_df.groupby("category", as_index=False).size().sort_values("size", ascending=False)
                st.dataframe(top_cat.head(10), use_container_width=True)

        st.divider()
        st.markdown("### Upsell Funnel")
        upsell_df = _load_upsell_events_df()
        if upsell_df.empty:
            st.caption("No upsell events yet.")
        else:
            upsell_df = upsell_df.copy()
            upsell_df["ts"] = pd.to_datetime(upsell_df.get("ts", ""), errors="coerce")
            upsell_df["event"] = upsell_df.get("event", "").astype(str)
            upsell_days = st.slider("Upsell recent days", min_value=1, max_value=30, value=14)
            upsell_cutoff = datetime.now() - timedelta(days=int(upsell_days))
            upsell_df = upsell_df[upsell_df["ts"].isna() | (upsell_df["ts"] >= upsell_cutoff)]

            views = int((upsell_df["event"] == "upsell_view").sum())
            clicks = int(upsell_df["event"].isin(["upsell_click_basic", "upsell_click_pro"]).sum())
            upgrades = int(upsell_df["event"].isin(["upgrade_applied_basic", "upgrade_applied_pro"]).sum())
            view_to_click = (clicks / views * 100.0) if views > 0 else 0.0
            click_to_upgrade = (upgrades / clicks * 100.0) if clicks > 0 else 0.0
            view_to_upgrade = (upgrades / views * 100.0) if views > 0 else 0.0
            uf1, uf2, uf3, uf4 = st.columns(4)
            uf1.metric("Upsell views", f"{views:,}")
            uf2.metric("Upsell clicks", f"{clicks:,}")
            uf3.metric("Upgrades", f"{upgrades:,}")
            uf4.metric("View→Upgrade", f"{view_to_upgrade:.2f}%")
            st.caption(f"View→Click: {view_to_click:.2f}% · Click→Upgrade: {click_to_upgrade:.2f}%")

            d1, d2 = st.columns([1, 1])
            with d1:
                st.download_button(
                    "Download upsell events CSV",
                    data=upsell_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"staypick_upsell_events_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                )
            with d2:
                if st.button("Reset upsell events", key="reset_upsell_events"):
                    try:
                        if os.path.exists(UPSELL_EVENTS_PATH):
                            os.remove(UPSELL_EVENTS_PATH)
                    except Exception:
                        pass
                    st.session_state["_upsell_view_logged_day"] = ""
                    st.rerun()

        st.divider()
        st.markdown("### Ranking A/B Report")
        ce_df = _load_content_events_df()
        if ce_df is None or ce_df.empty:
            st.caption("No content events yet.")
        else:
            ce_df = ce_df.copy()
            ce_df["ts"] = pd.to_datetime(ce_df.get("ts", ""), errors="coerce")
            ce_df["event"] = ce_df.get("event", "").astype(str)
            ce_df["variant"] = ce_df.get("variant", "").astype(str).replace("", "unknown")
            ce_df["placement"] = ce_df.get("placement", "").astype(str)

            days = st.slider("Recent days", min_value=1, max_value=30, value=7)
            cutoff = datetime.now() - timedelta(days=int(days))
            ce_df = ce_df[ce_df["ts"].isna() | (ce_df["ts"] >= cutoff)]

            st.caption(f"events (last {days}d): {len(ce_df)}")
            c_ab1, c_ab2 = st.columns([1, 1])
            with c_ab1:
                st.download_button(
                    "Download content events CSV",
                    data=ce_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"staypick_content_events_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                )
            with c_ab2:
                if st.button("Reset content events", key="reset_content_events"):
                    try:
                        path = os.path.join(APP_DIR, "data", "content_events.csv")
                        if os.path.exists(path):
                            os.remove(path)
                    except Exception:
                        pass
                    st.session_state["content_impressions"] = set()
                    st.rerun()

            imp = ce_df[ce_df["event"] == "impression"].groupby("variant").size().rename("impressions")
            clk = ce_df[ce_df["event"] == "click"].groupby("variant").size().rename("clicks")
            view = ce_df[ce_df["event"] == "view"].copy()
            if not view.empty:
                view["dwell_sec"] = pd.to_numeric(view.get("dwell_sec", 0), errors="coerce").fillna(0.0)
                skip_thr = float(st.session_state.get("skip_threshold_sec", 8.0) or 8.0)
                view["is_skip"] = view["dwell_sec"] < skip_thr
                v_agg = view.groupby("variant").agg(
                    avg_dwell_sec=("dwell_sec", "mean"),
                    skip_rate=("is_skip", "mean"),
                    views=("event", "count"),
                )
            else:
                v_agg = pd.DataFrame(columns=["avg_dwell_sec", "skip_rate", "views"])

            ab = pd.concat([imp, clk, v_agg], axis=1).fillna(0.0)
            ab["ctr"] = ab.apply(
                lambda r: (float(r.get("clicks", 0)) / float(r.get("impressions", 0))) if float(r.get("impressions", 0)) > 0 else 0.0,
                axis=1,
            )
            ab = ab.reset_index().rename(columns={"index": "variant"}).sort_values(["variant"])
            ab_view = ab[["variant", "impressions", "clicks", "ctr", "avg_dwell_sec", "skip_rate"]].copy()
            st.markdown("핵심 지표 5개만 표시합니다: `impressions`, `clicks`, `ctr`, `avg_dwell_sec`, `skip_rate`")
            st.dataframe(ab_view, use_container_width=True)

            if not ab_view.empty and "variant" in ab_view.columns:
                st.markdown("#### Winner suggestion")
                st.caption("기준: CTR(0.5) + 평균체류(0.3) + (1-스킵률)(0.2)로 빠른 판단용 점수")
                def _score_row(r: pd.Series) -> float:
                    ctr = float(r.get("ctr", 0) or 0)
                    dwell = float(r.get("avg_dwell_sec", 0) or 0)
                    skip = float(r.get("skip_rate", 0) or 0)
                    return (ctr * 0.5) + (min(dwell, 300.0) / 300.0 * 0.3) + ((1.0 - skip) * 0.2)

                ab_local = ab_view.copy()
                ab_local["score"] = ab_local.apply(_score_row, axis=1)
                best = ab_local.sort_values("score", ascending=False).head(1)
                if not best.empty:
                    winner = str(best.iloc[0].get("variant", "control"))
                    st.caption(f"Suggested winner: {winner} (heuristic score)")
                    c_w1, c_w2 = st.columns([1, 1])
                    with c_w1:
                        if st.button("실험 종료 및 적용", key="set_rank_winner"):
                            if winner in {"control", "quality"}:
                                st.session_state["rank_ab_mode"] = "quality" if winner == "quality" else "baseline"
                                st.success("Ranking mode updated.")
                    with c_w2:
                        if st.button("A/B 계속 진행", key="keep_ab_running"):
                            st.session_state["rank_ab_mode"] = "ab"
                            st.success("A/B mode kept.")

            st.markdown("#### Trend by day")
            if not ce_df.empty and "ts" in ce_df.columns:
                ce_df["date"] = ce_df["ts"].dt.date
                imp_d = ce_df[ce_df["event"] == "impression"].groupby(["date", "variant"]).size().rename("impressions")
                clk_d = ce_df[ce_df["event"] == "click"].groupby(["date", "variant"]).size().rename("clicks")
                view_d = ce_df[ce_df["event"] == "view"].copy()
                if not view_d.empty:
                    view_d["dwell_sec"] = pd.to_numeric(view_d.get("dwell_sec", 0), errors="coerce").fillna(0.0)
                    skip_thr = float(st.session_state.get("skip_threshold_sec", 8.0) or 8.0)
                    view_d["is_skip"] = view_d["dwell_sec"] < skip_thr
                    v_d = view_d.groupby(["date", "variant"]).agg(
                        avg_dwell_sec=("dwell_sec", "mean"),
                        skip_rate=("is_skip", "mean"),
                        views=("event", "count"),
                    )
                else:
                    v_d = pd.DataFrame(columns=["avg_dwell_sec", "skip_rate", "views"])

                daily = pd.concat([imp_d, clk_d, v_d], axis=1).fillna(0.0).reset_index()
                daily["ctr"] = daily.apply(
                    lambda r: (float(r.get("clicks", 0)) / float(r.get("impressions", 0))) if float(r.get("impressions", 0)) > 0 else 0.0,
                    axis=1,
                )
                metric_opt = st.selectbox("Trend metric", options=["CTR", "Avg Dwell (sec)", "Skip rate", "Impressions", "Clicks", "Views"], index=0)
                metric_map = {
                    "CTR": "ctr",
                    "Avg Dwell (sec)": "avg_dwell_sec",
                    "Skip rate": "skip_rate",
                    "Impressions": "impressions",
                    "Clicks": "clicks",
                    "Views": "views",
                }
                mcol = metric_map.get(metric_opt, "ctr")
                pivot = daily.pivot_table(index="date", columns="variant", values=mcol, aggfunc="mean").sort_index()
                st.line_chart(pivot)

            if "placement" in ce_df.columns:
                place = (
                    ce_df[ce_df["event"] == "click"]
                    .groupby(["variant", "placement"], as_index=False)
                    .size()
                    .sort_values("size", ascending=False)
                )
                if not place.empty:
                    st.markdown("#### Clicks by placement")
                    st.dataframe(place.head(20), use_container_width=True)



# ---------------------------
# Admin: Sponsor/Ads tab
# ---------------------------
if admin_mode and tab_sponsor is not None:
    with tab_sponsor:
        sub_sponsor = subscription_snapshot()
        b2b_enabled = sub_sponsor.get("tier") == "pro"
        st.subheader("💰 스폰서/광고 설정(운영자)")
        st.markdown(
            """
StayPick은 일반 유저에게는 **포털형 피드**로 경험을 제공하고, 수익화는 아래처럼 확장할 수 있어요.

- **네이티브 스폰서 카드(광고)**: 카테고리/키워드 매칭으로 자연스럽게 노출
- **어필리에이트 링크**: 구매/가입 전환 기반 수익
- **브랜드 스폰서십(직접 세일즈)**: 특정 카테고리 독점/고정 배치

해커톤 MVP에서는 '스폰서 카드' + 클릭/노출 로그로 **수익화 가능성**을 명확히 보여주는 것이 목표입니다.
"""
        )
        st.markdown("### 🧮 Monetization KPI (Auto)")
        profile_now = str(st.session_state.get("monetization_profile", "A") or "A").upper()
        assumption = MONETIZATION_ASSUMPTIONS.get(profile_now, MONETIZATION_ASSUMPTIONS["A"])
        default_paid_rate = float(assumption.get("paid_rate", 0.018) or 0.018)
        default_pro_share = float(assumption.get("pro_share", 0.25) or 0.25)
        k1, k2, k3 = st.columns(3)
        with k1:
            active_users_est = int(st.number_input("Estimated MAU", min_value=100, value=10000, step=100))
        with k2:
            period_days_est = int(st.number_input("Observed period days", min_value=1, value=30, step=1))
        with k3:
            paid_rate_input = float(
                st.number_input("Paid conversion rate (if no data)", min_value=0.0, max_value=1.0, value=default_paid_rate, step=0.001, format="%.3f")
            )
        pro_share_input = float(st.slider("Pro share among paid users", min_value=0.0, max_value=1.0, value=default_pro_share, step=0.01))
        st.caption(
            f"Profile default ({profile_now}) -> paid_rate {default_paid_rate*100:.2f}% · pro_share {default_pro_share*100:.1f}%"
        )
        pricing_now = MONETIZATION_PRICING.get(profile_now, MONETIZATION_PRICING["A"])
        st.caption(
            f"Pricing package ({profile_now}) -> Basic {int(pricing_now.get('basic', 4900)):,} / Pro {int(pricing_now.get('pro', 9900)):,} (monthly)"
        )

        # Load inventory
        ads_list = load_ads(APP_DIR)

        # Event logs
        events_path = os.path.join(APP_DIR, "data", "ads_events.csv")
        st.markdown("### 📈 광고 성과(로컬 로그)")
        if os.path.exists(events_path):
            try:
                df_ev = pd.read_csv(events_path)
            except Exception:
                df_ev = pd.DataFrame()

            if df_ev is None or df_ev.empty:
                st.caption("아직 이벤트가 없습니다. 피드에서 스폰서 카드를 노출/클릭해보세요.")
            else:
                pivot = (
                    df_ev.pivot_table(index="ad_id", columns="event", values="ts", aggfunc="count", fill_value=0)
                    .reset_index()
                    .rename_axis(None, axis=1)
                )
                if "impression" not in pivot.columns:
                    pivot["impression"] = 0
                if "click" not in pivot.columns:
                    pivot["click"] = 0
                pivot["CTR(%)"] = pivot.apply(
                    lambda r: (float(r.get("click", 0)) / float(r.get("impression", 0)) * 100.0) if float(r.get("impression", 0)) > 0 else 0.0,
                    axis=1,
                )
                st.dataframe(pivot, use_container_width=True)
                ad_by_id = {a.id: a for a in ads_list}
                if "affiliate_click" not in pivot.columns:
                    pivot["affiliate_click"] = 0
                if "affiliate_lead" not in pivot.columns:
                    pivot["affiliate_lead"] = 0
                if "affiliate_purchase" not in pivot.columns:
                    pivot["affiliate_purchase"] = 0
                pivot["affiliate_conversion"] = pivot["affiliate_lead"] + pivot["affiliate_purchase"]
                pivot["pricing_type"] = pivot.apply(
                    lambda r: str(((ad_by_id.get(str(r.get("ad_id", ""))).pricing or {}).get("type", "CPC") if ad_by_id.get(str(r.get("ad_id", ""))) else "CPC")).upper(),
                    axis=1,
                )
                pivot["ad_rev_est_krw"] = pivot.apply(
                    lambda r: (
                        float(r.get("click", 0))
                        * float((ad_by_id.get(str(r.get("ad_id", ""))).pricing or {}).get("cpc_krw", 0) or 0)
                        if str(r.get("pricing_type", "CPC")).upper() == "CPC"
                        else float(r.get("affiliate_conversion", 0))
                        * float((ad_by_id.get(str(r.get("ad_id", ""))).pricing or {}).get("cpa_krw", 0) or 0)
                    )
                    if ad_by_id.get(str(r.get("ad_id", "")))
                    else 0.0,
                    axis=1,
                )
                pivot["affiliate_rev_est_krw"] = pivot.apply(
                    lambda r: float(r.get("affiliate_conversion", 0))
                    * float((ad_by_id.get(str(r.get("ad_id", ""))).pricing or {}).get("cpa_krw", 0) or 0)
                    if ad_by_id.get(str(r.get("ad_id", ""))) and str(r.get("pricing_type", "CPC")).upper() == "CPC"
                    else 0.0,
                    axis=1,
                )
                pivot["total_rev_est_krw"] = pivot["ad_rev_est_krw"] + pivot["affiliate_rev_est_krw"]
                pivot["CVR(%)"] = pivot.apply(
                    lambda r: (float(r.get("affiliate_conversion", 0)) / float(r.get("affiliate_click", 0)) * 100.0)
                    if float(r.get("affiliate_click", 0)) > 0
                    else 0.0,
                    axis=1,
                )
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Impressions", f"{int(pivot['impression'].sum()):,}")
                m2.metric("Clicks", f"{int(pivot['click'].sum()):,}")
                m3.metric("Affiliate Conv", f"{int(pivot['affiliate_conversion'].sum()):,}")
                m4.metric("Ad Rev Est (KRW)", f"{int(pivot['ad_rev_est_krw'].sum()):,}")
                m5.metric("Total Rev Est (KRW)", f"{int(pivot['total_rev_est_krw'].sum()):,}")

                upsell_df = _load_upsell_events_df()
                paid_rate_obs = 0.0
                pro_share_obs = 0.0
                if upsell_df is not None and not upsell_df.empty and "event" in upsell_df.columns:
                    upsell_df = upsell_df.copy()
                    upsell_df["ts"] = pd.to_datetime(upsell_df.get("ts", ""), errors="coerce")
                    upsell_cutoff = datetime.now() - timedelta(days=int(period_days_est))
                    upsell_df = upsell_df[upsell_df["ts"].isna() | (upsell_df["ts"] >= upsell_cutoff)]
                    views_u = int((upsell_df["event"] == "upsell_view").sum())
                    upgrades_u = int(upsell_df["event"].isin(["upgrade_applied_basic", "upgrade_applied_pro"]).sum())
                    pro_up_u = int((upsell_df["event"] == "upgrade_applied_pro").sum())
                    paid_rate_obs = (upgrades_u / views_u) if views_u > 0 else 0.0
                    pro_share_obs = (pro_up_u / upgrades_u) if upgrades_u > 0 else 0.0

                paid_rate_used = paid_rate_obs if paid_rate_obs > 0 else paid_rate_input
                pro_share_used = pro_share_obs if pro_share_obs > 0 else pro_share_input
                basic_share_used = max(1.0 - pro_share_used, 0.0)
                monthly_factor = 30.0 / max(float(period_days_est), 1.0)
                mrr_ads_est = float(pivot["total_rev_est_krw"].sum()) * monthly_factor
                projected_paid_users = float(active_users_est) * float(paid_rate_used)
                mrr_sub_est = projected_paid_users * (
                    basic_share_used * float(sub_sponsor.get("price_basic", 4900))
                    + pro_share_used * float(sub_sponsor.get("price_pro", 9900))
                )
                total_mrr_est = mrr_sub_est + mrr_ads_est
                arpu_est = total_mrr_est / max(float(active_users_est), 1.0)

                st.caption(
                    f"Profile {profile_now} · paid_rate={paid_rate_used*100:.2f}% · pro_share={pro_share_used*100:.1f}%"
                )
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("Projected Paid Users", f"{int(projected_paid_users):,}")
                kpi2.metric("MRR Sub Est (KRW)", f"{int(mrr_sub_est):,}")
                kpi3.metric("MRR Ads Est (KRW)", f"{int(mrr_ads_est):,}")
                kpi4.metric("MRR Total Est (KRW)", f"{int(total_mrr_est):,}")
                st.caption(f"Projected ARPU (KRW/user/mo): {arpu_est:,.1f}")

                st.markdown("#### B2B report export")
                b2b_rows = []
                for _, r in pivot.iterrows():
                    ad_id = str(r.get("ad_id", ""))
                    ad = ad_by_id.get(ad_id)
                    b2b_rows.append(
                        {
                            "ad_id": ad_id,
                            "brand": (ad.brand if ad else ""),
                            "pricing_type": str(((ad.pricing or {}).get("type", "CPC") if ad else "CPC")).upper(),
                            "impression": float(r.get("impression", 0) or 0),
                            "click": float(r.get("click", 0) or 0),
                            "affiliate_click": float(r.get("affiliate_click", 0) or 0),
                            "affiliate_lead": float(r.get("affiliate_lead", 0) or 0),
                            "affiliate_purchase": float(r.get("affiliate_purchase", 0) or 0),
                            "affiliate_conversion": float(r.get("affiliate_conversion", 0) or 0),
                            "ctr_pct": float(r.get("CTR(%)", 0) or 0),
                            "cvr_pct": float(r.get("CVR(%)", 0) or 0),
                            "ad_rev_est_krw": float(r.get("ad_rev_est_krw", 0) or 0),
                            "affiliate_rev_est_krw": float(r.get("affiliate_rev_est_krw", 0) or 0),
                            "total_rev_est_krw": float(r.get("total_rev_est_krw", 0) or 0),
                            "ecpm_krw": (
                                float(r.get("ad_rev_est_krw", 0) or 0) * 1000.0 / float(r.get("impression", 0) or 0)
                                if float(r.get("impression", 0) or 0) > 0
                                else 0.0
                            ),
                            "rpm_krw": (
                                float(r.get("total_rev_est_krw", 0) or 0) * 1000.0 / float(r.get("impression", 0) or 0)
                                if float(r.get("impression", 0) or 0) > 0
                                else 0.0
                            ),
                            "arpu_est_krw": float(r.get("total_rev_est_krw", 0) or 0) / max(float(active_users_est), 1.0),
                        }
                    )
                b2b_df = pd.DataFrame(b2b_rows)
                st.download_button(
                    "Download B2B CSV",
                    data=b2b_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"staypick_b2b_monetization_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    disabled=not b2b_enabled,
                )

                # B2B-ready category performance view (ad/affiliate + content quality)
                if "content_category" in df_ev.columns:
                    cat_pivot = (
                        df_ev.pivot_table(index="content_category", columns="event", values="ts", aggfunc="count", fill_value=0)
                        .reset_index()
                        .rename_axis(None, axis=1)
                    )
                    if "impression" not in cat_pivot.columns:
                        cat_pivot["impression"] = 0
                    if "click" not in cat_pivot.columns:
                        cat_pivot["click"] = 0
                    if "affiliate_click" not in cat_pivot.columns:
                        cat_pivot["affiliate_click"] = 0
                    if "affiliate_lead" not in cat_pivot.columns:
                        cat_pivot["affiliate_lead"] = 0
                    if "affiliate_purchase" not in cat_pivot.columns:
                        cat_pivot["affiliate_purchase"] = 0
                    cat_pivot["affiliate_conversion"] = cat_pivot["affiliate_lead"] + cat_pivot["affiliate_purchase"]
                    cat_pivot["CTR(%)"] = cat_pivot.apply(
                        lambda r: (float(r.get("click", 0)) / float(r.get("impression", 0)) * 100.0) if float(r.get("impression", 0)) > 0 else 0.0,
                        axis=1,
                    )
                    cat_pivot["CVR(%)"] = cat_pivot.apply(
                        lambda r: (float(r.get("affiliate_conversion", 0)) / float(r.get("affiliate_click", 0)) * 100.0)
                        if float(r.get("affiliate_click", 0)) > 0
                        else 0.0,
                        axis=1,
                    )
                    df_sc_local = st.session_state.get("df_scored", pd.DataFrame())
                    if (
                        df_sc_local is not None
                        and not df_sc_local.empty
                        and "url" in df_sc_local.columns
                        and "engagement_score" in df_sc_local.columns
                    ):
                        quality = (
                            df_sc_local.groupby("category", dropna=False)
                            .agg(
                                avg_engagement=("engagement_score", "mean"),
                                avg_dwell_sec=("avg_dwell_sec", "mean"),
                                avg_visits=("visits", "mean"),
                            )
                            .reset_index()
                            .rename(columns={"category": "content_category"})
                        )
                        cat_pivot = cat_pivot.merge(quality, on="content_category", how="left")
                    st.markdown("#### Category performance (B2B)")
                    st.dataframe(cat_pivot.sort_values(["CTR(%)", "impression"], ascending=False), use_container_width=True)
                    st.download_button(
                        "Download Category CSV",
                        data=cat_pivot.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"staypick_b2b_category_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                        mime="text/csv",
                        disabled=not b2b_enabled,
                    )
                if not b2b_enabled:
                    st.info("B2B CSV export is available on Pro plan.")
        else:
            st.caption("이벤트 로그 파일이 없습니다. data 폴더를 확인해주세요.")

        st.divider()
        st.markdown("### 📦 현재 스폰서 인벤토리")
        if not ads_list:
            st.warning("인벤토리가 비어있습니다. 아래에서 스폰서를 추가하세요.")
        else:
            inv_df = pd.DataFrame(
                [
                    {
                        "id": a.id,
                        "brand": a.brand,
                        "title": a.title,
                        "pricing_type": str((a.pricing or {}).get("type", "CPC") or "CPC"),
                        "categories": ", ".join(a.categories),
                        "cpc(krw)": int((a.pricing or {}).get("cpc_krw", 0) or 0),
                        "cpa(krw)": int((a.pricing or {}).get("cpa_krw", 0) or 0),
                        "active": a.active,
                    }
                    for a in ads_list
                ]
            )
            st.dataframe(inv_df, use_container_width=True)
            with st.expander("Affiliate conversion logger", expanded=False):
                ad_ids = [a.id for a in ads_list]
                sel_ad = st.selectbox("Ad ID", options=ad_ids, key="aff_log_ad")
                conv_evt = st.selectbox("Conversion type", options=["affiliate_lead", "affiliate_purchase"], key="aff_log_type")
                conv_n = st.number_input("Count", min_value=1, value=1, step=1, key="aff_log_count")
                if st.button("Log conversion", key="aff_log_btn"):
                    for _ in range(int(conv_n)):
                        log_event(
                            APP_DIR,
                            event=conv_evt,
                            ad_id=sel_ad,
                            placement="affiliate_report",
                            content_url="",
                            content_category="",
                            persona="admin",
                            query="manual_conversion",
                        )
                    st.success(f"Logged {int(conv_n)} events: {conv_evt}")
                    st.rerun()

        st.divider()
        st.markdown("### ➕ 새 스폰서 추가")

        # category options from current dataset
        df_scored = st.session_state.get("df_scored", pd.DataFrame())
        cat_options = ["전체"]
        if df_scored is not None and not df_scored.empty and "category" in df_scored.columns:
            cat_options += sorted([c for c in df_scored["category"].dropna().unique().tolist() if str(c).strip()])
        cat_options = list(dict.fromkeys(cat_options))

        st.session_state.setdefault("new_ad_title", "")
        st.session_state.setdefault("new_ad_desc", "")
        st.session_state.setdefault("new_ad_hook", "")
        st.session_state.setdefault("new_ad_cta", "")
        st.session_state.setdefault("new_ad_kw", "")
        st.session_state.setdefault("new_ad_img", "")

        brand = st.text_input("브랜드/광고주", value="")
        landing_url = st.text_input("랜딩 URL", value="")
        product_desc = st.text_area("상품/서비스 설명(선택)", placeholder="예: 직장인 재테크 입문자를 위한 자동 예산 관리 앱", height=90)
        image_url = st.text_input("썸네일 이미지 URL(선택)", value=st.session_state.get("new_ad_img", ""), placeholder="예: https://.../image.png")
        cats = st.multiselect("타겟 카테고리", options=cat_options, default=["전체"])
        pricing_type = st.selectbox("Pricing type", options=["CPC", "CPA"], index=0)
        cpc = st.number_input("가정 CPC(원)", min_value=0, value=100, step=10)
        cpa = st.number_input("가정 CPA(원)", min_value=0, value=0, step=100)
        active = st.checkbox("활성화", value=True)

        st.markdown("#### 카피")
        hook_in = st.text_input("훅(클릭 유도 한 줄)", value=st.session_state.get("new_ad_hook", ""), placeholder="예: 🔥 월급날 이후도 통장 살아남는 법")
        title_in = st.text_input("타이틀", value=st.session_state.get("new_ad_title", ""))
        desc_in = st.text_area("설명", value=st.session_state.get("new_ad_desc", ""), height=70)
        cta_in = st.text_input("CTA", value=st.session_state.get("new_ad_cta", ""), placeholder="예: 지금 확인")
        kw_in = st.text_input("키워드(쉼표)", value=st.session_state.get("new_ad_kw", ""), placeholder="예: 월급,저축,자동이체")

        colA, colB = st.columns([1, 1])
        with colA:
            if st.button("🤖 AI로 카피 생성"):
                if not api_key:
                    st.error("OPENAI_API_KEY를 먼저 입력하세요.")
                else:
                    try:
                        ai = ensure_ai()
                    except Exception as e:
                        st.error(str(e))
                    else:
                        schema = {
                            "type": "object",
                            "properties": {
                                "hook": {"type": "string"},
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "cta": {"type": "string"},
                                "keywords": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 10},
                            },
                            "required": ["hook", "title", "description", "cta", "keywords"],
                            "additionalProperties": False,
                        }
                        system = (
                            "너는 퍼포먼스 마케터다. 네이티브 광고 카드용 카피를 만든다. "
                            "과장/허위/의학적 효능 등 민감 표현은 금지. 짧고 클릭 유도되게 한국어로 작성. "
                            "광고임이 드러나도록 직접적 표기는 훅/타이틀에 넣지 말고, UI에서 라벨로 표시한다."
                        )
                        user = f"""
[광고주]
- 브랜드: {brand or '(미정)'}
- 랜딩: {landing_url or '(미정)'}
- 타겟 카테고리: {', '.join(cats) if cats else '전체'}
- 상품/서비스 설명: {product_desc or '(없음)'}

요구사항:
- 훅(hook)은 14~24자 내외, 호기심/도파민(하지만 사실 기반)
- 타이틀은 18~28자 내외
- 설명은 35~60자 내외
- CTA는 2~8자
- 키워드는 3~10개
""".strip()

                        with st.spinner("AI 카피 생성 중..."):
                            try:
                                resp = ai.client.responses.create(
                                    model=model,
                                    input=[
                                        {"role": "system", "content": system},
                                        {"role": "user", "content": user},
                                    ],
                                    text={
                                        "format": {
                                            "type": "json_schema",
                                            "name": "ad_copy",
                                            "schema": schema,
                                            "strict": True,
                                        }
                                    },
                                    store=False,
                                )
                                data = json.loads(resp.output_text)
                                st.session_state["new_ad_hook"] = data.get("hook", "")
                                st.session_state["new_ad_title"] = data.get("title", "")
                                st.session_state["new_ad_desc"] = data.get("description", "")
                                st.session_state["new_ad_cta"] = data.get("cta", "")
                                st.session_state["new_ad_kw"] = ",".join(data.get("keywords") or [])
                                st.success("카피 생성 완료! 아래 입력칸에 반영되었습니다.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"생성 실패: {e}")

        with colB:
            if st.button("➕ 인벤토리에 추가", type="primary"):
                if not landing_url.strip():
                    st.error("랜딩 URL은 필수입니다.")
                elif not title_in.strip():
                    st.error("타이틀은 필수입니다.")
                else:
                    new_id = f"sp_{int(time.time())}"
                    new_ad = Ad(
                        id=new_id,
                        brand=(brand or "(unknown)"),
                        hook=(hook_in.strip() or ""),
                        title=title_in.strip(),
                        description=desc_in.strip(),
                        cta=(cta_in.strip() or "자세히"),
                        landing_url=landing_url.strip(),
                        categories=cats or ["전체"],
                        keywords=[k.strip() for k in (kw_in or "").split(",") if k.strip()],
                        pricing={"type": pricing_type, "cpc_krw": int(cpc), "cpa_krw": int(cpa)},
                        image_url=(image_url.strip() or ""),
                        active=bool(active),
                    )
                    ads_list.append(new_ad)
                    try:
                        save_ads(APP_DIR, ads_list)
                        st.success(f"추가 완료! (id={new_id})")
                    except Exception as e:
                        st.error(f"저장 실패: {e}")

        st.divider()
        st.markdown("### ✏️ 인벤토리 편집")
        st.caption("*해커톤 데모용으로 간단 편집 기능만 제공합니다*")

        if ads_list:
            edited: List[Ad] = []
            for a in ads_list:
                with st.expander(f"{a.id} · {a.brand}", expanded=False):
                    a_active = st.checkbox("활성", value=a.active, key=f"ad_active_{a.id}")
                    a_hook = st.text_input("훅(클릭 유도 한 줄)", value=getattr(a, "hook", ""), key=f"ad_hook_{a.id}")
                    a_title = st.text_input("타이틀", value=a.title, key=f"ad_title_{a.id}")
                    a_desc = st.text_area("설명", value=a.description, height=70, key=f"ad_desc_{a.id}")
                    a_cta = st.text_input("CTA", value=a.cta, key=f"ad_cta_{a.id}")
                    a_url = st.text_input("랜딩 URL", value=a.landing_url, key=f"ad_url_{a.id}")
                    a_img = st.text_input("썸네일 이미지 URL(선택)", value=getattr(a, "image_url", ""), key=f"ad_img_{a.id}")
                    a_cats = st.text_input("카테고리(쉼표)", value=", ".join(a.categories), key=f"ad_cats_{a.id}")
                    a_kw = st.text_input("키워드(쉼표)", value=", ".join(a.keywords), key=f"ad_kw_{a.id}")
                    a_type = st.selectbox(
                        "Pricing type",
                        options=["CPC", "CPA"],
                        index=0 if str((a.pricing or {}).get("type", "CPC")).upper() == "CPC" else 1,
                        key=f"ad_type_{a.id}",
                    )
                    a_cpc = st.number_input(
                        "CPC(원)",
                        min_value=0,
                        value=int((a.pricing or {}).get("cpc_krw", 0) or 0),
                        step=10,
                        key=f"ad_cpc_{a.id}",
                    )
                    a_cpa = st.number_input(
                        "CPA(원)",
                        min_value=0,
                        value=int((a.pricing or {}).get("cpa_krw", 0) or 0),
                        step=100,
                        key=f"ad_cpa_{a.id}",
                    )

                    edited.append(
                        Ad(
                            id=a.id,
                            brand=a.brand,
                            hook=a_hook,
                            title=a_title,
                            description=a_desc,
                            cta=a_cta,
                            landing_url=a_url,
                            categories=[c.strip() for c in a_cats.split(",") if c.strip()],
                            keywords=[k.strip() for k in a_kw.split(",") if k.strip()],
                            pricing={"type": a_type, "cpc_krw": int(a_cpc), "cpa_krw": int(a_cpa)},
                            image_url=a_img,
                            active=bool(a_active),
                        )
                    )

            if st.button("💾 변경 저장"):
                try:
                    save_ads(APP_DIR, edited)
                    st.success("저장 완료! 피드에 즉시 반영됩니다.")
                except Exception as e:
                    st.error(f"저장 실패: {e}")


# ---------------------------
# Admin: Global / SEO tab
# ---------------------------
if admin_mode and tab_global is not None:
    with tab_global:
        sub_global = subscription_snapshot()
        programmatic_seo_enabled = sub_global.get("tier") == "pro"
        st.subheader("🌍 글로벌 확장 & SEO")
        st.markdown(
            """
Streamlit 기반 MVP는 **데모/해커톤에는 최고**지만, 검색 엔진이 잘 크롤링하는 구조(SSR/정적 페이지)로 만들기는 제한이 있습니다.

그래서 StayPick의 글로벌/SEO는 보통 이렇게 갑니다:
1) **앱(StayPick)**: 실시간 피드/요약/재가공(인터랙티브)
2) **SEO 퍼블리싱(정적 페이지)**: 요약/재가공 결과를 HTML로 내보내서(정적) 검색 유입을 받기

아래는 MVP에서도 바로 가능한 **SEO HTML Export** 기능입니다.
"""
        )

        st.markdown("### 🔗 언어 고정 링크")
        st.caption("배포 후에는 URL에 `?lang=en`처럼 붙이면 해당 언어로 바로 열리게 할 수 있어요.")
        st.code("/ ?lang=ko   |   / ?lang=en   |   / ?lang=ja   |   / ?lang=es")

        st.markdown("### 🗺️ 지역별 대표 언어(기본값 예시)")
        st.markdown(
            """
- **북미/오세아니아**: English
- **중남미**: Español / Português
- **유럽**: English(공용) + FR/DE/ES(확장)
- **중동/북아프리카**: العربية
- **아프리카(사하라 이남)**: English / Français / Kiswahili
- **동아시아**: 中文 / 日本語 / 한국어
- **동남아**: English + ID/TH/VI(확장)
- **남아시아**: हिन्दी + English
"""
        )
        st.caption("실서비스에서는 보통 IP Geo(Cloudflare/Vercel) + 브라우저 언어(Accept-Language)로 기본 언어를 결정하고, 항상 수동 변경을 허용합니다.")

        st.divider()
        st.markdown("### 📄 SEO HTML 패키지로 내보내기")
        selected_list: List[Dict[str, Any]] = st.session_state.get("selected_summaries", [])
        if not selected_list:
            st.info("먼저 피드에서 글을 '저장'한 뒤, 여기서 HTML로 내보낼 수 있어요.")
        else:
            export_lang = st.selectbox(
                "Export language",
                options=["auto", "ko", "en", "ja", "es"],
                format_func=lambda x: {"auto": "Auto (UI)", "ko": "한국어", "en": "English", "ja": "日本語", "es": "Español"}.get(x, x),
                index=0,
            )
            lang_now = st.session_state.get("ui_lang", "ko")
            lang_export = lang_now if export_lang == "auto" else normalize_lang(export_lang)

            if st.button("📦 저장 목록을 HTML ZIP으로 내보내기", type="primary"):
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
                    for s in selected_list:
                        title_for_export = (s.get("localized_title") or s.get("title") or "staypick").strip()
                        desc_for_export = (s.get("one_liner") or s.get("summary") or "").strip()[:180]
                        url = (s.get("url") or "").strip()
                        body_html = "".join(
                            [
                                f"<h2>One-liner</h2><p>{html.escape((s.get('one_liner') or '').strip())}</p>",
                                f"<h2>Summary</h2><p>{html.escape((s.get('summary') or '').strip())}</p>",
                                "<h2>Key points</h2><ul>" + "".join([f"<li>{html.escape(str(x))}</li>" for x in (s.get('key_points') or [])]) + "</ul>",
                                "<h2>Tags</h2><p>" + ", ".join([html.escape(str(x)) for x in (s.get('tags') or [])]) + "</p>",
                                f"<h2>Sources</h2><p><a href='{html.escape(url)}'>{html.escape(url)}</a></p>",
                            ]
                        )
                        html_text = render_html(
                            SEOPage(
                                title=title_for_export,
                                description=desc_for_export,
                                lang=lang_export,
                                canonical_url=url,
                                body_html=body_html,
                            )
                        )
                        fn = f"{slugify(title_for_export)}_{lang_export}.html"
                        z.writestr(fn, html_text)

                buf.seek(0)
                st.download_button(
                    "⬇️ ZIP 다운로드",
                    data=buf.getvalue(),
                    file_name=f"staypick_seo_export_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                    mime="application/zip",
                )
                st.success("내보내기 준비 완료! (이 ZIP을 정적 호스팅에 올리면 SEO 페이지가 됩니다)")


        # ---------------------------
        # Programmatic SEO export (/{lang}/{country}/{category}/)
        # ---------------------------
        st.divider()
        st.markdown("### 🚀 Programmatic SEO 패키지 (/{lang}/{country}/{category}/)")
        st.caption(
            "카테고리별 Top N을 **정적 HTML 폴더 구조**로 내보냅니다. "
            "예: /ko/kr/game/ · /en/us/finance/ · /ja/jp/travel/"
        )

        df_scored = st.session_state.get("df_scored", pd.DataFrame())
        if df_scored is None or df_scored.empty:
            st.info("데이터가 없습니다. 먼저 ‘데이터(운영자)’ 탭에서 CSV/URL을 넣어주세요.")
        else:
            colP1, colP2, colP3 = st.columns([1, 1, 1], gap="medium")
            with colP1:
                export_lang = st.selectbox("페이지 언어(lang)", options=["ko", "en", "ja", "es"], index=["ko", "en", "ja", "es"].index(st.session_state.get("ui_lang", "ko")))
            with colP2:
                country_code = st.selectbox("국가 코드(country)", options=["kr", "us", "jp", "es", "mx", "br", "id", "vn", "th", "fr", "de"], index=0)
            with colP3:
                top_k = st.slider("카테고리별 Top N", min_value=3, max_value=20, value=10, step=1)

            # Audience tuning for summaries/hooks on SEO pages
            age_for_seo = st.selectbox(
                t("age_group") + " (SEO용)",
                options=["general", "elem", "mid", "high", "uni", "20s", "30s"],
                format_func=lambda x: {
                    "general": t("age_general"),
                    "elem": t("age_elem"),
                    "mid": t("age_mid"),
                    "high": t("age_high"),
                    "uni": t("age_uni"),
                    "20s": t("age_20s"),
                    "30s": t("age_30s"),
                }.get(x, x),
                index=["general", "elem", "mid", "high", "uni", "20s", "30s"].index("general"),
            )

            base_url = st.text_input("Base URL(선택, sitemap용)", value="", placeholder="예: https://staypick.yourdomain.com")

            categories_all = sorted([c for c in df_scored.get("category", pd.Series(dtype=str)).dropna().unique().tolist() if str(c).strip()]) or ["전체"]
            default_cats = categories_all[: min(len(categories_all), 6)]
            cats_sel = st.multiselect("내보낼 카테고리", options=categories_all, default=default_cats)

            use_ai = st.checkbox("AI 요약/훅 포함(권장)", value=True, help="체류/클릭을 돕는 제목/훅/요약을 함께 넣습니다. (OpenAI API 사용)")
            if use_ai and not api_key:
                st.warning("AI 요약을 포함하려면 OPENAI_API_KEY가 필요합니다. (환경변수 또는 사이드바 입력)")

            # Simple mapping to make pretty slugs for common Korean categories
            CAT_SLUG = {
                "게임": "game",
                "연애/썰": "love",
                "연애": "love",
                "썰": "story",
                "여행": "travel",
                "재테크": "finance",
                "생활꿀팁": "lifehacks",
                "생활": "life",
                "테크": "tech",
                "테크트렌드": "tech",
                "전체": "all",
            }

            COUNTRY_NAME = {
                "kr": {"ko": "한국", "en": "Korea", "ja": "韓国", "es": "Corea"},
                "us": {"ko": "미국", "en": "United States", "ja": "アメリカ", "es": "EE. UU."},
                "jp": {"ko": "일본", "en": "Japan", "ja": "日本", "es": "Japón"},
                "es": {"ko": "스페인", "en": "Spain", "ja": "スペイン", "es": "España"},
                "mx": {"ko": "멕시코", "en": "Mexico", "ja": "メキシコ", "es": "México"},
                "br": {"ko": "브라질", "en": "Brazil", "ja": "ブラジル", "es": "Brasil"},
                "id": {"ko": "인도네시아", "en": "Indonesia", "ja": "インドネシア", "es": "Indonesia"},
                "vn": {"ko": "베트남", "en": "Vietnam", "ja": "ベトナム", "es": "Vietnam"},
                "th": {"ko": "태국", "en": "Thailand", "ja": "タイ", "es": "Tailandia"},
                "fr": {"ko": "프랑스", "en": "France", "ja": "フランス", "es": "Francia"},
                "de": {"ko": "독일", "en": "Germany", "ja": "ドイツ", "es": "Alemania"},
            }

            def _country_name(code: str, lang_code: str) -> str:
                return COUNTRY_NAME.get(code, {}).get(lang_code, code.upper())

            def _cat_slug(cat: str) -> str:
                c = (cat or "").strip()
                if c in CAT_SLUG:
                    return CAT_SLUG[c]
                return slugify(c)

            TITLE_TMPL = {
                "ko": lambda cn, cat, n: f"오늘 {cn}에서 오래 읽힌 {cat} TOP{n}",
                "en": lambda cn, cat, n: f"Today's Top {n} {cat} in {cn} (by dwell time)",
                "ja": lambda cn, cat, n: f"今日 {cn} で長く読まれた {cat} TOP{n}",
                "es": lambda cn, cat, n: f"Top {n} de {cat} más leídos hoy en {cn}",
            }
            DESC_TMPL = {
                "ko": lambda cn, cat: f"{cn}에서 체류시간/방문이 높았던 {cat} 글을 3초 요약으로 정리했습니다.",
                "en": lambda cn, cat: f"We summarize the {cat} posts people spent the most time on in {cn}.",
                "ja": lambda cn, cat: f"{cn}で滞在時間が長かった{cat}投稿を3秒で要約します。",
                "es": lambda cn, cat: f"Resumimos en 3s los posts de {cat} con mayor tiempo de lectura en {cn}.",
            }

            if st.button(
                "📦 Programmatic SEO ZIP 생성",
                type="primary",
                key="btn_progseo",
                disabled=not programmatic_seo_enabled,
            ):
                # Build top-k per category
                topk_df = topk_per_category(df_scored, top_k=int(top_k))
                if cats_sel:
                    topk_df = topk_df[topk_df["category"].isin(cats_sel)]
                rows = topk_df.to_dict(orient="records")

                # Group by category
                by_cat: Dict[str, List[Dict[str, Any]]] = {}
                for r in rows:
                    by_cat.setdefault(r.get("category", "전체"), []).append(r)

                # Local cache for summaries during this export
                export_cache: Dict[str, Dict[str, Any]] = {}

                # Prepare AI if needed
                ai = None
                if use_ai:
                    try:
                        ai = ensure_ai()
                    except Exception as e:
                        st.error(str(e))
                        use_ai = False

                mem = io.BytesIO()
                z = zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED)

                # Locale landing page
                lang_code = export_lang
                cn = _country_name(country_code, lang_code)

                loc_index_path = f"{lang_code}/{country_code}/index.html"
                cat_links = []
                for cat in sorted(by_cat.keys()):
                    cat_slug = _cat_slug(cat)
                    cat_links.append((cat, f"./{cat_slug}/index.html"))
                body_links = "<ul>" + "".join([f'<li><a href="{html.escape(href)}">{html.escape(cat)}</a></li>' for cat, href in cat_links]) + "</ul>"
                index_page = SEOPage(
                    title=f"StayPick · {cn}",
                    description=f"{cn} 카테고리별 TOP 콘텐츠를 3초 요약으로 제공합니다.",
                    lang=lang_code,
                    canonical_url=(base_url.rstrip("/") + "/" + loc_index_path) if base_url else "",
                    body_html=(
                        f"<h1>StayPick · {html.escape(cn)}</h1>"
                        f"<p>카테고리별 TOP{int(top_k)} · 3초 요약 + 핵심 포인트</p>"
                        f"{body_links}"
                        f"<p style='opacity:0.65;font-size:12px'>Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>"
                    ),
                )
                z.writestr(loc_index_path, render_html(index_page))

                # Category pages
                sitemap_urls = []
                if base_url:
                    sitemap_urls.append(base_url.rstrip("/") + "/" + loc_index_path)

                total_items = sum(len(v) for v in by_cat.values())
                done = 0
                prog = st.progress(0, text="HTML 생성 중...")

                for cat, items in by_cat.items():
                    cat_slug = _cat_slug(cat)
                    page_path = f"{lang_code}/{country_code}/{cat_slug}/index.html"
                    h1 = TITLE_TMPL.get(lang_code, TITLE_TMPL["en"])(cn, cat, int(top_k))
                    desc = DESC_TMPL.get(lang_code, DESC_TMPL["en"])(cn, cat)

                    # Build item list HTML
                    parts = [f"<h1>{html.escape(h1)}</h1>", f"<p>{html.escape(desc)}</p>"]
                    parts.append("<hr/>")

                    for r in items:
                        url = r.get("url", "")
                        src_title = (r.get("title") or "").strip() or url
                        content_from_csv = (r.get("content") or "").strip()
                        metrics = {
                            "visits": float(r.get("visits", 0) or 0),
                            "avg_dwell_sec": float(r.get("avg_dwell_sec", 0) or 0),
                            "engagement_score": float(r.get("engagement_score", 0) or 0),
                            "comment_count": float(r.get("comment_count", 0) or 0),
                            "published_at": str(r.get("published_at", "") or ""),
                        }

                        s = None
                        if use_ai and ai and url:
                            if url in export_cache:
                                s = export_cache[url]
                            else:
                                try:
                                    if content_from_csv:
                                        page_title, text0 = src_title, content_from_csv
                                    else:
                                        fetched_title, text0 = cached_fetch(url)
                                        page_title = fetched_title or src_title
                                    s = ai.summarize(
                                        url=url,
                                        title=page_title,
                                        content=text0,
                                        metrics=metrics,
                                        language=lang_code,
                                        age_group=age_for_seo,
                                    )
                                    export_cache[url] = s
                                except Exception:
                                    s = None

                        display_title = (s.get("localized_title") or s.get("title")) if s else src_title
                        hook = (s.get("hook") or "") if s else ""
                        one = (s.get("one_liner") or "") if s else snippet_from_content(content_from_csv, 140)
                        kps = s.get("key_points") if s else []
                        tags = s.get("tags") if s else []

                        parts.append(f"<h2><a href='{html.escape(url)}' target='_blank' rel='noopener'>{html.escape(display_title)}</a></h2>")
                        if hook:
                            parts.append(f"<p><strong>{html.escape(hook)}</strong></p>")
                        if one:
                            parts.append(f"<p>{html.escape(one)}</p>")
                        if kps:
                            parts.append("<ul>" + "".join([f"<li>{html.escape(str(k))}</li>" for k in kps[:3]]) + "</ul>")
                        if tags:
                            parts.append(
                                "<p style='opacity:0.7;font-size:12px'>"
                                + " · ".join([html.escape(str(tg)) for tg in tags[:6]])
                                + "</p>"
                            )
                        parts.append("<hr/>")

                        done += 1
                        if total_items:
                            prog.progress(min(done / total_items, 1.0), text="HTML 생성 중...")

                    page = SEOPage(
                        title=h1,
                        description=desc,
                        lang=lang_code,
                        canonical_url=(base_url.rstrip("/") + "/" + page_path) if base_url else "",
                        body_html="\n".join(parts),
                    )
                    z.writestr(page_path, render_html(page))
                    if base_url:
                        sitemap_urls.append(base_url.rstrip("/") + "/" + page_path)

                prog.empty()

                # Optional: sitemap.xml
                if base_url and sitemap_urls:
                    urls_xml = "".join([f"<url><loc>{html.escape(u)}</loc></url>" for u in sitemap_urls])
                    sitemap = "<?xml version='1.0' encoding='UTF-8'?>\n" + "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>" + urls_xml + "</urlset>"
                    z.writestr("sitemap.xml", sitemap)

                # robots.txt (basic)
                if base_url:
                    robots = "User-agent: *\nAllow: /\nSitemap: " + base_url.rstrip("/") + "/sitemap.xml\n"
                    z.writestr("robots.txt", robots)

                z.close()
                mem.seek(0)

                st.download_button(
                    "Programmatic SEO ZIP 다운로드",
                    data=mem.getvalue(),
                    file_name=f"staypick_programmatic_seo_{export_lang}_{country_code}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
                    mime="application/zip",
                )
                st.success("생성 완료! ZIP을 정적 호스팅에 업로드하면 /{lang}/{country}/{category}/ 구조로 바로 서비스할 수 있습니다.")
            if not programmatic_seo_enabled:
                st.info("Programmatic SEO export is available on Pro plan.")
