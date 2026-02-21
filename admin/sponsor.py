from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from core.constants import APP_DIR, MONETIZATION_ASSUMPTIONS, MONETIZATION_PRICING
from core.subscription import subscription_snapshot


def render_admin_sponsor(ctx: Dict[str, Any]) -> None:
    ensure_ai = ctx["ensure_ai"]
    load_ads = ctx["load_ads"]
    save_ads = ctx["save_ads"]
    log_event = ctx["log_event"]
    Ad = ctx["Ad"]
    api_key = ctx["api_key"]
    model = ctx["model"]
    _load_upsell_events_df = ctx["_load_upsell_events_df"]

    sub_sponsor = subscription_snapshot()
    b2b_enabled = sub_sponsor.get("tier") == "pro"
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
    st.markdown("### 🧮 Monetization KPI (Auto)")
    profile_now = str(st.session_state.get("monetization_profile", "A") or "A").upper()
    assumption = MONETIZATION_ASSUMPTIONS.get(profile_now, MONETIZATION_ASSUMPTIONS["A"])
    default_paid_rate = float(assumption.get("paid_rate", 0.018) or 0.018)
    default_pro_share = float(assumption.get("pro_share", 0.25) or 0.25)
    k1, k2, k3 = st.columns(3)
    with k1:
        active_users_est = int(st.number_input("Estimated MAU", min_value=100, value=10000, step=100))
    with k2:
        period_days_est = int(st.number_input("Observed period days", min_value=1, value=30, step=1))
    with k3:
        paid_rate_input = float(
            st.number_input("Paid conversion rate (if no data)", min_value=0.0, max_value=1.0, value=default_paid_rate, step=0.001, format="%.3f")
        )
    pro_share_input = float(st.slider("Pro share among paid users", min_value=0.0, max_value=1.0, value=default_pro_share, step=0.01))
    st.caption(
        f"Profile default ({profile_now}) -> paid_rate {default_paid_rate*100:.2f}% · pro_share {default_pro_share*100:.1f}%"
    )
    pricing_now = MONETIZATION_PRICING.get(profile_now, MONETIZATION_PRICING["A"])
    st.caption(
        f"Pricing package ({profile_now}) -> Basic {int(pricing_now.get('basic', 4900)):,} / Pro {int(pricing_now.get('pro', 9900)):,} (monthly)"
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
            ad_by_id = {a.id: a for a in ads_list}
            if "affiliate_click" not in pivot.columns:
                pivot["affiliate_click"] = 0
            if "affiliate_lead" not in pivot.columns:
                pivot["affiliate_lead"] = 0
            if "affiliate_purchase" not in pivot.columns:
                pivot["affiliate_purchase"] = 0
            pivot["affiliate_conversion"] = pivot["affiliate_lead"] + pivot["affiliate_purchase"]
            pivot["pricing_type"] = pivot.apply(
                lambda r: str(((ad_by_id.get(str(r.get("ad_id", ""))).pricing or {}).get("type", "CPC") if ad_by_id.get(str(r.get("ad_id", ""))) else "CPC")).upper(),
                axis=1,
            )
            pivot["ad_rev_est_krw"] = pivot.apply(
                lambda r: (
                    float(r.get("click", 0))
                    * float((ad_by_id.get(str(r.get("ad_id", ""))).pricing or {}).get("cpc_krw", 0) or 0)
                    if str(r.get("pricing_type", "CPC")).upper() == "CPC"
                    else float(r.get("affiliate_conversion", 0))
                    * float((ad_by_id.get(str(r.get("ad_id", ""))).pricing or {}).get("cpa_krw", 0) or 0)
                )
                if ad_by_id.get(str(r.get("ad_id", "")))
                else 0.0,
                axis=1,
            )
            pivot["affiliate_rev_est_krw"] = pivot.apply(
                lambda r: float(r.get("affiliate_conversion", 0))
                * float((ad_by_id.get(str(r.get("ad_id", ""))).pricing or {}).get("cpa_krw", 0) or 0)
                if ad_by_id.get(str(r.get("ad_id", ""))) and str(r.get("pricing_type", "CPC")).upper() == "CPC"
                else 0.0,
                axis=1,
            )
            pivot["total_rev_est_krw"] = pivot["ad_rev_est_krw"] + pivot["affiliate_rev_est_krw"]
            pivot["CVR(%)"] = pivot.apply(
                lambda r: (float(r.get("affiliate_conversion", 0)) / float(r.get("affiliate_click", 0)) * 100.0)
                if float(r.get("affiliate_click", 0)) > 0
                else 0.0,
                axis=1,
            )
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Impressions", f"{int(pivot['impression'].sum()):,}")
            m2.metric("Clicks", f"{int(pivot['click'].sum()):,}")
            m3.metric("Affiliate Conv", f"{int(pivot['affiliate_conversion'].sum()):,}")
            m4.metric("Ad Rev Est (KRW)", f"{int(pivot['ad_rev_est_krw'].sum()):,}")
            m5.metric("Total Rev Est (KRW)", f"{int(pivot['total_rev_est_krw'].sum()):,}")

            upsell_df = _load_upsell_events_df()
            paid_rate_obs = 0.0
            pro_share_obs = 0.0
            if upsell_df is not None and not upsell_df.empty and "event" in upsell_df.columns:
                upsell_df = upsell_df.copy()
                upsell_df["ts"] = pd.to_datetime(upsell_df.get("ts", ""), errors="coerce")
                upsell_cutoff = datetime.now() - timedelta(days=int(period_days_est))
                upsell_df = upsell_df[upsell_df["ts"].isna() | (upsell_df["ts"] >= upsell_cutoff)]
                views_u = int((upsell_df["event"] == "upsell_view").sum())
                upgrades_u = int(upsell_df["event"].isin(["upgrade_applied_basic", "upgrade_applied_pro"]).sum())
                pro_up_u = int((upsell_df["event"] == "upgrade_applied_pro").sum())
                paid_rate_obs = (upgrades_u / views_u) if views_u > 0 else 0.0
                pro_share_obs = (pro_up_u / upgrades_u) if upgrades_u > 0 else 0.0

            paid_rate_used = paid_rate_obs if paid_rate_obs > 0 else paid_rate_input
            pro_share_used = pro_share_obs if pro_share_obs > 0 else pro_share_input
            basic_share_used = max(1.0 - pro_share_used, 0.0)
            monthly_factor = 30.0 / max(float(period_days_est), 1.0)
            mrr_ads_est = float(pivot["total_rev_est_krw"].sum()) * monthly_factor
            projected_paid_users = float(active_users_est) * float(paid_rate_used)
            mrr_sub_est = projected_paid_users * (
                basic_share_used * float(sub_sponsor.get("price_basic", 4900))
                + pro_share_used * float(sub_sponsor.get("price_pro", 9900))
            )
            total_mrr_est = mrr_sub_est + mrr_ads_est
            arpu_est = total_mrr_est / max(float(active_users_est), 1.0)

            st.caption(
                f"Profile {profile_now} · paid_rate={paid_rate_used*100:.2f}% · pro_share={pro_share_used*100:.1f}%"
            )
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Projected Paid Users", f"{int(projected_paid_users):,}")
            kpi2.metric("MRR Sub Est (KRW)", f"{int(mrr_sub_est):,}")
            kpi3.metric("MRR Ads Est (KRW)", f"{int(mrr_ads_est):,}")
            kpi4.metric("MRR Total Est (KRW)", f"{int(total_mrr_est):,}")
            st.caption(f"Projected ARPU (KRW/user/mo): {arpu_est:,.1f}")

            st.markdown("#### B2B report export")
            b2b_rows = []
            for _, r in pivot.iterrows():
                ad_id = str(r.get("ad_id", ""))
                ad = ad_by_id.get(ad_id)
                b2b_rows.append(
                    {
                        "ad_id": ad_id,
                        "brand": (ad.brand if ad else ""),
                        "pricing_type": str(((ad.pricing or {}).get("type", "CPC") if ad else "CPC")).upper(),
                        "impression": float(r.get("impression", 0) or 0),
                        "click": float(r.get("click", 0) or 0),
                        "affiliate_click": float(r.get("affiliate_click", 0) or 0),
                        "affiliate_lead": float(r.get("affiliate_lead", 0) or 0),
                        "affiliate_purchase": float(r.get("affiliate_purchase", 0) or 0),
                        "affiliate_conversion": float(r.get("affiliate_conversion", 0) or 0),
                        "ctr_pct": float(r.get("CTR(%)", 0) or 0),
                        "cvr_pct": float(r.get("CVR(%)", 0) or 0),
                        "ad_rev_est_krw": float(r.get("ad_rev_est_krw", 0) or 0),
                        "affiliate_rev_est_krw": float(r.get("affiliate_rev_est_krw", 0) or 0),
                        "total_rev_est_krw": float(r.get("total_rev_est_krw", 0) or 0),
                        "ecpm_krw": (
                            float(r.get("ad_rev_est_krw", 0) or 0) * 1000.0 / float(r.get("impression", 0) or 0)
                            if float(r.get("impression", 0) or 0) > 0
                            else 0.0
                        ),
                        "rpm_krw": (
                            float(r.get("total_rev_est_krw", 0) or 0) * 1000.0 / float(r.get("impression", 0) or 0)
                            if float(r.get("impression", 0) or 0) > 0
                            else 0.0
                        ),
                        "arpu_est_krw": float(r.get("total_rev_est_krw", 0) or 0) / max(float(active_users_est), 1.0),
                    }
                )
            b2b_df = pd.DataFrame(b2b_rows)
            st.download_button(
                "Download B2B CSV",
                data=b2b_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"staypick_b2b_monetization_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                disabled=not b2b_enabled,
            )

            # B2B-ready category performance view (ad/affiliate + content quality)
            if "content_category" in df_ev.columns:
                cat_pivot = (
                    df_ev.pivot_table(index="content_category", columns="event", values="ts", aggfunc="count", fill_value=0)
                    .reset_index()
                    .rename_axis(None, axis=1)
                )
                if "impression" not in cat_pivot.columns:
                    cat_pivot["impression"] = 0
                if "click" not in cat_pivot.columns:
                    cat_pivot["click"] = 0
                if "affiliate_click" not in cat_pivot.columns:
                    cat_pivot["affiliate_click"] = 0
                if "affiliate_lead" not in cat_pivot.columns:
                    cat_pivot["affiliate_lead"] = 0
                if "affiliate_purchase" not in cat_pivot.columns:
                    cat_pivot["affiliate_purchase"] = 0
                cat_pivot["affiliate_conversion"] = cat_pivot["affiliate_lead"] + cat_pivot["affiliate_purchase"]
                cat_pivot["CTR(%)"] = cat_pivot.apply(
                    lambda r: (float(r.get("click", 0)) / float(r.get("impression", 0)) * 100.0) if float(r.get("impression", 0)) > 0 else 0.0,
                    axis=1,
                )
                cat_pivot["CVR(%)"] = cat_pivot.apply(
                    lambda r: (float(r.get("affiliate_conversion", 0)) / float(r.get("affiliate_click", 0)) * 100.0)
                    if float(r.get("affiliate_click", 0)) > 0
                    else 0.0,
                    axis=1,
                )
                df_sc_local = st.session_state.get("df_scored", pd.DataFrame())
                if (
                    df_sc_local is not None
                    and not df_sc_local.empty
                    and "url" in df_sc_local.columns
                    and "engagement_score" in df_sc_local.columns
                ):
                    quality = (
                        df_sc_local.groupby("category", dropna=False)
                        .agg(
                            avg_engagement=("engagement_score", "mean"),
                            avg_dwell_sec=("avg_dwell_sec", "mean"),
                            avg_visits=("visits", "mean"),
                        )
                        .reset_index()
                        .rename(columns={"category": "content_category"})
                    )
                    cat_pivot = cat_pivot.merge(quality, on="content_category", how="left")
                st.markdown("#### Category performance (B2B)")
                st.dataframe(cat_pivot.sort_values(["CTR(%)", "impression"], ascending=False), use_container_width=True)
                st.download_button(
                    "Download Category CSV",
                    data=cat_pivot.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"staypick_b2b_category_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    disabled=not b2b_enabled,
                )
            if not b2b_enabled:
                st.info("B2B CSV export is available on Pro plan.")
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
                    "pricing_type": str((a.pricing or {}).get("type", "CPC") or "CPC"),
                    "categories": ", ".join(a.categories),
                    "cpc(krw)": int((a.pricing or {}).get("cpc_krw", 0) or 0),
                    "cpa(krw)": int((a.pricing or {}).get("cpa_krw", 0) or 0),
                    "active": a.active,
                }
                for a in ads_list
            ]
        )
        st.dataframe(inv_df, use_container_width=True)
        with st.expander("Affiliate conversion logger", expanded=False):
            ad_ids = [a.id for a in ads_list]
            sel_ad = st.selectbox("Ad ID", options=ad_ids, key="aff_log_ad")
            conv_evt = st.selectbox("Conversion type", options=["affiliate_lead", "affiliate_purchase"], key="aff_log_type")
            conv_n = st.number_input("Count", min_value=1, value=1, step=1, key="aff_log_count")
            if st.button("Log conversion", key="aff_log_btn"):
                for _ in range(int(conv_n)):
                    log_event(
                        APP_DIR,
                        event=conv_evt,
                        ad_id=sel_ad,
                        placement="affiliate_report",
                        content_url="",
                        content_category="",
                        persona="admin",
                        query="manual_conversion",
                    )
                st.success(f"Logged {int(conv_n)} events: {conv_evt}")
                st.rerun()

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
    pricing_type = st.selectbox("Pricing type", options=["CPC", "CPA"], index=0)
    cpc = st.number_input("가정 CPC(원)", min_value=0, value=100, step=10)
    cpa = st.number_input("가정 CPA(원)", min_value=0, value=0, step=100)
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
                    pricing={"type": pricing_type, "cpc_krw": int(cpc), "cpa_krw": int(cpa)},
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
                a_type = st.selectbox(
                    "Pricing type",
                    options=["CPC", "CPA"],
                    index=0 if str((a.pricing or {}).get("type", "CPC")).upper() == "CPC" else 1,
                    key=f"ad_type_{a.id}",
                )
                a_cpc = st.number_input(
                    "CPC(원)",
                    min_value=0,
                    value=int((a.pricing or {}).get("cpc_krw", 0) or 0),
                    step=10,
                    key=f"ad_cpc_{a.id}",
                )
                a_cpa = st.number_input(
                    "CPA(원)",
                    min_value=0,
                    value=int((a.pricing or {}).get("cpa_krw", 0) or 0),
                    step=100,
                    key=f"ad_cpa_{a.id}",
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
                        pricing={"type": a_type, "cpc_krw": int(a_cpc), "cpa_krw": int(a_cpa)},
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
