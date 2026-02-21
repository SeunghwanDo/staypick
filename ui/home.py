from __future__ import annotations

from typing import Optional

import streamlit as st


def render_home() -> Optional[str]:
    st.markdown(
        """
<div class="home-wrap">
  <section class="home-hero">
    <div class="home-hero-card">
      <span class="home-pill">콘텐츠 재생산 스튜디오</span>
      <div class="home-title">트렌드를 내 콘텐츠로 재생산하는 가장 빠른 방법, StayPick</div>
      <p class="home-sub">요약 · 후킹 · 포맷 변환(블로그/뉴스레터/X 스레드/카루셀)까지 한 번에.</p>
      <div class="home-format">
        <span class="home-tag">블로그</span>
        <span class="home-tag">뉴스레터</span>
        <span class="home-tag">X 스레드</span>
        <span class="home-tag">카루셀</span>
        <span class="home-tag">스크립트</span>
      </div>
      <div class="home-note">발견 → 분석 → 재생산 → 저장 흐름으로 한 번에 정리됩니다.</div>
    </div>
    <div class="home-hero-card">
      <div class="home-step-title">재생산 플로우 미리보기</div>
      <p class="home-step-desc">피드에서 트렌드를 고르고, 3초 요약과 핵심 포인트를 확인한 뒤 포맷별로 즉시 생성합니다.</p>
      <div class="home-flow" style="margin-top:12px;">
        <div class="home-step">
          <div class="home-step-title">1) 트렌드 수집</div>
          <p class="home-step-desc">피드에서 지금 뜨는 소재를 빠르게 모읍니다.</p>
        </div>
        <div class="home-step">
          <div class="home-step-title">2) 3초 요약</div>
          <p class="home-step-desc">후킹 포인트와 핵심만 뽑아 재료를 만듭니다.</p>
        </div>
        <div class="home-step">
          <div class="home-step-title">3) 포맷별 생성</div>
          <p class="home-step-desc">블로그/뉴스레터/X/카루셀로 즉시 변환.</p>
        </div>
        <div class="home-step">
          <div class="home-step-title">4) 저장/히스토리</div>
          <p class="home-step-desc">마이페이지에 결과를 누적하고 재활용.</p>
        </div>
      </div>
    </div>
  </section>
</div>
""",
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1.1, 1.0, 3.4])
    intent: Optional[str] = None
    with c1:
        if st.button("지금 재생산 시작하기", type="primary", use_container_width=True, key="home_cta_make"):
            intent = "make"
    with c2:
        if st.button("데모 보기", use_container_width=True, key="home_cta_demo"):
            intent = "feed"
    with c3:
        st.caption("CTA 클릭 시 App 화면으로 이동하며, 선택한 탭(만들기/피드)이 바로 열립니다.")

    return intent
