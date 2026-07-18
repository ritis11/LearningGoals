"""Stages 3 + 5: YouTube search, deep fetch, transcript compression, disk cache.

Design validated by experiments/benchmark_youtube_fetch.py: flat search gives all
triage fields in ~1s/query; full metadata is ~1s/video, so only finalists get it;
subtitle text needs a separate json3 download and per-video compression.
"""

import hashlib
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import requests
import yt_dlp

from .config import (
    CACHE_DIR,
    DESCRIPTION_CHAR_LIMIT,
    FETCH_WORKERS,
    RESULTS_PER_QUERY,
    TRANSCRIPT_TOKEN_BUDGET,
)
from .schemas import CandidateVideo, Chapter, VideoContent

log = logging.getLogger(__name__)

_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "socket_timeout": 20,
}

# The full extract_info dict is huge (formats, thumbnails, ...); downstream only
# ever reads these keys, so cache files stay small.
_INFO_KEYS = [
    "id", "title", "webpage_url", "duration", "channel", "channel_follower_count",
    "view_count", "like_count", "upload_date", "description", "chapters", "tags",
    "heatmap", "subtitles", "automatic_captions",
]


# --- disk cache ---------------------------------------------------------------

def _cache_path(kind: str, key: str) -> Path:
    return CACHE_DIR / kind / f"{key}.json"


def _cache_read(path: Path):
    """Return cached JSON, or None if missing/corrupt (corrupt -> refetch)."""
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _cache_write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


# --- stage 3: flat search -------------------------------------------------------

def search_flat(query: str, n: int = RESULTS_PER_QUERY,
                use_cache: bool = True) -> list[CandidateVideo]:
    """One flat yt-dlp search -> light candidates. Returns [] on failure."""
    key = hashlib.sha1(f"{query}|{n}".encode()).hexdigest()
    path = _cache_path("search", key)
    if use_cache and (cached := _cache_read(path)) is not None:
        return [CandidateVideo(**c) for c in cached]

    try:
        with yt_dlp.YoutubeDL({**_YDL_OPTS, "extract_flat": True}) as ydl:
            info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    except Exception as e:
        log.warning("search failed for %r: %s", query, e)
        return []

    candidates = []
    for e in info.get("entries") or []:
        if not e or not e.get("id") or not e.get("title"):
            continue
        candidates.append(CandidateVideo(
            id=e["id"],
            title=e["title"],
            url=e.get("url") or f"https://www.youtube.com/watch?v={e['id']}",
            duration_s=int(e["duration"]) if e.get("duration") else None,
            channel=e.get("channel"),
            view_count=e.get("view_count"),
            source_query=query,
        ))
    _cache_write(path, [c.model_dump() for c in candidates])
    return candidates


def search_many(queries: list[str], n: int = RESULTS_PER_QUERY,
                use_cache: bool = True) -> list[CandidateVideo]:
    """Run searches in parallel; dedupe by video id, preserving query order."""
    with ThreadPoolExecutor(max_workers=len(queries) or 1) as ex:
        per_query = list(ex.map(lambda q: search_flat(q, n, use_cache), queries))

    seen: set[str] = set()
    merged = []
    for candidates in per_query:
        for c in candidates:
            if c.id not in seen:
                seen.add(c.id)
                merged.append(c)
    return merged


# --- stage 5: deep fetch ---------------------------------------------------------

def _prune_info(info: dict, language: str) -> dict:
    """Keep only the keys downstream needs; keep only json3 subtitle tracks
    for the requested language (and variants like en-US / en-orig)."""
    pruned = {k: info.get(k) for k in _INFO_KEYS}
    for field in ("subtitles", "automatic_captions"):
        tracks = {}
        for lang, fmts in (info.get(field) or {}).items():
            if lang == language or lang.startswith(language + "-"):
                j3 = next((f for f in fmts if f.get("ext") == "json3"), None)
                if j3:
                    tracks[lang] = [{"ext": "json3", "url": j3["url"]}]
        pruned[field] = tracks
    return pruned


def fetch_video(video_id: str, use_cache: bool = True,
                language: str = "en") -> Optional[dict]:
    """Full metadata for one video, pruned to what the curator needs. None on failure."""
    path = _cache_path("videos", video_id)
    if use_cache and (cached := _cache_read(path)) is not None:
        return cached

    try:
        with yt_dlp.YoutubeDL({**_YDL_OPTS, "extract_flat": False}) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=False)
    except Exception as e:
        log.warning("deep fetch failed for %s: %s", video_id, e)
        return None

    pruned = _prune_info(info, language)
    _cache_write(path, pruned)
    return pruned


