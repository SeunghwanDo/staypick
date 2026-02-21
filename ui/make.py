from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st


def render_make(ctx: Dict[str, Any]) -> None:
    t = ctx["t"]
    ensure_ai = ctx["ensure_ai"]
    get_row_by_url = ctx["get_row_by_url"]
    add_to_selection = ctx["add_to_selection"]
    build_demo_summary = ctx["build_demo_summary"]
    cached_fetch = ctx["cached_fetch"]
    get_cached_summary = ctx["get_cached_summary"]
    set_cached_summary = ctx["set_cached_summary"]
    current_summary_language = ctx["current_summary_language"]
    subscription_snapshot = ctx["subscription_snapshot"]
    subscription_entitlements = ctx["subscription_entitlements"]
    ai_usage_left = ctx["ai_usage_left"]
    consume_ai_credit = ctx["consume_ai_credit"]
    OpenAIService = ctx["OpenAIService"]
    api_key = ctx["api_key"]
    model = ctx["model"]
    embedding_model = ctx["embedding_model"]

    if st.session_state.get("_jump_to_make"):
        st.info("만들기 탭으로 이동했습니다. 저장한 항목으로 바로 재생산을 시작하세요.")
        st.session_state["_jump_to_make"] = False

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
