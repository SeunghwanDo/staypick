from __future__ import annotations

from typing import Any, Dict

import streamlit as st
import streamlit.components.v1 as components


def render_landing(ctx: Dict[str, Any]) -> None:
    _load_landing_html = ctx["_load_landing_html"]
    LANDING_PAGE_PATH = ctx["LANDING_PAGE_PATH"]

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