def fetch_many(video_ids: list[str], use_cache: bool = True,
               language: str = "en") -> dict[str, dict]:
    """Parallel fetch_video; failures are dropped."""
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as ex:
        infos = ex.map(lambda v: fetch_video(v, use_cache, language), video_ids)
    return {vid: info for vid, info in zip(video_ids, infos) if info}


# --- transcript pipeline -----------------------------------------------------------

def _select_track(info: dict, language: str) -> tuple[str, str, Optional[str]]:
    """Pick the best json3 track: manual subs over auto-captions, exact language
    key over variants ('en-US', 'en-orig'). Returns (source, language_key, url)."""
    for field, source in (("subtitles", "manual"), ("automatic_captions", "auto")):
        tracks = info.get(field) or {}
        keys = [k for k in tracks if k == language or k.startswith(language + "-")]
        keys.sort(key=lambda k: k != language)  # exact match first
        for k in keys:
            j3 = next((f for f in tracks[k] if f.get("ext") == "json3"), None)
            if j3 and j3.get("url"):
                return source, k, j3["url"]
    return "none", "", None


# YouTube's timedtext endpoint rate-limits aggressively per IP (observed: a burst of
# 14 downloads all 429'd). Downloads are paced, retried with backoff, and cached; after
# 3 consecutive exhausted retries the breaker skips transcripts for the rest of the run
# (bundles still carry chapters + description).
_TIMEDTEXT_PACING_S = 1.5
_TIMEDTEXT_BACKOFFS_S = (5, 20)
_BREAKER_LIMIT = 3
_last_download_at = 0.0
_consecutive_failures = 0


def _download_lines(url: str) -> list[tuple[int, str]]:
    """Download a json3 track -> [(start_ms, text)] with empty events skipped.
    Paced + retried on 429; raises after retries are exhausted."""
    global _last_download_at
    for attempt, backoff in enumerate((*_TIMEDTEXT_BACKOFFS_S, None)):
        wait = _TIMEDTEXT_PACING_S - (time.monotonic() - _last_download_at)
        if wait > 0:
            time.sleep(wait)
        r = requests.get(url, timeout=30)
        _last_download_at = time.monotonic()
        if r.status_code == 429 and backoff is not None:
            retry_after = int(r.headers.get("retry-after") or 0)
            time.sleep(max(backoff, retry_after))
            continue
        r.raise_for_status()
        lines = []
        for ev in r.json().get("events", []):
            text = "".join(seg.get("utf8", "") for seg in ev.get("segs") or [])
            text = " ".join(text.split())  # collapse newlines/whitespace
            if text:
                lines.append((ev.get("tStartMs", 0), text))
        return lines
    raise RuntimeError("unreachable")


