from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from core.constants import APP_DIR, UPSELL_EVENTS_PATH


def render_admin_insights(ctx: Dict[str, Any]) -> None:
    ensure_ai = ctx["ensure_ai"]
    cached_fetch = ctx["cached_fetch"]
    cluster_summaries = ctx["cluster_summaries"]
    get_cached_summary = ctx["get_cached_summary"]
    set_cached_summary = ctx["set_cached_summary"]
    current_summary_language = ctx["current_summary_language"]
    build_demo_summary = ctx["build_demo_summary"]
    _load_reco_events_df = ctx["_load_reco_events_df"]
    _load_upsell_events_df = ctx["_load_upsell_events_df"]
    _load_content_events_df = ctx["_load_content_events_df"]

    st.subheader("🔎 Top 콘텐츠 요약 & 트렌드 클러스터(운영자)")

    top_df = st.session_state.get("top_df", pd.DataFrame())
    if top_df.empty:
        st.warning("데이터가 없습니다. 데이터 탭에서 먼저 넣어주세요.")
        st.stop()

    st.write("스코어 기준 Top 콘텐츠:")
    st.dataframe(top_df[["category", "title", "url", "visits", "avg_dwell_min", "engagement_score"]], use_container_width=True)

    if st.button("Top 콘텐츠 일괄 요약 생성", type="primary"):
        demo_mode_local = bool(st.session_state.get("demo_mode", False))
        ai = None
        if not demo_mode_local:
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

            if demo_mode_local:
                page_title = title_hint
                text = content_from_csv or title_hint
                summary = build_demo_summary(
                    url=url,
                    title=page_title,
                    content=text,
                    metrics=metrics,
                )
                set_cached_summary(
                    cache,
                    url,
                    summary,
                    lang=current_summary_language(),
                    age=st.session_state.get("age_group", "general"),
                )
                summaries.append(summary)
            else:
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
            if demo_mode_local:
                st.info("데모 모드: 클러스터링은 생략합니다.")
                st.session_state["clusters"] = []
            else:
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
