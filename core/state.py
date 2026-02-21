from __future__ import annotations

import random
import time
from typing import Dict

import pandas as pd
import streamlit as st

from core.constants import DEFAULT_YT_QUERY_GROUPS
from core.data import _load_youtube_snapshot, _save_youtube_snapshot, load_youtube_df, refresh_scores
from core.subscription import _load_subscription_state


def _refresh_youtube_cache() -> None:
    if "df_raw" not in st.session_state:
        return
    ttl_min = min(max(int(st.session_state.get("yt_cache_ttl_min", 15) or 15), 10), 30)
    bucket = int(time.time() // (ttl_min * 60))
    prev_bucket = st.session_state.get("_yt_bucket")
    if st.session_state.get("data_source") == "youtube" and prev_bucket != bucket and not st.session_state.get("_yt_reload_requested"):
        try:
            st.session_state["df_raw"] = load_youtube_df(selected_category=st.session_state.get("feed_category", "trend"))
            _save_youtube_snapshot(st.session_state["df_raw"])
            st.session_state["youtube_error"] = ""
            refresh_scores()
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
        refresh_scores()


def init_state() -> None:
    if st.session_state.get("_init_done"):
        _refresh_youtube_cache()
        return
    st.session_state["_init_done"] = True

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
    _refresh_youtube_cache()
