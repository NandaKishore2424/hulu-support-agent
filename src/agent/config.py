"""Central configuration.

Everything tunable lives here so the report can point at one file when it says
"these were the settings that produced the headline numbers".
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# ---------------------------------------------------------------- filesystem
RAW_DIR = ROOT / "data" / "raw"
PROC_DIR = ROOT / "data" / "processed"
GOLDEN_DIR = ROOT / "data" / "golden"
CACHE_DIR = ROOT / "cache" / "llm"
REPORT_DIR = ROOT / "reports"
for _d in (RAW_DIR, PROC_DIR, GOLDEN_DIR, CACHE_DIR, REPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

TWCS_CSV = RAW_DIR / "twcs" / "twcs.csv"

# ---------------------------------------------------------------- providers
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

GROQ_BASE = "https://api.groq.com/openai/v1"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# The agent generates on Groq; the judge scores on Gemini. Different vendors and
# different model families, so the judge is not grading its own writing. See
# decision log entry on judge independence.
#
# Groq retired the Llama 3.x models this project first targeted, so the agent
# runs on gpt-oss. It is a reasoning model: it spends tokens thinking before it
# answers, and a small max_tokens truncates the JSON mid-object, which Groq
# rejects with a 400. Hence the large default budget below.
AGENT_MODEL = os.getenv("AGENT_MODEL", "openai/gpt-oss-120b")
AGENT_MODEL_FALLBACK = os.getenv("AGENT_MODEL_FALLBACK", "openai/gpt-oss-20b")
AGENT_REASONING_EFFORT = os.getenv("AGENT_REASONING_EFFORT", "medium")

# gemini-2.5-flash is closed to new API keys. gemini-3.6-flash answers but took
# 23s per call, too slow for several hundred judgements.
#
# gemini-3.5-flash was the judge until its free-tier daily request cap ran out
# mid-run. That cap is per model
# (quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier), so a sibling model
# has its own untouched allowance. The judge moved to 3.5-flash-lite, which
# separates reply quality from postability just as cleanly on the discrimination
# probe and answers in about a second.
#
# One judge scores every system or the comparison is meaningless, so the verdicts
# written by the old judge were discarded rather than mixed in, every verdict now
# records the model that produced it, and the scripts refuse to aggregate a mixed
# set. The judge deliberately does not fail over to another model: a quota wall
# must stop the run, not silently change the instrument.
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-3.5-flash-lite")
# Last-resort model if Groq's daily cap is hit mid-run. Deliberately NOT the
# judge model: if the judge ever scored text written by its own weights the
# independence argument would collapse. Runs served this way are counted and
# reported.
EMERGENCY_MODEL = os.getenv("EMERGENCY_MODEL", "gemini-3.1-flash-lite")

# Measured from Groq's own headers on this key: 1000 requests/day and 8000
# tokens/minute. Tokens bind long before requests do, because one agent prompt is
# roughly 1900 tokens, so the sustainable rate is about three calls a minute.
# A rolling token-budget throttle enforces that; a fixed sleep cannot, since
# prompts vary in size by a factor of two.
GROQ_TOKENS_PER_MINUTE = int(os.getenv("GROQ_TOKENS_PER_MINUTE", "7200"))
GEMINI_TOKENS_PER_MINUTE = int(os.getenv("GEMINI_TOKENS_PER_MINUTE", "200000"))

# The two providers bind on different axes and both have to be respected.
# Groq's ceiling is tokens per minute; its request allowance is generous.
# Gemini is the opposite: tokens per minute are effectively unlimited on the free
# tier but requests per minute are tight, and exceeding them returns a 429 whose
# quotaId ends PerMinutePerProjectPerModel. The judge was running at 20 to 26
# requests a minute against that limit and burning its retries on self-inflicted
# 429s, which looked like exhausted daily quota and was not.
GROQ_REQUESTS_PER_MINUTE = int(os.getenv("GROQ_REQUESTS_PER_MINUTE", "25"))
GEMINI_REQUESTS_PER_MINUTE = int(os.getenv("GEMINI_REQUESTS_PER_MINUTE", "12"))
MIN_SECONDS_BETWEEN_CALLS = float(os.getenv("MIN_SECONDS_BETWEEN_CALLS", "1.0"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "900"))
# The judge needs far more headroom than the agent. Gemini 3.5 Flash spends 400
# to 500 thinking tokens before it writes anything and those count against
# maxOutputTokens, so a 900 budget truncated the verdict JSON mid-string and the
# parse failed on real cases. Gemini's free tier is generous on tokens per
# minute, so the fix is to stop starving it.
JUDGE_MAX_TOKENS = int(os.getenv("JUDGE_MAX_TOKENS", "2200"))
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "90"))

# ---------------------------------------------------------------- experiment
BRAND = os.getenv("BRAND", "")          # set after brand selection, see scripts/01_pick_brand.py
RANDOM_SEED = 20260910
GOLDEN_TARGET_N = 200                    # assignment asks for 150-250
RETRIEVAL_K = 4                          # historical exemplars shown to the agent
