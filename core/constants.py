from __future__ import annotations

import os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEMO_CSV_PATH = os.path.join(APP_DIR, "sample_data", "metrics_sample_fun_with_content.csv")
SUBSCRIPTION_STATE_PATH = os.path.join(APP_DIR, "data", "subscription_state.json")
YOUTUBE_SNAPSHOT_PATH = os.path.join(APP_DIR, "data", "youtube_last_success.csv")
UPSELL_EVENTS_PATH = os.path.join(APP_DIR, "data", "upsell_events.csv")
LANDING_PAGE_PATH = os.path.join(APP_DIR, "StayPick_OnePager_Package", "StayPick_Landing.html")

DEFAULT_YT_QUERY_GROUPS = {
    "game": ["게임 추천", "스팀 게임", "모바일 게임"],
    "finance": ["재정 관리", "재테크", "절약"],
    "love": ["연애 썰", "썸", "이별"],
    "life": ["생활 꿀팁", "청소 꿀팁", "요리 꿀팁"],
    "animal": ["반려동물", "강아지", "고양이"],
    "celebrity": ["연예인 근황", "아이돌", "배우 인터뷰"],
    "tech": ["테크 트렌드", "AI 툴", "가젯 리뷰"],
    "trend": ["실시간 이슈", "요즘 화제", "급상승 영상"],
}

FEED_CATEGORY_ORDER = ["game", "finance", "love", "life", "animal", "celebrity", "tech", "trend"]
FEED_CATEGORY_EMOJI = {
    "game": "🎮",
    "finance": "💰",
    "love": "💕",
    "life": "🧩",
    "animal": "🐾",
    "celebrity": "✨",
    "tech": "🤖",
    "trend": "🔥",
}

MONETIZATION_ASSUMPTIONS = {
    # A: conversion-first (more conservative)
    "A": {"paid_rate": 0.018, "pro_share": 0.25},
    # B: value-first (higher conversion/value expectation)
    "B": {"paid_rate": 0.030, "pro_share": 0.38},
}
MONETIZATION_PRICING = {
    # A: lower entry price for conversion
    "A": {"basic": 4900, "pro": 9900},
    # B: higher value capture
    "B": {"basic": 5900, "pro": 12900},
}
ANNUAL_DISCOUNT_RATE = 0.20
