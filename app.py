from __future__ import annotations

import os
import json
import re
import html
import io
import zipfile
from datetime import datetime
import time
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from modules.metrics import load_metrics_csv, compute_engagement_score, top_by_score, topk_per_category
from modules.fetch import fetch_and_extract
from modules.ai import OpenAIService
from modules.cluster import cluster_summaries
from modules.ads import ensure_ads_storage, load_ads, save_ads, select_ads, log_event, Ad
from modules.i18n import get_translator, normalize_lang
from modules.seo import SEOPage, render_html, slugify

load_dotenv()

st.set_page_config(page_title="StayPick", layout="wide")


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

/* App background */
.stApp { background: #f6f7fb; }

/* More top padding: prevents the top area from looking 'cut' */
.block-container { padding-top: 1.8rem; padding-bottom: 3.0rem; }

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
  padding: 10px 14px;
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
  padding: 12px 12px;
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
.sp-title { font-weight: 900; font-size: 15px; line-height: 1.25; margin-top: 2px; }
.sp-snippet { font-size: 13px; color: rgba(49, 51, 63, 0.88); line-height: 1.35; margin-top: 6px; }
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
</style>
"""
st.markdown(PORTAL_CSS, unsafe_allow_html=True)


# ---------------------------
# Paths & demo
# ---------------------------
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEMO_CSV_PATH = os.path.join(APP_DIR, "sample_data", "metrics_sample_fun_with_content.csv")

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
        index=["auto", "ko", "en", "ja", "es"].index(st.session_state.get("ui_lang_choice", "auto")),
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

    # Admin mode first (so we can hide sensitive inputs for general users)
    try:
        admin_mode = st.toggle(t("admin_toggle"), value=False)
    except Exception:
        admin_mode = st.checkbox(t("admin_toggle"), value=False)

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

    # Defaults (safe)
    model = "gpt-4o-mini"
    embedding_model = "text-embedding-3-small"
    top_n = 8
    top_k_per_category = 10
    weight_visits = 0.6
    weight_dwell = 0.4

    # User-facing settings (folded)
    with st.expander(t("exp_user"), expanded=True):
        try:
            show_ads = st.toggle(t("toggle_ads"), value=True)
            show_metrics = st.toggle(t("toggle_metrics"), value=False)
            # For general users: make "View" instantly satisfying.
            auto_summarize = st.toggle(t("toggle_auto_summary"), value=True)
        except Exception:
            show_ads = st.checkbox(t("toggle_ads"), value=True)
            show_metrics = st.checkbox(t("toggle_metrics"), value=False)
            auto_summarize = st.checkbox(t("toggle_auto_summary"), value=True)

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
                value=0.6,
                step=0.05,
            )
            weight_dwell = 1.0 - weight_visits
            st.caption(f"체류시간 가중치 = {weight_dwell:.2f}")


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


def refresh_scores() -> None:
    """Recompute df_scored/top tables when weights or dataset changes."""
    if "df_raw" not in st.session_state or st.session_state["df_raw"] is None:
        return
    df_raw: pd.DataFrame = st.session_state["df_raw"]
    df_scored = compute_engagement_score(df_raw, weight_visits=weight_visits, weight_dwell=weight_dwell)
    st.session_state["df_scored"] = df_scored
    st.session_state["top_df"] = top_by_score(df_scored, top_n=top_n)
    st.session_state["topk_cat_df"] = topk_per_category(df_scored, top_k=top_k_per_category)


def init_state() -> None:
    if "df_raw" not in st.session_state:
        st.session_state["df_raw"] = load_demo_df()
        st.session_state["data_source"] = "demo"

    st.session_state.setdefault("summary_cache", {})  # url -> summary dict
    st.session_state.setdefault("ad_impressions", set())  # (ad|placement|context)
    st.session_state.setdefault("selected_summaries", [])  # list of summary dicts
    st.session_state.setdefault("selected_url", "")
    st.session_state.setdefault("open_dialog", False)
    st.session_state.setdefault("search_query", "")
    st.session_state.setdefault("interest_cats", [])
    refresh_scores()


init_state()


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


def open_item(url: str) -> None:
    st.session_state["selected_url"] = url
    st.session_state["open_dialog"] = True
    st.rerun()


def current_summary_language() -> str:
    return normalize_lang(st.session_state.get("content_lang") or st.session_state.get("ui_lang", "ko"))


def make_cache_key(url: str, lang: Optional[str], age: Optional[str]) -> str:
    lang = normalize_lang(lang or current_summary_language())
    age = (age or st.session_state.get("age_group", "general") or "general").strip()
    return f"{(url or '').strip()}||{lang}||{age}"


def get_cached_summary(
    url: str,
    language: Optional[str] = None,
    age_group: Optional[str] = None,
    cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    cache = cache if cache is not None else st.session_state.get("summary_cache", {})
    key = make_cache_key(url, language, age_group)
    return cache.get(key) or cache.get(url)


def set_cached_summary(
    url: str,
    summary: Dict[str, Any],
    language: Optional[str] = None,
    age_group: Optional[str] = None,
    cache: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    cache = cache if cache is not None else st.session_state.get("summary_cache", {})
    key = make_cache_key(url, language, age_group)
    cache[key] = summary


def add_to_selection(summary: Dict[str, Any]) -> None:
    selected: List[Dict[str, Any]] = st.session_state.get("selected_summaries", [])
    urls = {x.get("url") for x in selected}
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
tab_names = [t("tab_feed"), t("tab_make")]
if admin_mode:
    tab_names += [t("tab_data"), t("tab_insights"), t("tab_sponsor"), t("tab_global")]
tabs = st.tabs(tab_names)

tab_feed = tabs[0]
tab_make = tabs[1]
tab_data = tabs[2] if admin_mode else None
tab_insights = tabs[3] if admin_mode else None
tab_sponsor = tabs[4] if admin_mode else None
tab_global = tabs[5] if admin_mode else None


# ---------------------------
# Feed tab (portal-like)
# ---------------------------
with tab_feed:
    df_scored: pd.DataFrame = st.session_state.get("df_scored", pd.DataFrame())
    topk_cat_df: pd.DataFrame = st.session_state.get("topk_cat_df", pd.DataFrame())
    search_q = (st.session_state.get("search_query") or "").strip().lower()

    if st.session_state.get("data_source") == "demo":
        st.info("현재 **데모 데이터**로 실행 중입니다. (운영자 모드에서 실제 데이터로 교체 가능)")

    if df_scored.empty:
        st.warning("데이터가 없습니다. (운영자 모드 → 데이터 탭에서 넣을 수 있어요)")
        st.stop()

    # Category stats for menu
    cat_stats = (
        df_scored.groupby("category", as_index=False)
        .agg(items=("url", "count"), total_score=("engagement_score", "sum"))
        .sort_values(["total_score", "items"], ascending=False)
    )
    categories = cat_stats["category"].tolist()
    if not categories:
        categories = ["전체"]

    # Onboarding: interest categories (user-friendly)
    if not st.session_state.get("interest_cats"):
        # preselect top 5 categories
        st.session_state["interest_cats"] = categories[:5]

    interest_cats = st.multiselect(
        "관심 카테고리(추천 피드)",
        options=categories,
        default=st.session_state.get("interest_cats", categories[:5]),
        help="선택한 카테고리 위주로 '실시간 베스트'를 보여줘요.",
    )
    st.session_state["interest_cats"] = interest_cats

    # Filter base
    df_view = df_scored.copy()
    if interest_cats:
        df_view = df_view[df_view["category"].isin(interest_cats)]

    if search_q:
        mask = (
            df_view["title"].astype(str).str.lower().str.contains(search_q, na=False)
            | df_view["url"].astype(str).str.lower().str.contains(search_q, na=False)
            | df_view["content"].astype(str).str.lower().str.contains(search_q, na=False)
        )
        df_view = df_view[mask]

    df_view = df_view.sort_values(["engagement_score", "visits", "avg_dwell_sec"], ascending=False)

    main_col, side_col = st.columns([2.25, 1], gap="large")

    # ---- Ads (native sponsored cards) ----
    ads_inv = load_ads(APP_DIR)
    ctx_keywords = compute_trending_keywords(df_view.head(50), top_k=12)
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
                        event="click",
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
                st.markdown(f"[🔗 스폰서 링크 열기]({ad.landing_url})")
        with c2:
            st.caption("※ 스폰서/광고")

    with main_col:
        st.subheader(t("realtime_best"))
        best = df_view.head(6).to_dict(orient="records")

        if not best:
            st.caption("조건에 맞는 콘텐츠가 없어요. 관심 카테고리를 늘리거나 검색을 지워보세요.")
        else:
            cols = st.columns(3, gap="small")
            for i, row in enumerate(best, start=1):
                with cols[(i - 1) % 3]:
                    source_title = (row.get("title") or "").strip() or row.get("url")
                    url = row.get("url", "")
                    cat = row.get("category", "전체")
                    content = (row.get("content") or "").strip()
                    cache: Dict[str, Dict[str, Any]] = st.session_state.get("summary_cache", {})
                    s = get_cached_summary(url, cache=cache)
                    display_title = (s.get("localized_title") or s.get("title") or source_title) if s else source_title
                    if teaser_mode == "ai" and s:
                        teaser = (s.get("hook") or s.get("one_liner") or "")
                    else:
                        teaser = snippet_from_content(content, 90)

                    emoji = emoji_for_category(cat)
                    thumb_style = gradient_for_seed(url)
                    chips_html = chips_to_html([f"{emoji} {cat}", "🔥 실시간"], max_items=2)

                    st.markdown(
                        f"""
<div class="sp-card">
  <div class="sp-row">
    <div class="sp-thumb" style="{thumb_style}">{html.escape(emoji)}</div>
    <div class="sp-meta">
      <div>
        <span class="rank-badge">TOP {i}</span>
        <span class="sp-kicker" style="margin-left:6px;">{html.escape(cat)}</span>
      </div>
      <div class="sp-title">{html.escape(display_title)}</div>
      <div class="sp-snippet">{html.escape(teaser or '눌러서 3초 요약 보기')}</div>
      <div class="sp-chips">{chips_html}</div>
    </div>
  </div>
</div>
""",
                        unsafe_allow_html=True,
                    )

                    if show_metrics:
                        st.caption(f"방문 {float(row.get('visits', 0)):.0f} · 체류 {float(row.get('avg_dwell_min', 0)):.2f}분")

                    c1, c2 = st.columns([1, 1])
                    with c1:
                        if st.button(t("btn_view"), key=f"best_open_{i}"):
                            open_item(url)
                    with c2:
                        if s and st.button(t("btn_save"), key=f"best_save_{i}"):
                            add_to_selection(s)
                            st.toast("저장됨(선택 목록)")

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

        # Category list section
        st.subheader(t("category_top"))
        selected_cat = st.selectbox("카테고리", options=categories, index=0)
        cat_items = topk_cat_df[topk_cat_df["category"] == selected_cat].copy()
        cat_items = cat_items.sort_values(["engagement_score", "visits", "avg_dwell_sec"], ascending=False).head(10)

        if cat_items.empty:
            st.caption("이 카테고리에 표시할 콘텐츠가 없습니다.")
        else:
            inline_ad = None
            if show_ads:
                picked = select_ads(
                    ads_inv,
                    context_categories=[selected_cat, "전체"],
                    context_keywords=ctx_keywords,
                    n=1,
                    seed=11,
                )
                inline_ad = picked[0] if picked else None

            for rank, row in enumerate(cat_items.to_dict(orient="records"), start=1):
                # insert a native sponsored card around the middle
                if show_ads and inline_ad is not None and rank == 4:
                    render_ad(inline_ad, placement="inline_category", content_category=selected_cat)

                source_title = (row.get("title") or "").strip() or row.get("url")
                url = row.get("url", "")
                content = (row.get("content") or "").strip()
                cache: Dict[str, Dict[str, Any]] = st.session_state.get("summary_cache", {})
                s = get_cached_summary(url, cache=cache)
                display_title = (s.get("localized_title") or s.get("title") or source_title) if s else source_title
                if teaser_mode == "ai" and s:
                    teaser = (s.get("hook") or s.get("one_liner") or "")
                else:
                    teaser = snippet_from_content(content, 120)

                emoji = emoji_for_category(selected_cat)
                thumb_style = gradient_for_seed(url)
                chips_html = chips_to_html([f"{emoji} {selected_cat}", f"TOP {rank}"], max_items=2)

                st.markdown(
                    f"""
<div class="sp-card">
  <div class="sp-row">
    <div class="sp-thumb" style="{thumb_style}">{html.escape(emoji)}</div>
    <div class="sp-meta">
      <div class="sp-kicker">{rank}. {html.escape(selected_cat)}</div>
      <div class="sp-title">{html.escape(display_title)}</div>
      <div class="sp-snippet">{html.escape(teaser or '미리보기 없음 · 눌러서 3초 요약')}</div>
      <div class="sp-chips">{chips_html}</div>
    </div>
  </div>
</div>
""",
                    unsafe_allow_html=True,
                )

                if show_metrics:
                    st.caption(f"방문 {float(row.get('visits', 0)):.0f} · 체류 {float(row.get('avg_dwell_min', 0)):.2f}분")

                if st.button(t("btn_open"), key=f"cat_open_{selected_cat}_{rank}"):
                    open_item(url)

    with side_col:
        if show_ads:
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

        st.subheader(t("hot"))
        hot = df_view.head(10).to_dict(orient="records")
        for i, row in enumerate(hot, start=1):
            source_title = (row.get("title") or "").strip() or row.get("url")
            url = row.get("url", "")
            cache: Dict[str, Dict[str, Any]] = st.session_state.get("summary_cache", {})
            s = get_cached_summary(url, cache=cache)
            display_title = (s.get("localized_title") or s.get("title") or source_title) if s else source_title
            if st.button(f"{i}. {display_title}", key=f"hot_{i}"):
                open_item(url)

        st.divider()
        st.subheader(t("keywords"))
        kw = compute_trending_keywords(df_view.head(50), top_k=12)
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

        row = get_row_by_url(selected_url) or {"url": selected_url, "title": selected_url, "category": "전체"}
        source_title = (row.get("title") or "").strip() or selected_url
        cat = row.get("category", "전체")

        cache: Dict[str, Dict[str, Any]] = st.session_state.get("summary_cache", {})
        current_lang = current_summary_language()
        current_age = st.session_state.get("age_group", "general")
        cache_key = make_cache_key(selected_url, current_lang, current_age)
        existing = get_cached_summary(selected_url, language=current_lang, age_group=current_age, cache=cache)

        display_title = (existing.get("localized_title") or existing.get("title") or source_title) if existing else source_title

        st.markdown(f"## {emoji_for_category(cat)} {display_title}")
        st.caption(
            f"{cat} ? visits {float(row.get('visits', 0)):.0f} ? dwell {float(row.get('avg_dwell_min', 0)):.2f}m ? "
            f"score {float(row.get('engagement_score', 0)):.3f} ? [source]({selected_url})"
        )
        if source_title and source_title != display_title:
            st.caption(f"source title: {source_title}")

        content_from_csv = (row.get("content", "") or "").strip()
        if content_from_csv:
            with st.expander("원문 일부 보기", expanded=False):
                st.write(content_from_csv[:2500] + ("…" if len(content_from_csv) > 2500 else ""))
        else:
            st.caption("원문이 CSV에 없어요. 요약 생성 시 URL에서 가져옵니다.")

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
                if visits_v <= 0 and dwell_s <= 0 and score_v is None:
                    why = "?? ??? ???? ?? ?? ?? ?? ????? ???? ?? ?????."
                else:
                    why = (
                        f"?? {visits_v:.0f}?? ?? ?? {dwell_s:.1f}?? ?? ??? ??? ?????. "
                        f"??? ?? {float(score_v or 0):.3f}? ?? ?? ?? ???? ?? ??? ????."
                    )
            st.markdown("**Why trending**")
            st.write(why)

            discussion = (s.get("discussion_prompt") or "").strip()
            if not discussion:
                discussion = "???? ???? ? ?? ??? ? ??? ?????"
            st.markdown("**Discussion prompt**")
            st.write(discussion)

            rec_base = df_scored.sort_values(
                ["engagement_score", "visits", "avg_dwell_sec"], ascending=False
            ).copy()
            rec_base = rec_base[rec_base["url"] != selected_url].drop_duplicates(subset=["url"], keep="first")

            same_cat = rec_base[rec_base["category"] == cat]
            others = rec_base[rec_base["category"] != cat]
            people_df = pd.concat([same_cat, others], ignore_index=True).head(5)

            st.markdown("**People also viewed**")
            if not people_df.empty:
                for i, rec in enumerate(people_df.to_dict(orient="records"), start=1):
                    rec_url = rec.get("url", "")
                    rec_title = (rec.get("title") or rec_url).strip()
                    if st.button(f"{i}. {rec_title}", key=f"pav_open::{cache_key}::{i}"):
                        open_item(rec_url)
            else:
                st.caption("?? ??? ????.")

            interest_set = set(st.session_state.get("interest_cats", []) or [])
            top_interest = rec_base[rec_base["category"].isin(interest_set)] if interest_set else rec_base
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
                for i, rec in enumerate(next_df.to_dict(orient="records"), start=1):
                    rec_url = rec.get("url", "")
                    rec_title = (rec.get("title") or rec_url).strip()
                    if st.button(f"{i}. {rec_title}", key=f"next_open::{cache_key}::{i}"):
                        open_item(rec_url)
            else:
                st.caption("?? ??? ????.")

            full = (s.get("summary") or "").strip()
            if full:
                with st.expander("Summary", expanded=False):
                    st.write(full)
            tags = (s.get("tags") or [])
            if tags:
                st.caption("#" + " #".join([str(x) for x in tags[:8]]))

        def _build_summary() -> Optional[Dict[str, Any]]:
            """Fetch content (if needed) and build a summary. Returns summary dict or None."""
            try:
                ai = ensure_ai()
            except Exception as e:
                st.error(str(e))
                return None

            metrics = {"visits": float(row.get("visits", 0)), "avg_dwell_sec": float(row.get("avg_dwell_sec", 0))}
            # Prefer CSV content; otherwise fetch. If fetch fails, fall back to title/snippet.
            with st.spinner("원문 준비 중..."):
                page_title = source_title or selected_url
                text = content_from_csv
                if not text:
                    try:
                        # Skip fetch for non-http URLs
                        if re.match(r"^https?://", selected_url, flags=re.I):
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
        if existing:
            st.success("??? ???? ???")
            _render_summary_v2(existing)
        else:
            if not api_ready:
                st.info("OPENAI_API_KEY? ?? ?? ???? ??? ?????. AI ?? ??? ???????.")
                fallback_base = content_from_csv or source_title
                fallback = {
                    "url": selected_url,
                    "title": source_title,
                    "localized_title": source_title,
                    "hook": snippet_from_content(fallback_base, 80).replace("?", "."),
                    "one_liner": snippet_from_content(fallback_base, 120),
                    "key_points": [
                        snippet_from_content(fallback_base, 70),
                        "?? ???? ????? ??? ?????.",
                        "???? ?? ?? ????? ?????.",
                    ],
                    "why_trending": "",
                    "discussion_prompt": "A? B ? ??? ? ?????: ?? ? vs ?? ???",
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
                    set_cached_summary(selected_url, summary, language=current_lang, age_group=current_age, cache=cache)
                    st.session_state["summary_cache"] = cache
                    st.rerun()

            st.warning("?? ??? ????. ?? ???? ??? ? ???.")
            if st.button("3? ?? ???", type="primary", disabled=not api_ready, key=f"dlg_make_summary::{cache_key}"):
                st.session_state[did_flag] = True
                summary = _build_summary()
                if summary:
                    set_cached_summary(selected_url, summary, language=current_lang, age_group=current_age, cache=cache)
                    st.session_state["summary_cache"] = cache
                    st.success("?? ?? ??")
                    st.rerun()

        # 9) Actions area
        cache = st.session_state.get("summary_cache", {})
        s = get_cached_summary(selected_url, language=current_lang, age_group=current_age, cache=cache)
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
                st.download_button(
                    "Markdown 다운로드",
                    data=output_md,
                    file_name=f"staypick_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                    mime="text/markdown",
                )

    if st.session_state.get("open_dialog"):
        item_dialog()


# ---------------------------
# Make tab (batch generate from saved list)
# ---------------------------
with tab_make:
    st.subheader("✍️ 저장한 목록으로 콘텐츠 만들기")
    selected_list: List[Dict[str, Any]] = st.session_state.get("selected_summaries", [])
    st.caption("피드에서 마음에 드는 글을 **저장**하면, 여기서 묶어서 만들 수 있어요.")

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
            try:
                ai = ensure_ai()
            except Exception as e:
                st.error(str(e))
                st.stop()

            with st.spinner("새 콘텐츠 생성 중..."):
                try:
                    output_md = ai.generate_content(
                        summaries=selected_list,
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
            st.download_button(
                "Markdown 다운로드",
                data=output_md,
                file_name=f"staypick_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                mime="text/markdown",
            )


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
                metrics = {"visits": float(row.get("visits", 0)), "avg_dwell_sec": float(row.get("avg_dwell_sec", 0))}
                content_from_csv = (row.get("content", "") or "").strip()

                cached = get_cached_summary(
                    url,
                    language=current_summary_language(),
                    age_group=st.session_state.get("age_group", "general"),
                    cache=cache,
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
                            url,
                            summary,
                            language=current_summary_language(),
                            age_group=st.session_state.get("age_group", "general"),
                            cache=cache,
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



# ---------------------------
# Admin: Sponsor/Ads tab
# ---------------------------
if admin_mode and tab_sponsor is not None:
    with tab_sponsor:
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
                        "categories": ", ".join(a.categories),
                        "cpc(krw)": int((a.pricing or {}).get("cpc_krw", 0) or 0),
                        "active": a.active,
                    }
                    for a in ads_list
                ]
            )
            st.dataframe(inv_df, use_container_width=True)

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
        cpc = st.number_input("가정 CPC(원)", min_value=0, value=100, step=10)
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
                        pricing={"type": "CPC", "cpc_krw": int(cpc)},
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
                    a_cpc = st.number_input(
                        "CPC(원)",
                        min_value=0,
                        value=int((a.pricing or {}).get("cpc_krw", 0) or 0),
                        step=10,
                        key=f"ad_cpc_{a.id}",
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
                            pricing={"type": "CPC", "cpc_krw": int(a_cpc)},
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

            if st.button("📦 Programmatic SEO ZIP 생성", type="primary", key="btn_progseo"):
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
