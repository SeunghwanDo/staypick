from __future__ import annotations

import streamlit as st

PORTAL_CSS = """
<style>
/* Hide Streamlit chrome (better for demo videos) */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header[data-testid="stHeader"] {visibility: hidden; height: 0px;}
div[data-testid="stToolbar"] {visibility: hidden; height: 0px;}
div[data-testid="stDeployButton"] {display: none;}
html { scroll-behavior: smooth; }

/* App background */
.stApp { background: #f6f7fb; }

/* Compact vertical spacing for denser feed */
.block-container { padding-top: 0.7rem; padding-bottom: 1.1rem; }

/* Sidebar */
section[data-testid="stSidebar"] > div {
  background: linear-gradient(180deg, rgba(255, 99, 71, 0.12), rgba(255,255,255,1) 240px);
  border-right: 1px solid rgba(49, 51, 63, 0.10);
}
.sp-side-brand {
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(49, 51, 63, 0.10);
  background: rgba(255,255,255,0.80);
}
.sp-side-title { font-weight: 900; font-size: 18px; letter-spacing: -0.4px; }
.sp-side-sub { color: rgba(49, 51, 63, 0.70); font-size: 12px; margin-top: 4px; }

/* Top header */
.staypick-header {
  display:flex; align-items:center; gap:10px;
  padding: 8px 12px;
  border:1px solid rgba(49, 51, 63, 0.12);
  border-radius: 14px;
  background: rgba(255,255,255,0.85);
  box-shadow: 0 4px 16px rgba(20, 20, 40, 0.06);
}
.staypick-logo { font-weight: 900; font-size: 20px; letter-spacing: -0.3px; }
.staypick-pill {
  font-size: 12px; padding: 3px 10px; border-radius: 999px;
  border: 1px solid rgba(49, 51, 63, 0.18);
  background: rgba(255,255,255,0.9);
}

/* Mini buttons */
.staypick-btn-mini {
  display:inline-block; padding: 5px 10px; border-radius: 999px;
  border: 1px solid rgba(49, 51, 63, 0.14);
  background: rgba(255,255,255,0.9);
  font-size: 12px;
}

/* Category pills */
.sp-cat {
  display:inline-flex; align-items:center; gap:6px;
  padding: 8px 12px; border-radius: 999px; font-size: 13px;
  border: 1px solid rgba(49, 51, 63, 0.12);
  background: rgba(255,255,255,0.85);
}

/* Cards */
.sp-card {
  border-radius: 16px; border: 1px solid rgba(49, 51, 63, 0.10);
  background: rgba(255,255,255,0.9); box-shadow: 0 8px 20px rgba(20,20,40,0.06);
  padding: 16px;
}
.sp-card:hover { box-shadow: 0 12px 24px rgba(20,20,40,0.12); }

.sp-card-item {
  border-radius: 18px;
  border: 1px solid rgba(49, 51, 63, 0.10);
  background: rgba(255,255,255,0.95);
  box-shadow: 0 10px 24px rgba(20,20,40,0.10);
  padding: 18px;
  margin-bottom: 22px;
}
.sp-card-item.large {
  transform: scale(1.02);
}
.sp-card-body {
  display: flex;
  gap: 16px;
}
.sp-card-thumb {
  flex: 0 0 180px;
}
.sp-card-content {
  flex: 1 1 auto;
}
.sp-card-title {
  font-weight: 900;
  font-size: 16px;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.sp-card-title.large {
  font-size: 22px;
}
.sp-card-meta {
  font-size: 12px;
  color: rgba(49,51,63,0.72);
  margin-top: 4px;
}
.sp-card-snippet {
  margin-top: 8px;
  color: rgba(49,51,63,0.8);
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Feed thumbnails */
.sp-thumb {
  border-radius: 14px; overflow: hidden; border: 1px solid rgba(49, 51, 63, 0.08);
  box-shadow: 0 6px 14px rgba(10,10,30,0.10);
}

/* Shorts grid: title clamp + equal button widths */
.short-title{
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 40px;
  font-weight: 900;
}
.short-meta{
  font-size: 12px;
  color: rgba(49,51,63,0.72);
  min-height: 18px;
}

/* Dialog */
section[data-testid="stModal"] {
  max-width: 980px;
}

/* Pill tags */
.sp-tag {
  display:inline-flex; align-items:center; gap:6px;
  padding: 4px 8px; border-radius: 999px;
  border: 1px solid rgba(49, 51, 63, 0.12);
  background: rgba(255,255,255,0.8); font-size: 12px;
}

/* Smoother input */
.stTextInput input, .stSelectbox select, .stTextArea textarea {
  border-radius: 10px !important;
}

/* Tabs tweaks */
.stTabs [data-baseweb="tab"] {
  font-weight: 700;
}

/* Buttons */
.stButton>button {
  border-radius: 12px;
}

/* Metrics */
.stMetric {
  border: 1px solid rgba(49, 51, 63, 0.10);
  border-radius: 16px;
  padding: 10px 14px;
  background: rgba(255,255,255,0.88);
}

/* Hero */
.sp-hero {
  border-radius: 22px;
  padding: 24px 24px;
  border: 1px solid rgba(49, 51, 63, 0.10);
  background: linear-gradient(135deg, rgba(255, 99, 71, 0.14), rgba(255, 200, 120, 0.12));
  box-shadow: 0 12px 30px rgba(20,20,40,0.08);
}

.sp-hero h1 {
  font-size: 32px; font-weight: 900; letter-spacing: -0.6px; margin-bottom: 8px;
}
.sp-hero p {
  font-size: 15px; color: rgba(49, 51, 63, 0.8); line-height: 1.6;
}

.sp-hero-cta {
  display:flex; flex-wrap: wrap; gap: 10px; margin-top: 8px;
}

.sp-hero-cta a {
  text-decoration: none;
}

.sp-hero-cta .sp-primary {
  display:inline-block; padding: 10px 16px; border-radius: 12px;
  background: #ff6347; color: white; font-weight: 800; border: 0;
}

.sp-hero-cta .sp-secondary {
  display:inline-block; padding: 10px 16px; border-radius: 12px;
  background: white; color: #ff6347; font-weight: 800; border: 1px solid rgba(49, 51, 63, 0.14);
}

.sp-step {
  border-radius: 16px; padding: 14px 16px; background: rgba(255,255,255,0.9);
  border: 1px solid rgba(49, 51, 63, 0.10);
}

.sp-step h4 { margin-bottom: 4px; }

.sp-footer {
  margin-top: 24px; padding: 18px; border-radius: 16px;
  background: rgba(255,255,255,0.85); border: 1px solid rgba(49, 51, 63, 0.10);
}
</style>
"""


def apply_portal_css() -> None:
    st.markdown(PORTAL_CSS, unsafe_allow_html=True)
