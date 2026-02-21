from __future__ import annotations

import streamlit as st

from modules.i18n import get_translator, normalize_lang


def get_query_param(name: str) -> str:
    """Best-effort query param getter across Streamlit versions."""
    try:
        v = st.query_params.get(name)
        if isinstance(v, list):
            return str(v[0]) if v else ""
        return str(v or "")
    except Exception:
        try:
            qp = st.experimental_get_query_params()  # type: ignore[attr-defined]
            v2 = qp.get(name, [""])
            return str(v2[0]) if v2 else ""
        except Exception:
            return ""


def detect_lang_auto() -> str:
    """Detect UI language.

    Priority:
    1) URL param ?lang=ko|en|ja|es
    2) HTTP Accept-Language header (when deployed)
    3) Default to Korean
    """
    q = (get_query_param("lang") or "").strip()
    if q:
        return normalize_lang(q)

    try:
        accept = (st.context.headers.get("accept-language") or st.context.headers.get("Accept-Language") or "")  # type: ignore[attr-defined]
    except Exception:
        accept = ""
    if accept:
        first = accept.split(",")[0].strip()
        code = first.split(";")[0].strip()
        return normalize_lang(code)
    return "ko"
