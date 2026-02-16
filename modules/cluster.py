from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

import numpy as np
from sklearn.cluster import KMeans


def cluster_summaries(
    embeddings: List[List[float]],
    summaries: List[Dict[str, Any]],
    max_clusters: int = 3,
) -> List[Dict[str, Any]]:
    """
    Very small clustering utility:
    - Runs KMeans with k=min(max_clusters, n)
    - Labels clusters by most frequent tags
    Returns: list of {label, items}
    """
    n = len(summaries)
    if n == 0:
        return []
    if n == 1:
        return [{"label": "전체", "items": summaries}]

    k = min(max_clusters, n)
    X = np.array(embeddings, dtype=float)

    # KMeans n_init changed in sklearn; "auto" supported on newer versions.
    try:
        km = KMeans(n_clusters=k, random_state=42, n_init="auto")
    except TypeError:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)

    labels = km.fit_predict(X).tolist()

    bucket = defaultdict(list)
    for lab, item in zip(labels, summaries):
        bucket[int(lab)].append(item)

    clusters = []
    for lab, items in bucket.items():
        tag_counter = Counter()
        for it in items:
            for t in it.get("tags", []) or []:
                tag_counter[t] += 1
        top_tags = [t for t, _ in tag_counter.most_common(3)]
        label = " / ".join(top_tags) if top_tags else f"클러스터 {lab+1}"
        clusters.append({"label": label, "items": items})

    # Sort clusters by size desc
    clusters.sort(key=lambda c: len(c["items"]), reverse=True)
    return clusters