def _dedupe_rolling(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Auto-captions re-emit the previous line at the start of the next event;
    strip text already emitted by the immediately preceding event."""
    out: list[tuple[int, str]] = []
    prev = ""
    for start_ms, text in lines:
        if prev:
            if text.startswith(prev):
                text = text[len(prev):].strip()
            elif text in prev:
                text = ""
        if text:
            out.append((start_ms, text))
            prev = text
    return out


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _snippet_at(lines: list[tuple[int, str]], start_ms: int, max_chars: int) -> str:
    """~2 sentences (capped at max_chars) of transcript from start_ms onward."""
    i = next((j for j, (t, _) in enumerate(lines) if t >= start_ms), len(lines))
    text = ""
    for _, chunk in lines[i:]:
        text = f"{text} {chunk}".strip()
        if len(text) >= max_chars or len(re.findall(r"[.!?] ", text)) >= 2:
            break
    return text[:max_chars]


def _compress(lines: list[tuple[int, str]], chapters: list[Chapter],
              duration_s: int) -> tuple[str, str]:
    """Fit the transcript into TRANSCRIPT_TOKEN_BUDGET (~4 chars/token).
    Returns (excerpt, coverage)."""
    if not lines:
        return "", "none"
    budget_chars = TRANSCRIPT_TOKEN_BUDGET * 4
    full = " ".join(text for _, text in lines)
    if len(full) <= budget_chars:
        return full, "full"

    pieces = []
    if chapters:
        # Sample the opening of each chapter: "what is taught, when".
        per = max(200, min(600, budget_chars // len(chapters)))
        used = 0
        for ch in chapters:
            if used >= budget_chars:
                break
            snippet = _snippet_at(lines, ch.start_s * 1000, per)
            if snippet:
                pieces.append(f"[{ch.title} @ {_fmt_ts(ch.start_s)}] {snippet}")
                used += len(pieces[-1])
    else:
        # Head chunk + evenly spaced windows across the video.
        head = full[:int(budget_chars * 0.3)]
        pieces.append(f"[@ 00:00] {head}")
        n_windows = 6
        per = int(budget_chars * 0.7) // n_windows
        end_ms = lines[-1][0] or duration_s * 1000
        for i in range(1, n_windows + 1):
            at_ms = int(end_ms * i / (n_windows + 1))
            snippet = _snippet_at(lines, at_ms, per)
            if snippet:
                pieces.append(f"[@ {_fmt_ts(at_ms / 1000)}] {snippet}")
    return "\n".join(pieces), "sampled"


def _build_transcript(info: dict, chapters: list[Chapter],
                      language: str) -> tuple[str, str, str, str]:
    """Full pipeline: select -> download (cached) -> dedupe -> compress. Never raises.
    Returns (excerpt, coverage, source, language_key)."""
    global _consecutive_failures
    source, lang_key, url = _select_track(info, language)
    if not url:
        return "", "none", "none", ""

    # transcripts are immutable per video+track: cache the deduped lines so eval
    # reruns never re-hit the rate-limited timedtext endpoint
    cache = _cache_path("transcripts", f"{info['id']}.{source}.{lang_key}")
    lines = _cache_read(cache)
    if lines is not None:
        lines = [(int(t), s) for t, s in lines]
    else:
        if _consecutive_failures >= _BREAKER_LIMIT:
            log.warning("transcript breaker open; skipping %s", info.get("id"))
            return "", "none", "none", ""
        try:
            lines = _dedupe_rolling(_download_lines(url))
            _cache_write(cache, lines)
            _consecutive_failures = 0
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (403, 404):
                # cached track URLs are signed and expire (~6h): refresh metadata once
                fresh = fetch_video(info["id"], use_cache=False, language=language)
                _, _, fresh_url = _select_track(fresh or {}, language)
                if fresh_url and fresh_url != url:
                    try:
                        lines = _dedupe_rolling(_download_lines(fresh_url))
                        _cache_write(cache, lines)
                        _consecutive_failures = 0
                        excerpt, coverage = _compress(
                            lines, chapters, int(info.get("duration") or 0))
                        return (excerpt, coverage, source, lang_key) if excerpt else ("", "none", "none", "")
                    except Exception as e2:
                        e = e2
            _consecutive_failures += 1
            log.warning("transcript failed for %s: %s", info.get("id"), e)
            return "", "none", "none", ""

    excerpt, coverage = _compress(lines, chapters, int(info.get("duration") or 0))
    if not excerpt:
        return "", "none", "none", ""
    return excerpt, coverage, source, lang_key


# --- curator bundle ------------------------------------------------------------------

def build_content_bundle(info: dict, language: str = "en") -> VideoContent:
    """Assemble the curator's per-video bundle from a pruned info dict."""
    chapters = [
        Chapter(title=c.get("title", ""), start_s=int(c.get("start_time") or 0),
                end_s=int(c.get("end_time") or 0))
        for c in info.get("chapters") or []
    ]
    excerpt, coverage, source, lang_key = _build_transcript(info, chapters, language)
    return VideoContent(
        id=info["id"],
        title=info.get("title") or "",
        url=info.get("webpage_url") or f"https://www.youtube.com/watch?v={info['id']}",
        duration_s=int(info.get("duration") or 0),
        channel=info.get("channel") or "",
        channel_followers=info.get("channel_follower_count"),
        view_count=info.get("view_count"),
        like_count=info.get("like_count"),
        upload_date=info.get("upload_date") or "",
        description_excerpt=(info.get("description") or "")[:DESCRIPTION_CHAR_LIMIT],
        chapters=chapters,
        transcript_excerpt=excerpt,
        transcript_coverage=coverage,
        transcript_source=source,
        transcript_language=lang_key,
    )
