"""Every dial in one place. Change behavior here, not by hunting through modules."""

from pathlib import Path

# --- models -----------------------------------------------------------------
MODEL_FAST = "claude-haiku-4-5"   # guard, triage: high-volume, cheap
MODEL_SMART = "claude-sonnet-5"   # plan, curate, judge: reasoning-heavy

# $ per million tokens (input, output) — used for run_meta cost accounting
PRICES_PER_MTOK = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
}
WEB_SEARCH_PRICE_PER_CALL = 0.01  # $10 / 1k searches

# --- pipeline dials ----------------------------------------------------------
RESULTS_PER_QUERY = 12       # flat search results per generated query
MAX_QUERIES = 5              # planner generates 3..MAX_QUERIES
FINALIST_COUNT = 14          # candidates that get deep fetch + go to the curator
MIN_VIDEO_SECONDS = 120      # hard filter: shorts / "in 100 seconds" style
TRANSCRIPT_TOKEN_BUDGET = 2500   # per-video transcript excerpt budget (approx tokens)
DESCRIPTION_CHAR_LIMIT = 1200    # per-video description trim for curator bundles
BUDGET_TOLERANCE = 1.05      # curriculum may exceed time budget by at most 5%
MAX_PICKS = 6
WEB_SEARCH_MAX_USES = 3      # recency-enrichment search cap
FETCH_WORKERS = 8            # parallel yt-dlp workers

# --- paths -------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / ".cache"
OUTPUT_DIR = ROOT / "outputs"
TEST_SET_DIR = ROOT / "test_set"
EVAL_RESULTS_DIR = ROOT / "eval" / "results"
