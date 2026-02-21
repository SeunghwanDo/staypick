from __future__ import annotations

import html
from typing import Dict, List, Optional, Tuple

import streamlit as st


def render_app_shell(t, admin_mode: bool) -> Dict[str, "st.delta_generator.DeltaGenerator"]:
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
        st.write("")

    st.caption(t("header_caption"))

    # ---------------------------
    # Tabs (general users first)
    # ---------------------------
    jump_to_make = bool(st.session_state.get("_jump_to_make", False))
    jump_to_feed = bool(st.session_state.get("_jump_to_feed", False))

    base_tabs: List[Tuple[str, str]] = [
        ("feed", t("tab_feed")),
        ("guide", "활용법"),
        ("make", t("tab_make")),
        ("mypage", "마이페이지"),
        ("landing", "랜딩"),
    ]

    def _reorder_tabs(tabs: List[Tuple[str, str]], first_key: Optional[str]) -> List[Tuple[str, str]]:
        if not first_key:
            return tabs
        head = [t for t in tabs if t[0] == first_key]
        tail = [t for t in tabs if t[0] != first_key]
        return head + tail

    if jump_to_make:
        base_tabs = _reorder_tabs(base_tabs, "make")
    elif jump_to_feed:
        base_tabs = _reorder_tabs(base_tabs, "feed")

    all_tabs = list(base_tabs)
    if admin_mode:
        all_tabs += [
            ("data", t("tab_data")),
            ("insights", t("tab_insights")),
            ("sponsor", t("tab_sponsor")),
            ("global", t("tab_global")),
        ]

    tabs = st.tabs([label for _, label in all_tabs])
    tab_map = {key: tabs[i] for i, (key, _) in enumerate(all_tabs)}

    return tab_map
