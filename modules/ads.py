from __future__ import annotations

import csv
import json
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass
class Ad:
    id: str
    brand: str
    title: str
    description: str
    cta: str
    landing_url: str
    categories: List[str]
    keywords: List[str]
    pricing: Dict[str, Any]
    hook: str = ""  # short dopamine/curiosity line (keep truthful)
    image_url: str = ""  # optional thumbnail
    active: bool = True


def _data_paths(app_dir: str) -> Tuple[str, str, str]:
    data_dir = os.path.join(app_dir, "data")
    ads_file = os.path.join(data_dir, "ads_inventory.json")
    events_file = os.path.join(data_dir, "ads_events.csv")
    return data_dir, ads_file, events_file


def ensure_ads_storage(app_dir: str) -> None:
    """Create data dir and empty events file if missing."""
    data_dir, ads_file, events_file = _data_paths(app_dir)
    os.makedirs(data_dir, exist_ok=True)

    # Don't overwrite ads file if user already customized it
    if not os.path.exists(ads_file):
        # Minimal default inventory
        default_ads = [
            {
                "id": "sp_default",
                "brand": "StayPick Sponsor",
                "title": "스폰서 슬롯(데모)",
                "description": "운영자 모드에서 광고 인벤토리를 수정할 수 있어요.",
                "hook": "🔥 스폰서 데모",
                "cta": "자세히",
                "landing_url": "https://example.com",
                "categories": ["전체"],
                "keywords": ["demo"],
                "pricing": {"type": "CPC", "cpc_krw": 100},
                "image_url": "",
                "active": True,
            }
        ]
        with open(ads_file, "w", encoding="utf-8") as f:
            json.dump(default_ads, f, ensure_ascii=False, indent=2)

    # Create events header if missing
    if not os.path.exists(events_file):
        with open(events_file, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "ts",
                    "event",
                    "ad_id",
                    "placement",
                    "content_url",
                    "content_category",
                    "persona",
                    "query",
                ]
            )


def load_ads(app_dir: str) -> List[Ad]:
    data_dir, ads_file, _ = _data_paths(app_dir)
    os.makedirs(data_dir, exist_ok=True)
    if not os.path.exists(ads_file):
        ensure_ads_storage(app_dir)

    with open(ads_file, "r", encoding="utf-8") as f:
        raw = json.load(f)

    ads: List[Ad] = []
    for a in raw:
        try:
            ads.append(
                Ad(
                    id=str(a.get("id", "")),
                    brand=str(a.get("brand", "")),
                    title=str(a.get("title", "")),
                    description=str(a.get("description", "")),
                    hook=str(a.get("hook", "")),
                    cta=str(a.get("cta", "보기")),
                    landing_url=str(a.get("landing_url", "")),
                    categories=list(a.get("categories") or []),
                    keywords=list(a.get("keywords") or []),
                    pricing=dict(a.get("pricing") or {}),
                    image_url=str(a.get("image_url", "")),
                    active=bool(a.get("active", True)),
                )
            )
        except Exception:
            continue
    return ads


def save_ads(app_dir: str, ads: Sequence[Ad]) -> None:
    data_dir, ads_file, _ = _data_paths(app_dir)
    os.makedirs(data_dir, exist_ok=True)

    raw = []
    for a in ads:
        raw.append(
            {
                "id": a.id,
                "brand": a.brand,
                "title": a.title,
                "description": a.description,
                "hook": a.hook,
                "cta": a.cta,
                "landing_url": a.landing_url,
                "categories": a.categories,
                "keywords": a.keywords,
                "pricing": a.pricing,
                "image_url": a.image_url,
                "active": a.active,
            }
        )

    with open(ads_file, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)


def log_event(
    app_dir: str,
    *,
    event: str,
    ad_id: str,
    placement: str,
    content_url: str = "",
    content_category: str = "",
    persona: str = "",
    query: str = "",
) -> None:
    _, _, events_file = _data_paths(app_dir)
    if not os.path.exists(events_file):
        ensure_ads_storage(app_dir)

    with open(events_file, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                int(time.time()),
                event,
                ad_id,
                placement,
                content_url,
                content_category,
                persona,
                query,
            ]
        )


def _normalize_tokens(items: Iterable[str]) -> List[str]:
    out = []
    for x in items:
        t = (x or "").strip().lower()
        if not t:
            continue
        out.append(t)
    return out


def select_ads(
    ads: Sequence[Ad],
    *,
    context_categories: Sequence[str],
    context_keywords: Sequence[str],
    n: int = 2,
    seed: Optional[int] = None,
) -> List[Ad]:
    """Very small 'native ads' selector.

    - Matches categories first
    - Then keyword overlap
    - Uses CPC as a base

    This is intentionally simple for hackathon demos.
    """
    rng = random.Random(seed)

    ctx_cats = set(_normalize_tokens(context_categories))
    ctx_kw = set(_normalize_tokens(context_keywords))

    scored: List[Tuple[float, Ad]] = []
    for a in ads:
        if not a.active:
            continue
        a_cats = set(_normalize_tokens(a.categories))
        a_kw = set(_normalize_tokens(a.keywords))

        cat_match = 1.0 if ("전체" in a_cats or bool(ctx_cats & a_cats)) else 0.0
        kw_overlap = len(ctx_kw & a_kw)

        cpc = float((a.pricing or {}).get("cpc_krw", 0) or 0)
        base = cpc / 100.0

        # Small random jitter to avoid same ordering forever
        score = base + cat_match * 2.0 + min(kw_overlap, 5) * 0.4 + rng.random() * 0.05
        scored.append((score, a))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored[:n]]
