from __future__ import annotations

import html
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st

from core.urls import is_youtube_url
from ui.utils import chips_to_html, emoji_for_category, gradient_for_seed


def render_feed(ctx: Dict[str, Any]) -> None:
    t = ctx["t"]
    admin_mode = ctx["admin_mode"]
    FEED_CATEGORY_ORDER = ctx["FEED_CATEGORY_ORDER"]
    FEED_CATEGORY_EMOJI = ctx["FEED_CATEGORY_EMOJI"]
    _youtube_query_groups = ctx["_youtube_query_groups"]
    load_youtube_df = ctx["load_youtube_df"]
    _save_youtube_snapshot = ctx["_save_youtube_snapshot"]
    _load_youtube_snapshot = ctx["_load_youtube_snapshot"]
    refresh_scores = ctx["refresh_scores"]
    undo_not_interested = ctx["undo_not_interested"]
    _log_content_impression_once = ctx["_log_content_impression_once"]
    _today_watch_seconds = ctx["_today_watch_seconds"]
    _watch_streak_count = ctx["_watch_streak_count"]
    open_item = ctx["open_item"]
    _log_content_event = ctx["_log_content_event"]
    _log_reco_event = ctx["_log_reco_event"]
    _log_reco_click = ctx["_log_reco_click"]
    _relative_time_text = ctx["_relative_time_text"]
    _views_text = ctx["_views_text"]
    _category_click_boost = ctx["_category_click_boost"]
    _watch_dwell_boost = ctx["_watch_dwell_boost"]
    _compute_quality_score = ctx["_compute_quality_score"]
    _resolve_rank_variant = ctx["_resolve_rank_variant"]
    _reco_click_boost = ctx["_reco_click_boost"]
    _is_shorts_item = ctx["_is_shorts_item"]
    compute_trending_keywords = ctx["compute_trending_keywords"]
    build_news_row = ctx["build_news_row"]
    build_yt_row = ctx["build_yt_row"]
    build_article_header = ctx["build_article_header"]
    build_toc = ctx["build_toc"]
    paragraphize_fulltext = ctx["paragraphize_fulltext"]
    get_row_by_url = ctx["get_row_by_url"]
    get_cached_summary = ctx["get_cached_summary"]
    set_cached_summary = ctx["set_cached_summary"]
    current_summary_language = ctx["current_summary_language"]
    build_demo_summary = ctx["build_demo_summary"]
    cached_fetch = ctx["cached_fetch"]
    add_to_selection = ctx["add_to_selection"]
    make_cache_key = ctx["make_cache_key"]
    ensure_ai = ctx["ensure_ai"]
    ai_usage_left = ctx["ai_usage_left"]
    consume_ai_credit = ctx["consume_ai_credit"]
    subscription_snapshot = ctx["subscription_snapshot"]
    subscription_entitlements = ctx["subscription_entitlements"]
    select_ads = ctx["select_ads"]
    load_ads = ctx["load_ads"]
    log_event = ctx["log_event"]
    Ad = ctx["Ad"]
    APP_DIR = ctx["APP_DIR"]
    api_key = ctx["api_key"]
    model = ctx["model"]
    embedding_model = ctx["embedding_model"]
    teaser_mode = ctx["teaser_mode"]
    snippet_from_content = ctx["snippet_from_content"]
    show_metrics = ctx["show_metrics"]
    show_ads = ctx["show_ads"]
    persona = ctx["persona"]
    mark_not_interested = ctx["mark_not_interested"]
    _finalize_current_view = ctx["_finalize_current_view"]

    if st.session_state.get("_jump_to_feed"):
        st.info("피드로 이동했습니다. 지금 뜨는 트렌드를 확인하세요.")
        st.session_state["_jump_to_feed"] = False

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
        st.caption("지금 뜨는 쇼츠를 한 번에 훑고, 요약/재생산으로 이어가세요.")
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

    main_col, side_col = st.columns([4.6, 1.4], gap="large")

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

    def render_sponsor(ad: Ad, placement: str, content_url: str = "", content_category: str = "") -> None:
        if (not show_ads) or (ad is None):
            return
        _log_impression_once(ad.id, placement, content_url, content_category)
        cat = (ad.categories[0] if (ad.categories or []) else "전체")
        emoji = emoji_for_category(cat)

        thumb_style = ""
        if getattr(ad, "image_url", ""):
            safe_url = html.escape(str(ad.image_url))
            thumb_style = f"background-image:url('{safe_url}'); background-size:cover; background-position:center;"
        else:
            thumb_style = gradient_for_seed(ad.id + "|" + placement)

        hook = (getattr(ad, "hook", "") or "").strip()
        if not hook:
            if (ad.keywords or []):
                hook = f"지금 뜨는 키워드: {ad.keywords[0]}"
            else:
                hook = "스폰서 추천"

        chips = [f"{emoji} {cat}"]
        for kw in (ad.keywords or [])[:2]:
            chips.append(f"#{kw}")
        chips_html = chips_to_html(chips, max_items=3)

        st.markdown(
            f"""
<div class="sp-card">
  <div class="sp-row">
    <div class="sp-thumb" style="{thumb_style}">{html.escape(emoji)}</div>
    <div class="sp-meta">
      <div class="small-muted">스폰서</div>
      <div class="sp-title">{html.escape(ad.title)}</div>
      <div class="sp-snippet">{html.escape(ad.description or '')}</div>
      <div class="sp-chips">{chips_html}</div>
    </div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns([1.1, 1])
        with c1:
            if st.button(f"{ad.cta}", key=f"ad_click_{placement}_{ad.id}_{content_url}"):
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
                st.markdown(f"[스폰서 링크 열기]({tracked_link or ad.landing_url})")
        with c2:
            st.caption("광고")

    def _build_card_payload(row: Dict[str, Any]) -> Dict[str, Any]:
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
        ).strip(" · ")

        return {
            "url": url,
            "cat": cat,
            "display_title": display_title,
            "teaser": teaser or "내용 보기",
            "thumb_block": thumb_block,
            "meta": yt_meta,
            "summary": s,
        }

    def render_hero(current_cat: str) -> str:
        st.markdown(
            """
<div class="sp-hero">
  <h1>트렌드를 내 콘텐츠로 재생산</h1>
  <p>검색하고, 카테고리를 고르고, 바로 Top Pick에서 시작하세요.</p>
</div>
""",
            unsafe_allow_html=True,
        )
        st.text_input(
            "검색",
            value=st.session_state.get("search_query", ""),
            placeholder="키워드, 제목, 채널을 검색하세요",
            key="search_query",
        )
        labels = feed_options
        current_label = current_cat if current_cat in labels else (labels[0] if labels else "trend")
        if hasattr(st, "segmented_control"):
            choice = st.segmented_control(
                "Category",
                options=labels,
                default=current_label,
                label_visibility="collapsed",
            )
        else:
            choice = st.radio(
                "Category",
                options=labels,
                index=labels.index(current_label),
                horizontal=True,
                label_visibility="collapsed",
            )
        return choice or current_label

    def render_top_pick(row: Dict[str, Any]) -> None:
        st.subheader("Top Pick")
        payload = _build_card_payload(row)
        def _render_card(open_key: str, save_key: str, large: bool = False, primary: bool = False) -> None:
            size_class = "large" if large else ""
            st.markdown(
                f"""
<div class="sp-card-item {size_class}">
  <div class="sp-card-body">
    <div class="sp-card-thumb">{payload["thumb_block"]}</div>
    <div class="sp-card-content">
      <div class="sp-card-title {size_class}">{html.escape(payload["display_title"])}</div>
      <div class="sp-card-meta">{html.escape(payload["meta"])}</div>
      <div class="sp-card-snippet">{html.escape(payload["teaser"])}</div>
    </div>
  </div>
</div>
""",
                unsafe_allow_html=True,
            )
            b1, b2 = st.columns([1, 1])
            with b1:
                if st.button("상세 보기", key=open_key, type=("primary" if primary else "secondary")):
                    open_item(payload["url"], source="top_pick")
            with b2:
                if payload["summary"] and st.button("저장", key=save_key):
                    add_to_selection(payload["summary"])
                    st.toast("저장되었습니다")

        _render_card(
            open_key=f"top_pick_open_{abs(hash(payload['url'])) % 100000}",
            save_key=f"top_pick_save_{abs(hash(payload['url'])) % 100000}",
            large=True,
            primary=True,
        )

    def render_grid(rows: List[Dict[str, Any]]) -> None:
        st.subheader("추천 콘텐츠")
        cols = st.columns(2, gap="medium")
        for idx, row in enumerate(rows, start=1):
            payload = _build_card_payload(row)
            _log_content_impression_once(str(payload["url"] or "").strip(), str(payload["cat"] or "전체").strip() or "전체", "grid", variant=str(st.session_state.get("rank_variant", "control") or "control"))
            with cols[(idx - 1) % 2]:
                st.markdown(
                    f"""
<div class="sp-card-item">
  <div class="sp-card-body">
    <div class="sp-card-thumb">{payload["thumb_block"]}</div>
    <div class="sp-card-content">
      <div class="sp-card-title">{html.escape(payload["display_title"])}</div>
      <div class="sp-card-meta">{html.escape(payload["meta"])}</div>
      <div class="sp-card-snippet">{html.escape(payload["teaser"])}</div>
    </div>
  </div>
</div>
""",
                    unsafe_allow_html=True,
                )
                b1, b2 = st.columns([1, 1])
                with b1:
                    if st.button("열기", key=f"grid_open_{idx}_{abs(hash(payload['url'])) % 100000}"):
                        open_item(payload["url"], source="grid")
                with b2:
                    if payload["summary"] and st.button("저장", key=f"grid_save_{idx}_{abs(hash(payload['url'])) % 100000}"):
                        add_to_selection(payload["summary"])
                        st.toast("저장되었습니다")

    def render_longform(rows: List[Dict[str, Any]]) -> None:
        st.subheader("심층 분석")
        if not rows:
            st.caption("조건에 맞는 콘텐츠가 없습니다. 검색어나 카테고리를 바꿔보세요.")
            return
        for i, row in enumerate(rows, start=1):
            payload = _build_card_payload(row)
            _log_content_impression_once(str(payload["url"] or "").strip(), str(payload["cat"] or "전체").strip() or "전체", "longform", variant=str(st.session_state.get("rank_variant", "control") or "control"))
            st.markdown(
                f"""
<div class="sp-card-item">
  <div class="sp-card-body">
    <div class="sp-card-thumb">{payload["thumb_block"]}</div>
    <div class="sp-card-content">
      <div class="sp-card-title">{html.escape(payload["display_title"])}</div>
      <div class="sp-card-meta">{html.escape(payload["meta"])}</div>
      <div class="sp-card-snippet">{html.escape(payload["teaser"])}</div>
    </div>
  </div>
</div>
""",
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
                if st.button("열기", key=f"long_open_{i}_{abs(hash(payload['url'])) % 100000}"):
                    open_item(payload["url"], source="longform")
            with c2:
                if payload["summary"] and st.button("저장", key=f"long_save_{i}_{abs(hash(payload['url'])) % 100000}"):
                    add_to_selection(payload["summary"])
                    st.toast("저장되었습니다")

    def render_filter_panel() -> None:
        with st.expander("필터", expanded=True):
            st.caption("검색어")
            if search_q:
                st.write(f"`{search_q}`")
            else:
                st.write("-")

            st.caption("트렌딩 키워드")
            kw = compute_trending_keywords(df_overall.head(50), top_k=12)
            if kw:
                for w in kw:
                    if st.button(f"#{w}", key=f"kw_{w}"):
                        st.session_state["search_query"] = w
                        st.rerun()
            else:
                st.caption("키워드가 충분하지 않습니다.")

            st.divider()
            st.caption("저장됨")
            selected_list: List[Dict[str, Any]] = st.session_state.get("selected_summaries", [])
            st.caption(f"{len(selected_list)}개 저장됨")
            if selected_list:
                if st.button("만들기 탭으로 이동"):
                    st.session_state["_jump_to_make"] = True
                    st.rerun()

    with main_col:
        selected_cat = render_hero(feed_cat)
        if selected_cat != feed_cat:
            feed_cat = selected_cat

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

        c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.2, 1.2], gap="small")
        with c1:
            st.toggle("자동 다음재생", key="autoplay_next")
        with c2:
            delay_opt = st.selectbox("딜레이", options=[3, 5, 8], index=[3, 5, 8].index(int(st.session_state.get("autoplay_delay_sec", 3))), key="autoplay_delay_selector")
            st.session_state["autoplay_delay_sec"] = int(delay_opt)
        with c3:
            if st.button("관심없음 취소", use_container_width=True, key="undo_not_interested_btn"):
                if undo_not_interested():
                    st.rerun()
        with c4:
            if st.button("기록 비우기", use_container_width=True, key="clear_watch_history_toolbar_btn"):
                st.session_state["watch_history"] = []
                st.session_state["watch_dwell_by_url"] = {}
                st.session_state["watch_dwell_by_cat"] = {}
                st.rerun()

        items = df_view.to_dict(orient="records")
        if not items:
            st.warning("조건에 맞는 콘텐츠가 없습니다.")
        else:
            top_pick = items[0]
            grid_items = items[1:9]
            render_top_pick(top_pick)

            if grid_items:
                render_grid(grid_items[:6])
                if show_ads:
                    sponsor_banner = select_ads(
                        ads_inv,
                        context_categories=ctx_categories,
                        context_keywords=ctx_keywords,
                        n=1,
                        seed=7,
                    )
                    if sponsor_banner:
                        st.caption("스폰서")
                        render_sponsor(sponsor_banner[0], placement="grid")
                render_grid(grid_items[6:])

        long_items = [r for r in items if not _is_shorts_item(r)]
        long_show = int(st.session_state.get("long_show_n", 3) or 3)
        render_longform(long_items[:long_show])
        if len(long_items) > long_show:
            if st.button("심층 분석 더보기"):
                st.session_state["long_show_n"] = long_show + 3
                st.rerun()

    with side_col:
        render_filter_panel()

        st.divider()
        st.subheader("HOT 랭킹")
        hot = df_overall.head(10).to_dict(orient="records")
        for i, row in enumerate(hot, start=1):
            source_title = (row.get("title") or "").strip() or row.get("url")
            url = row.get("url", "")
            cat_hot = str(row.get("category", "") or "").strip() or "전체"
            cache: Dict[str, Dict[str, Any]] = st.session_state.get("summary_cache", {})
            s = get_cached_summary(cache, url)
            display_title = (s.get("localized_title") or s.get("title") or source_title) if s else source_title
            meta = " ? ".join(
                [
                    str(row.get("channel_title", "") or "").strip(),
                    _views_text(row.get("visits", 0)),
                ]
            ).strip(" ? ")
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

        with st.expander("쇼츠", expanded=False):
            st.caption("지금 뜨는 쇼츠를 한 번에 훑고, 요약/재생산으로 이어가세요.")
            shorts_items = [r for r in df_overall.head(80).to_dict(orient="records") if _is_shorts_item(r)]
            if shorts_items:
                short_show = int(st.session_state.get("shorts_show_n", 12) or 12)
                short_cols = st.columns(2, gap="small")
                for i, row in enumerate(shorts_items[:short_show], start=1):
                    s_url = str(row.get("url", "") or "").strip()
                    s_title = str(row.get("title", "") or s_url).strip()
                    s_thumb = str(row.get("thumbnail_url", "") or "").strip()
                    s_cat = str(row.get("category", "") or "").strip() or "전체"
                    s_channel = str(row.get("channel_title", "") or "").strip()
                    _log_content_impression_once(s_url, s_cat, "shorts", variant=str(st.session_state.get("rank_variant", "control") or "control"))
                    with short_cols[(i - 1) % 2]:
                        if s_thumb:
                            thumb_block = f"<img class='short-thumb-img' src='{html.escape(s_thumb)}' alt='short thumbnail'/>"
                        else:
                            thumb_block = (
                                f"<div class='sp-thumb' style='{gradient_for_seed(s_url)}; width:100%; height:100%; border-radius:0;'>"
                                f"{html.escape(emoji_for_category(s_cat))}</div>"
                            )
                        short_title = (s_title[:52] + "...") if len(s_title) > 52 else s_title
                        short_meta = " ? ".join([x for x in [s_channel, _views_text(row.get("visits", 0))] if x]).strip(" ? ")
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
                        b1, b2 = st.columns(2, gap="small")
                        with b1:
                            if st.button("요약", use_container_width=True, key=f"short_summary_{abs(hash(s_url)) % 100000}_{i}"):
                                open_item(s_url, source="shorts")
                        with b2:
                            if st.button("공유", use_container_width=True, key=f"short_share_{abs(hash(s_url)) % 100000}_{i}"):
                                st.code(s_url)
                                st.caption("링크를 복사해 공유하세요.")
                if len(shorts_items) > short_show:
                    if st.button("쇼츠 더보기", key="btn_more_shorts"):
                        st.session_state["shorts_show_n"] = short_show + 6
                        st.rerun()
            else:
                st.caption("쇼츠가 없습니다.")

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
        auto_summarize = bool(st.session_state.get("auto_summarize", True))
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
            if (not text) and (not is_youtube_url(selected_url)):
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
                discussion = "이 주제에서 가장 뜨거운 논쟁 포인트는 무엇일까요?"
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
                st.caption("볼만한 콘텐츠가 없습니다.")

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
                st.caption("볼만한 콘텐츠가 없습니다.")

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
            if is_youtube_url(selected_url):
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
