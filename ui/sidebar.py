from __future__ import annotations

from datetime import datetime
import html
import os
from typing import Any, Dict

import streamlit as st

from core.constants import DEFAULT_YT_QUERY_GROUPS
from core.i18n_utils import detect_lang_auto, get_query_param, get_translator, normalize_lang
from core.subscription import (
    ai_usage_left,
    subscription_entitlements,
    subscription_snapshot,
    _save_subscription_state,
)
from core.upsell import log_upsell_event


def render_sidebar() -> Dict[str, Any]:
    """Render sidebar and return shared UI state used by the main app."""
    # Initialize translator early so the whole app can use it.
    initial_lang = normalize_lang(st.session_state.get("ui_lang") or detect_lang_auto())
    translator = get_translator(initial_lang)
    t = translator.t

    with st.sidebar:
        ui_lang_choice = st.selectbox(
            t("lang_selector"),
            options=["auto", "ko", "en", "ja", "es"],
            format_func=lambda x: {
                "auto": t("lang_auto"),
                "ko": "한국어",
                "en": "English",
                "ja": "日本語",
                "es": "Español",
            }.get(x, x),
            index=["auto", "ko", "en", "ja", "es"].index(st.session_state.get("ui_lang_choice", "ko")),
            key="ui_lang_choice",
        )

        ui_lang = detect_lang_auto() if ui_lang_choice == "auto" else normalize_lang(ui_lang_choice)
        if st.session_state.get("ui_lang") != ui_lang:
            st.session_state["ui_lang"] = ui_lang
            st.session_state["summary_cache"] = {}
            st.session_state["selected_summaries"] = []
            st.session_state["open_dialog"] = False
            st.rerun()

        translator = get_translator(ui_lang)
        t = translator.t

        st.markdown(
            f"""
<div class="sp-side-brand">
  <div class="sp-side-title">StayPick</div>
  <div class="sp-side-sub">{html.escape(t('sidebar_sub'))}</div>
</div>
""",
            unsafe_allow_html=True,
        )

        st.write("")

        admin_enabled = (get_query_param("admin") or "").strip() == "1"
        if admin_enabled:
            try:
                admin_mode = st.toggle(t("admin_toggle"), value=True)
            except Exception:
                admin_mode = st.checkbox(t("admin_toggle"), value=True)
        else:
            admin_mode = False

        env_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if env_key and not admin_mode:
            api_key = env_key
            st.caption(t("api_key_hidden"))
        else:
            api_key = st.text_input(
                t("api_key"),
                type="password",
                value=env_key,
                help=t("api_key_help"),
            )
        st.session_state.setdefault("demo_mode", False)
        try:
            demo_mode = st.toggle(
                "데모 모드 (API 없이 요약/생성)",
                value=bool(st.session_state.get("demo_mode", False)),
                help="OpenAI 호출 없이 샘플 요약/콘텐츠를 로컬에서 생성합니다.",
            )
        except Exception:
            demo_mode = st.checkbox(
                "데모 모드 (API 없이 요약/생성)",
                value=bool(st.session_state.get("demo_mode", False)),
                help="OpenAI 호출 없이 샘플 요약/콘텐츠를 로컬에서 생성합니다.",
            )
        st.session_state["demo_mode"] = bool(demo_mode)
        if st.session_state["demo_mode"]:
            st.caption("데모 모드: OpenAI API 호출이 비활성화됩니다.")
        if admin_mode and st.session_state.get("youtube_error"):
            st.warning(f"YouTube source fallback: {st.session_state.get('youtube_error')}")

        model = "gpt-4o-mini"
        embedding_model = "text-embedding-3-small"
        top_n = 8
        top_k_per_category = 10
        st.session_state.setdefault("weight_visits", 0.6)
        st.session_state.setdefault("portal_base_w", 0.72)
        st.session_state.setdefault("portal_react_w", 0.18)
        st.session_state.setdefault("portal_recency_w", 0.10)
        st.session_state.setdefault("personal_base_w", 0.9)
        st.session_state.setdefault("personal_cat_w", 0.1)
        st.session_state.setdefault("reco_base_w", 0.9)
        st.session_state.setdefault("reco_click_w", 0.1)
        st.session_state.setdefault("reco_half_life_hours", 24.0)
        st.session_state.setdefault("monetization_profile", "A")
        weight_visits = float(st.session_state.get("weight_visits", 0.6))
        weight_dwell = 1.0 - weight_visits
        sub = subscription_snapshot()

        with st.expander(t("exp_user"), expanded=True):
            st.caption(
                f"Plan: {sub['tier'].upper()} ({sub['cycle']}) · Trial left: {sub['days_left']} days · "
                f"Basic {sub['price_basic']:,}/mo ({sub['price_basic_year']:,}/yr) · "
                f"Pro {sub['price_pro']:,}/mo ({sub['price_pro_year']:,}/yr)"
            )
            if admin_mode:
                prof = st.selectbox(
                    "Monetization profile (A/B)",
                    options=["A", "B"],
                    format_func=lambda x: "A · Conversion-first" if x == "A" else "B · Value-first",
                    index=0 if st.session_state.get("monetization_profile", "A") == "A" else 1,
                )
                st.session_state["monetization_profile"] = prof
            if (not sub.get("paid", False)) and (not sub["in_trial"]):
                st.info("Trial ended. Ads stay on in free plan. Upgrade to remove ads and raise limits.")
            bill_cycle = st.selectbox(
                "Billing",
                options=["monthly", "annual"],
                index=0 if st.session_state.get("billing_cycle", "monthly") == "monthly" else 1,
                key="billing_cycle",
            )
            c_plan0, c_plan1, c_plan2 = st.columns(3)
            with c_plan0:
                if st.button("Use Free"):
                    st.session_state["plan_tier"] = "free"
                    st.session_state["billing_cycle"] = bill_cycle
                    _save_subscription_state()
                    st.rerun()
            with c_plan1:
                if st.button("Use Basic"):
                    st.session_state["plan_tier"] = "basic"
                    st.session_state["billing_cycle"] = bill_cycle
                    _save_subscription_state()
                    st.rerun()
            with c_plan2:
                if st.button("Use Pro"):
                    st.session_state["plan_tier"] = "pro"
                    st.session_state["billing_cycle"] = bill_cycle
                    _save_subscription_state()
                    st.rerun()
            ent_now = subscription_entitlements(sub)
            st.caption(
                f"Current limits · Save {ent_now['save_limit']} · Make {ent_now['make_limit']} · AI/day {ent_now['ai_daily_limit']}"
            )
            st.caption(f"AI credits left today: {ai_usage_left()}")
            if not sub.get("paid", False):
                upsell_msg = "Upgrade to remove ads and raise daily AI credits."
                if sub.get("in_trial"):
                    upsell_msg = "You are in trial. Upgrading now keeps higher limits and removes ads after trial."
                st.info(upsell_msg)
                today_key = datetime.now().strftime("%Y-%m-%d")
                if st.session_state.get("_upsell_view_logged_day") != today_key:
                    log_upsell_event("upsell_view", target_plan="")
                    st.session_state["_upsell_view_logged_day"] = today_key
                c_up1, c_up2 = st.columns(2)
                with c_up1:
                    if st.button("Upgrade to Basic", type="primary"):
                        log_upsell_event("upsell_click_basic", target_plan="basic")
                        st.session_state["plan_tier"] = "basic"
                        st.session_state["billing_cycle"] = bill_cycle
                        _save_subscription_state()
                        log_upsell_event("upgrade_applied_basic", target_plan="basic")
                        st.success("Basic plan applied.")
                        st.rerun()
                with c_up2:
                    if st.button("Upgrade to Pro"):
                        log_upsell_event("upsell_click_pro", target_plan="pro")
                        st.session_state["plan_tier"] = "pro"
                        st.session_state["billing_cycle"] = bill_cycle
                        _save_subscription_state()
                        log_upsell_event("upgrade_applied_pro", target_plan="pro")
                        st.success("Pro plan applied.")
                        st.rerun()
            if st.session_state.get("plan_tier", "free") in {"free", "basic", "pro"}:
                if st.button("Reset trial (demo)"):
                    st.session_state["trial_started_at"] = datetime.now().date().isoformat()
                    _save_subscription_state()
                    st.success("Trial reset.")
                    st.rerun()

            try:
                show_ads = st.toggle(t("toggle_ads"), value=True)
                show_metrics = st.toggle(t("toggle_metrics"), value=False)
                auto_summarize = st.toggle(t("toggle_auto_summary"), value=True, key="auto_summarize")
            except Exception:
                show_ads = st.checkbox(t("toggle_ads"), value=True)
                show_metrics = st.checkbox(t("toggle_metrics"), value=False)
                auto_summarize = st.checkbox(t("toggle_auto_summary"), value=True, key="auto_summarize")
            if not sub.get("paid", False):
                show_ads = True

            teaser_mode = st.selectbox(
                t("teaser_mode"),
                options=["snippet", "ai"],
                format_func=lambda x: t("teaser_opt_snippet") if x == "snippet" else t("teaser_opt_ai"),
                index=0,
                help="AI 한줄요약은 ‘상세 보기’에서 1회 생성(캐시됨).",
            )

        with st.expander(t("exp_make"), expanded=False):
            age_group = st.selectbox(
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
                key="age_group",
                help="연령/라이프스테이지에 맞춰 요약/훅/새 콘텐츠 난이도를 조절합니다.",
            )
            if st.session_state.get("_prev_age_group") not in (None, age_group):
                st.session_state["summary_cache"] = {}
            st.session_state["_prev_age_group"] = age_group

            persona = st.selectbox(
                t("persona"),
                options=[
                    "일반 유저(입문자)",
                    "직장인(가볍게 읽기)",
                    "스타트업 마케터",
                    "PM/PO",
                    "개발자/데이터",
                ],
                index=0,
            )
            output_format = st.selectbox(
                t("output_format"),
                options=[
                    "친구에게 보내는 추천글(짧게)",
                    "3줄 요약(초간단)",
                    "블로그 포스트(1200~1600자)",
                    "X(트위터) 스레드(8~10개)",
                ],
                index=0,
            )
            content_lang_choice = st.selectbox(
                t("output_lang"),
                options=["auto", "ko", "en", "ja", "es"],
                format_func=lambda x: {
                    "auto": t("lang_auto"),
                    "ko": "한국어",
                    "en": "English",
                    "ja": "日本語",
                    "es": "Español",
                }.get(x, x),
                index=["auto", "ko", "en", "ja", "es"].index(st.session_state.get("content_lang_choice", "auto")),
                key="content_lang_choice",
                help="생성되는 요약/새 콘텐츠 언어를 고릅니다. Auto는 화면 언어를 따릅니다.",
            )
            content_lang = ui_lang if content_lang_choice == "auto" else normalize_lang(content_lang_choice)
            st.session_state["content_lang"] = content_lang

            with st.expander(t("exp_make_advanced"), expanded=False):
                brand_tone = st.text_area(
                    t("tone"),
                    placeholder="예: 훅은 세게, 밈은 과하지 않게, 마지막에 한줄 결론",
                    height=90,
                )
        persona = locals().get("persona", "일반 유저(입문자)")
        output_format = locals().get("output_format", "친구에게 보내는 추천글(짧게)")
        brand_tone = locals().get("brand_tone", "")

        if admin_mode:
            with st.expander(t("exp_admin"), expanded=True):
                model_choice = st.selectbox(
                    "텍스트 생성 모델",
                    options=[
                        "gpt-4o-mini",
                        "gpt-4o",
                        "gpt-4.1-mini",
                        "gpt-4.1",
                        "custom",
                    ],
                    index=0,
                )
                if model_choice == "custom":
                    model = st.text_input("커스텀 모델 ID", value="gpt-4o-mini")
                else:
                    model = model_choice

                embedding_model = st.selectbox(
                    "임베딩 모델(클러스터링)",
                    options=["text-embedding-3-small", "text-embedding-3-large"],
                    index=0,
                )

                top_n = st.slider("일괄 요약할 Top N", min_value=1, max_value=20, value=8)
                top_k_per_category = st.slider("카테고리별 Top K(홈)", min_value=3, max_value=30, value=10)

                weight_visits = st.slider(
                    "스코어 가중치: 방문수",
                    min_value=0.0,
                    max_value=1.0,
                    value=float(st.session_state.get("weight_visits", 0.6)),
                    step=0.05,
                )
                st.session_state["weight_visits"] = float(weight_visits)
                weight_dwell = 1.0 - weight_visits
                st.caption(f"체류시간 가중치 = {weight_dwell:.2f}")

                st.markdown("#### Recommendation tuning")
                pb = st.slider("portal base", min_value=0.0, max_value=1.0, value=float(st.session_state.get("portal_base_w", 0.72)), step=0.01)
                pr = st.slider("portal reactions", min_value=0.0, max_value=1.0, value=float(st.session_state.get("portal_react_w", 0.18)), step=0.01)
                pc = st.slider("portal recency", min_value=0.0, max_value=1.0, value=float(st.session_state.get("portal_recency_w", 0.10)), step=0.01)
                s = max(pb + pr + pc, 1e-9)
                st.session_state["portal_base_w"] = pb / s
                st.session_state["portal_react_w"] = pr / s
                st.session_state["portal_recency_w"] = pc / s
                st.caption(
                    f"normalized: {st.session_state['portal_base_w']:.2f} / "
                    f"{st.session_state['portal_react_w']:.2f} / {st.session_state['portal_recency_w']:.2f}"
                )
                st.session_state["personal_base_w"] = st.slider("feed base score", min_value=0.0, max_value=1.0, value=float(st.session_state.get("personal_base_w", 0.9)), step=0.05)
                st.session_state["personal_cat_w"] = st.slider("feed category preference", min_value=0.0, max_value=1.0, value=float(st.session_state.get("personal_cat_w", 0.1)), step=0.05)
                st.session_state["reco_base_w"] = st.slider("reco base score", min_value=0.0, max_value=1.0, value=float(st.session_state.get("reco_base_w", 0.9)), step=0.05)
                st.session_state["reco_click_w"] = st.slider("reco click boost", min_value=0.0, max_value=1.0, value=float(st.session_state.get("reco_click_w", 0.1)), step=0.05)
                st.session_state["reco_half_life_hours"] = st.slider("reco decay half-life (hours)", min_value=6.0, max_value=168.0, value=float(st.session_state.get("reco_half_life_hours", 24.0)), step=1.0)

                st.markdown("#### Quality ranking (A/B)")
                st.session_state["rank_ab_mode"] = st.selectbox(
                    "ranking mode",
                    options=["baseline", "quality", "ab"],
                    format_func=lambda x: {"baseline": "baseline (control)", "quality": "quality score", "ab": "A/B split"}[x],
                    index=["baseline", "quality", "ab"].index(st.session_state.get("rank_ab_mode", "baseline")),
                )
                st.session_state["quality_mix_w"] = st.slider("quality mix weight", min_value=0.0, max_value=1.0, value=float(st.session_state.get("quality_mix_w", 0.35)), step=0.05)
                st.session_state["quality_ctr_w"] = st.slider("quality CTR weight", min_value=0.0, max_value=1.0, value=float(st.session_state.get("quality_ctr_w", 0.45)), step=0.05)
                st.session_state["quality_dwell_w"] = st.slider("quality dwell weight", min_value=0.0, max_value=1.0, value=float(st.session_state.get("quality_dwell_w", 0.35)), step=0.05)
                st.session_state["quality_skip_w"] = st.slider("quality skip weight", min_value=0.0, max_value=1.0, value=float(st.session_state.get("quality_skip_w", 0.20)), step=0.05)
                st.session_state["skip_threshold_sec"] = st.slider("skip threshold (sec)", min_value=3.0, max_value=30.0, value=float(st.session_state.get("skip_threshold_sec", 8.0)), step=1.0)

                st.markdown("#### YouTube source")
                st.session_state["yt_region"] = st.text_input("YT region", value=st.session_state.get("yt_region", "KR")).upper()
                st.session_state["yt_lang"] = st.text_input("YT language", value=st.session_state.get("yt_lang", "ko"))
                st.session_state["yt_kr_ratio"] = st.slider("KR mix ratio", min_value=0.5, max_value=0.9, value=float(st.session_state.get("yt_kr_ratio", 0.7)), step=0.05)
                st.session_state["yt_cache_ttl_min"] = st.slider("YT cache TTL (min)", min_value=10, max_value=30, value=int(st.session_state.get("yt_cache_ttl_min", 15)))
                st.session_state["yt_max_per_query"] = st.slider("YT max/query", min_value=3, max_value=20, value=int(st.session_state.get("yt_max_per_query", 8)))
                raw_groups = json.dumps(st.session_state.get("yt_query_groups", DEFAULT_YT_QUERY_GROUPS), ensure_ascii=False, indent=2)
                groups_txt = st.text_area("YT category queries (JSON)", value=raw_groups, height=180)
                if st.button("Apply YT query config"):
                    try:
                        parsed = json.loads(groups_txt)
                        if isinstance(parsed, dict) and parsed:
                            st.session_state["yt_query_groups"] = parsed
                            st.session_state["_yt_reload_requested"] = True
                            st.success("YouTube query config saved.")
                            st.rerun()
                        else:
                            st.error("Invalid JSON object")
                    except Exception as e:
                        st.error(f"Invalid JSON: {e}")

    return {
        "t": t,
        "admin_mode": admin_mode,
        "api_key": api_key,
        "model": model,
        "embedding_model": embedding_model,
        "top_n": top_n,
        "top_k_per_category": top_k_per_category,
        "weight_visits": weight_visits,
        "weight_dwell": weight_dwell,
        "show_ads": show_ads,
        "show_metrics": show_metrics,
        "auto_summarize": auto_summarize,
        "teaser_mode": teaser_mode,
        "age_group": age_group,
        "persona": persona,
        "output_format": output_format,
        "content_lang": content_lang,
        "brand_tone": brand_tone,
    }
