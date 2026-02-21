from __future__ import annotations

import html
from typing import List


def chips_to_html(chips: List[str], max_items: int = 3) -> str:
    items = [c for c in (chips or []) if str(c).strip()][:max_items]
    if not items:
        return ""
    return "".join([f"<span class='sp-chip'>{html.escape(str(x))}</span>" for x in items])


def emoji_for_category(cat: str) -> str:
    c = (cat or "").lower()
    mapping = {
        "ai": "🤖",
        "tech": "🧠",
        "product": "🧩",
        "startup": "🚀",
        "career": "💼",
        "travel": "🧳",
        "food": "🍜",
        "game": "🎮",
        "fun": "😂",
        "ent": "🎬",
        "love": "💘",
        "sports": "⚽",
        "finance": "💰",
        "news": "🗞️",
        "전체": "🔥",
    }
    for k, v in mapping.items():
        if k in c:
            return v
    return "✨"


def gradient_for_seed(seed: str) -> str:
    """Return a nice gradient background style from a stable seed."""
    palettes = [
        ("#ff5f6d", "#ffc371"),
        ("#36d1dc", "#5b86e5"),
        ("#a18cd1", "#fbc2eb"),
        ("#f953c6", "#b91d73"),
        ("#43cea2", "#185a9d"),
        ("#ff9966", "#ff5e62"),
        ("#7f7fd5", "#86a8e7"),
    ]
    idx = abs(hash(seed or "seed")) % len(palettes)
    a, b = palettes[idx]
    return f"background: linear-gradient(135deg, {a}, {b});"
