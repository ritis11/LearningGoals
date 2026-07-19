"""Pre-implementation benchmark for pipeline stages 3-5 (plans/01-mvp-plan.md).

Question under test: do we need the two-stage design (flat search -> deep fetch of
finalists only), or does a single full-metadata search ("one query returns everything,
chapters included") work just as well? And how heavy are subtitles, really?

Measures, against live YouTube:
  A. flat search   (extract_flat=True)  - latency + fields available for triage
  B. full search   (extract_flat=False) - latency (this is per-video work) + extra fields
  C. targeted full extraction of single video ids, sequential vs parallel
  D. subtitle text download (json3)     - bytes, events, ~tokens, latency

Run:  uv run python experiments/benchmark_youtube_fetch.py
"""

import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import requests
import yt_dlp

QUERY = "react vite project tutorial build app"
FLAT_N = 15          # candidates per query in the planned two-stage design
FULL_SEARCH_N = 8    # kept smaller: full search does per-video work; we extrapolate
DEEP_N = 6           # finalists to deep-fetch in test C
SUB_N = 4            # videos to download subtitle text for in test D

TRIAGE_FIELDS = ["id", "title", "duration", "channel", "view_count", "url"]
DEEP_FIELDS = ["chapters", "description", "subtitles", "automatic_captions",
               "like_count", "channel_follower_count", "upload_date", "heatmap", "tags"]


def timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    return out, time.perf_counter() - t0


def ydl_extract(target, flat):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": flat,
        "socket_timeout": 20,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(target, download=False)


def field_coverage(entries, fields):
    """% of entries where each field is present and non-empty."""
    cov = {}
    for f in fields:
        have = sum(1 for e in entries if e.get(f) not in (None, "", [], {}))
        cov[f] = f"{have}/{len(entries)}"
    return cov


def approx_tokens(text: str) -> int:
    return len(text) // 4  # rough; fine for sizing decisions


def main():
    report = {}

    # ---- A: flat search -----------------------------------------------------
    print(f"[A] flat search: ytsearch{FLAT_N}:{QUERY!r}")
    info, dt = timed(ydl_extract, f"ytsearch{FLAT_N}:{QUERY}", True)
    flat_entries = [e for e in info.get("entries", []) if e]
    report["A_flat_search"] = {
        "latency_s": round(dt, 2),
        "results": len(flat_entries),
        "triage_field_coverage": field_coverage(flat_entries, TRIAGE_FIELDS),
        "deep_field_coverage": field_coverage(flat_entries, DEEP_FIELDS),
    }
    print(json.dumps(report["A_flat_search"], indent=2))

    # ---- B: full-metadata search (the "single query" approach) --------------
    print(f"\n[B] full search: ytsearch{FULL_SEARCH_N}:{QUERY!r}  (extract_flat=False)")
    info, dt = timed(ydl_extract, f"ytsearch{FULL_SEARCH_N}:{QUERY}", False)
    full_entries = [e for e in info.get("entries", []) if e]
    per_video = dt / max(len(full_entries), 1)
    report["B_full_search"] = {
        "latency_s": round(dt, 2),
        "results": len(full_entries),
        "per_video_s": round(per_video, 2),
        "extrapolated_60_candidates_s": round(per_video * 60, 1),
        "triage_field_coverage": field_coverage(full_entries, TRIAGE_FIELDS),
        "deep_field_coverage": field_coverage(full_entries, DEEP_FIELDS),
        "note": "subtitles/automatic_captions here are URL listings, not text",
    }
    print(json.dumps(report["B_full_search"], indent=2))

    # ---- C: targeted deep fetch of finalist ids, seq vs parallel ------------
    ids = [e["id"] for e in (flat_entries or full_entries)][:DEEP_N]
    print(f"\n[C] targeted full extraction of {len(ids)} video ids")

    seq_times = []
    deep_infos = {}
    for vid in ids:
        d, dt = timed(ydl_extract, f"https://www.youtube.com/watch?v={vid}", False)
        deep_infos[vid] = d
        seq_times.append(dt)

    def fetch(vid):
        return ydl_extract(f"https://www.youtube.com/watch?v={vid}", False)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(ids)) as ex:
        list(ex.map(fetch, ids))
    par_total = time.perf_counter() - t0

    with_chapters = sum(1 for d in deep_infos.values() if d.get("chapters"))
    report["C_deep_fetch"] = {
        "sequential_per_video_s": round(statistics.mean(seq_times), 2),
        "sequential_total_s": round(sum(seq_times), 2),
        "parallel_total_s": round(par_total, 2),
        "videos_with_chapters": f"{with_chapters}/{len(ids)}",
        "extrapolated_parallel_14_finalists_s": round(par_total / len(ids) * 14 / 1.0, 1),
    }
    print(json.dumps(report["C_deep_fetch"], indent=2))

    # ---- D: subtitle text download (the part metadata does NOT include) -----
    print(f"\n[D] subtitle json3 download for up to {SUB_N} videos")
    sub_stats = []
    for vid, d in list(deep_infos.items())[:SUB_N]:
        tracks = d.get("subtitles", {}).get("en") or d.get("automatic_captions", {}).get("en") or []
        j3 = next((t for t in tracks if t.get("ext") == "json3"), None)
        if not j3:
            sub_stats.append({"id": vid, "subs": "none"})
            continue
        t0 = time.perf_counter()
        r = requests.get(j3["url"], timeout=30)
        dt = time.perf_counter() - t0
        events = r.json().get("events", [])
        text = " ".join(
            seg.get("utf8", "") for ev in events for seg in ev.get("segs", []) or []
        )
        sub_stats.append({
            "id": vid,
            "source": "manual" if d.get("subtitles", {}).get("en") else "auto",
            "download_s": round(dt, 2),
            "payload_kb": round(len(r.content) / 1024),
            "events": len(events),
            "raw_text_chars": len(text),
            "approx_tokens_raw": approx_tokens(text),
            "video_duration_min": round((d.get("duration") or 0) / 60),
        })
    report["D_subtitles"] = sub_stats
    print(json.dumps(sub_stats, indent=2))

    # ---- verdict helper ------------------------------------------------------
    print("\n" + "=" * 70)
    print("DECISION INPUTS")
    print("=" * 70)
    a, b, c = report["A_flat_search"], report["B_full_search"], report["C_deep_fetch"]
    print(f"flat search {a['results']} results:        {a['latency_s']}s")
    print(f"full search per video:          {b['per_video_s']}s  "
          f"-> ~{b['extrapolated_60_candidates_s']}s for a 60-candidate pool")
    print(f"two-stage: flat(60) + parallel deep(14): "
          f"~{round(a['latency_s'] * 4 + c['extrapolated_parallel_14_finalists_s'], 1)}s "
          f"(4 flat queries + parallel finalist fetch)")
    print(f"chapters present on deep fetch: {c['videos_with_chapters']}")
    toks = [s.get("approx_tokens_raw", 0) for s in sub_stats if "approx_tokens_raw" in s]
    if toks:
        print(f"raw subtitle tokens/video:      {min(toks)}-{max(toks)} "
              f"(vs plan's 2,500/video budget -> compression {'REQUIRED' if max(toks) > 2500 else 'optional'})")

    out = "experiments/benchmark_results.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nfull report -> {out}")


if __name__ == "__main__":
    main()
