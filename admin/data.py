from __future__ import annotations

from typing import Any, Dict

import pandas as pd
import streamlit as st


def render_admin_data(ctx: Dict[str, Any]) -> None:
    load_metrics_csv = ctx["load_metrics_csv"]
    load_demo_df = ctx["load_demo_df"]
    refresh_scores = ctx["refresh_scores"]

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
