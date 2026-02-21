from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict

import streamlit as st

from core.constants import ANNUAL_DISCOUNT_RATE, MONETIZATION_PRICING, SUBSCRIPTION_STATE_PATH


def _load_subscription_state() -> Dict[str, Any]:
    try:
        if os.path.exists(SUBSCRIPTION_STATE_PATH):
            with open(SUBSCRIPTION_STATE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {}


def _save_subscription_state() -> None:
    try:
        os.makedirs(os.path.dirname(SUBSCRIPTION_STATE_PATH), exist_ok=True)
        data = {
            "plan_tier": st.session_state.get("plan_tier", "free"),
            "billing_cycle": st.session_state.get("billing_cycle", "monthly"),
            "trial_started_at": st.session_state.get("trial_started_at"),
        }
        with open(SUBSCRIPTION_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def subscription_snapshot() -> Dict[str, Any]:
    trial_days = 14
    started = st.session_state.get("trial_started_at")
    if not started:
        started = datetime.now().date().isoformat()
        st.session_state["trial_started_at"] = started
        _save_subscription_state()
    try:
        started_dt = datetime.fromisoformat(str(started)).date()
    except Exception:
        started_dt = datetime.now().date()
        st.session_state["trial_started_at"] = started_dt.isoformat()
        _save_subscription_state()

    trial_ends = started_dt + timedelta(days=trial_days)
    today = datetime.now().date()
    in_trial = today <= trial_ends

    tier = str(st.session_state.get("plan_tier", "free") or "free").lower()
    if tier not in {"free", "basic", "pro"}:
        tier = "free"
    cycle = str(st.session_state.get("billing_cycle", "monthly") or "monthly").lower()
    if cycle not in {"monthly", "annual"}:
        cycle = "monthly"
    paid = tier in {"basic", "pro"}
    premium = paid
    days_left = max((trial_ends - today).days, 0)
    profile = str(st.session_state.get("monetization_profile", "A") or "A").upper()
    pricing = MONETIZATION_PRICING.get(profile, MONETIZATION_PRICING["A"])
    price_basic = int(pricing.get("basic", 4900) or 4900)
    price_pro = int(pricing.get("pro", 9900) or 9900)
    annual_mult = max(0.0, 1.0 - float(ANNUAL_DISCOUNT_RATE))
    price_basic_year = int(price_basic * 12 * annual_mult)
    price_pro_year = int(price_pro * 12 * annual_mult)
    return {
        "tier": tier,
        "cycle": cycle,
        "in_trial": in_trial,
        "paid": paid,
        "premium": premium,
        "days_left": days_left,
        "trial_ends": trial_ends.isoformat(),
        "price_basic": price_basic,
        "price_pro": price_pro,
        "price_basic_year": price_basic_year,
        "price_pro_year": price_pro_year,
    }


def subscription_entitlements(sub: Dict[str, Any]) -> Dict[str, int]:
    profile = str(st.session_state.get("monetization_profile", "A") or "A").upper()
    if profile == "B":
        if str(sub.get("tier", "free") or "free").lower() == "pro":
            return {"save_limit": 1500, "make_limit": 150, "ai_daily_limit": 1500}
        if str(sub.get("tier", "free") or "free").lower() == "basic":
            return {"save_limit": 500, "make_limit": 50, "ai_daily_limit": 500}
        if sub.get("in_trial"):
            return {"save_limit": 80, "make_limit": 20, "ai_daily_limit": 80}
        return {"save_limit": 20, "make_limit": 5, "ai_daily_limit": 10}

    tier = str(sub.get("tier", "free") or "free").lower()
    if tier == "pro":
        return {"save_limit": 1000, "make_limit": 100, "ai_daily_limit": 1000}
    if tier == "basic":
        return {"save_limit": 300, "make_limit": 30, "ai_daily_limit": 300}
    if sub.get("in_trial"):
        return {"save_limit": 50, "make_limit": 10, "ai_daily_limit": 50}
    return {"save_limit": 20, "make_limit": 5, "ai_daily_limit": 10}


def _today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def ai_usage_left() -> int:
    sub = subscription_snapshot()
    ent = subscription_entitlements(sub)
    day = _today_key()
    usage = st.session_state.get("ai_usage", {})
    if not isinstance(usage, dict):
        usage = {}
    used = int(usage.get(day, 0) or 0)
    return max(int(ent["ai_daily_limit"]) - used, 0)


def consume_ai_credit() -> bool:
    left = ai_usage_left()
    if left <= 0:
        return False
    day = _today_key()
    usage = st.session_state.get("ai_usage", {})
    if not isinstance(usage, dict):
        usage = {}
    usage[day] = int(usage.get(day, 0) or 0) + 1
    st.session_state["ai_usage"] = usage
    return True
