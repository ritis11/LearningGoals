"""Live smoke test for the YouTube layer (WP2). No API key needed, just network.

Run:  uv run python experiments/smoke_youtube_layer.py
"""

import logging
import time

from curriculum_agent.config import CACHE_DIR, TRANSCRIPT_TOKEN_BUDGET
from curriculum_agent.youtube import (
    build_content_bundle,
    fetch_many,
    fetch_video,
    search_flat,
    search_many,
)

logging.basicConfig(level=logging.WARNING)

QUERIES = [
    "react vite project tutorial",
    "react hooks crash course",
    "build habit tracker react",
]


def main() -> None:
    # 1. parallel flat search + dedupe
    t0 = time.perf_counter()
    candidates = search_many(QUERIES)
    print(f"[1] search_many: {len(candidates)} unique candidates "
          f"in {time.perf_counter() - t0:.1f}s")
    assert len(candidates) >= 25, f"expected >= 25 candidates, got {len(candidates)}"
    assert all(c.id and c.title and c.duration_s for c in candidates[:3])
    for c in candidates[:3]:
        print(f"    {c.id}  {c.duration_s or 0:>5}s  {c.title[:60]}")

    # 2. deep fetch 4 finalists (prefer 8-45 min videos)
    mid = [c for c in candidates if c.duration_s and 8 * 60 <= c.duration_s <= 45 * 60]
    ids = [c.id for c in (mid or candidates)[:4]]
    t0 = time.perf_counter()
    infos = fetch_many(ids)
    print(f"[2] fetch_many: {len(infos)}/{len(ids)} succeeded "
          f"in {time.perf_counter() - t0:.1f}s")
    assert len(infos) >= 3, f"expected >= 3 fetches, got {len(infos)}"

    # 3. content bundles under token budget
    n_with_transcript = 0
    for vid, info in infos.items():
        b = build_content_bundle(info)
        tokens = len(b.transcript_excerpt) // 4
        print(f"[3] {b.title[:52]:<52} {b.duration_s // 60:>3}min "
              f"chapters={len(b.chapters):<2} src={b.transcript_source:<6} "
              f"coverage={b.transcript_coverage:<7} ~{tokens} tok")
        if b.transcript_excerpt:
            n_with_transcript += 1
            assert tokens <= TRANSCRIPT_TOKEN_BUDGET * 1.2, \
                f"{vid}: transcript over budget ({tokens} tok)"
    assert n_with_transcript >= 1, "no bundle got a transcript"

    # 4. cache behavior: re-run one search and one fetch
    t0 = time.perf_counter()
    again = search_flat(QUERIES[0])
    t_search = time.perf_counter() - t0
    t0 = time.perf_counter()
    fetch_video(ids[0])
    t_fetch = time.perf_counter() - t0
    print(f"[4] cache: search_flat rerun {t_search * 1000:.0f}ms "
          f"({len(again)} results), fetch_video rerun {t_fetch * 1000:.0f}ms")
    assert t_search < 0.5 and t_fetch < 0.5, "cached reruns should be near-instant"
    assert any((CACHE_DIR / "search").glob("*.json")), "no search cache files"
    assert (CACHE_DIR / "videos" / f"{ids[0]}.json").exists(), "no video cache file"

    print("SMOKE OK")


if __name__ == "__main__":
    main()
