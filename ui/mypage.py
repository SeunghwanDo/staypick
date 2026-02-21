from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

import streamlit as st


def render_mypage(ctx: Dict[str, Any]) -> None:
    _ = ctx.get("subscription_snapshot")

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
                current_sort = st.session_state.get("_mypage_sort", "recent")
                st.session_state["_mypage_sort"] = "oldest" if current_sort == "recent" else "recent"
        with c_m2:
            if st.button("기록 비우기", key="mypage_clear_history"):
                st.session_state["generated_history"] = []
                st.session_state["last_generated_content"] = {}
                st.rerun()
        items = list(gen_hist)
        sort_mode = st.session_state.get("_mypage_sort", "recent")
        if sort_mode == "recent":
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
