from __future__ import annotations

import os
from datetime import datetime

import pandas as pd
import streamlit as st

from core.constants import APP_DIR, UPSELL_EVENTS_PATH
from core.subscription import subscription_snapshot


def log_upsell_event(event: str, target_plan: str = "", source: str = "sidebar") -> None:
    try:
        os.makedirs(os.path.join(APP_DIR, "data"), exist_ok=True)
        sub = subscription_snapshot()
        row = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": (event or "").strip(),
            "source": (source or "").strip(),
            "from_plan": str(sub.get("tier", "free") or "free"),
            "target_plan": (target_plan or "").strip(),
            "billing_cycle": str(st.session_state.get("billing_cycle", "monthly") or "monthly"),
            "in_trial": bool(sub.get("in_trial", False)),
            "days_left": int(sub.get("days_left", 0) or 0),
            "profile": str(st.session_state.get("monetization_profile", "A") or "A"),
        }
        df_row = pd.DataFrame([row])
        if os.path.exists(UPSELL_EVENTS_PATH):
            df_row.to_csv(UPSELL_EVENTS_PATH, mode="a", index=False, header=False, encoding="utf-8-sig")
        else:
            df_row.to_csv(UPSELL_EVENTS_PATH, mode="w", index=False, header=True, encoding="utf-8-sig")
    except Exception:
        pass


def load_upsell_events_df() -> pd.DataFrame:
    if not os.path.exists(UPSELL_EVENTS_PATH):
        return pd.DataFrame()
    try:
        return pd.read_csv(UPSELL_EVENTS_PATH)
    except Exception:
        return pd.DataFrame()
