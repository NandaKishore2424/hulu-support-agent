"""One LLM entry point for the whole project.

Three things this file exists to guarantee:

1. Every call is cached to disk by a hash of its full input. Re-running the
   evaluation costs nothing and returns byte-identical results, which is what
   makes the headline numbers in the report reproducible by a grader who has no
   API key at all.
2. Free-tier rate limits are respected by self-throttling instead of by
   absorbing 429s, with Groq -> Gemini failover when Groq's daily cap is hit.
3. Call volume is counted, so the report can state the real cost of a run.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from . import config as C


class QuotaExhausted(RuntimeError):
    """A per-day allowance is gone, so retrying inside this run cannot help.

    Groq enforces a tokens-per-day ceiling that appears in no response header:
    x-ratelimit-* reports only the per-minute token bucket and the request count,
    both of which read healthy while the daily budget is finished. The limit
    surfaces only in the body of a 429. Retrying it burns the retry ladder and
    then dies with a truncated error, which is exactly how three runs in this
    project failed before the cause was found. Raising a distinct error makes the
    wall legible and stops the run instead of hiding it.
    """


class CacheMiss(RuntimeError):
    """Raised in offline mode when a prompt has never been run before."""


@dataclass
class Usage:
    calls_served_from_cache: int = 0
    calls_to_groq: int = 0
    calls_to_gemini: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    errors: list[str] = field(default_factory=list)
    # Which model actually answered, cache hits included. The report states the
    # share served by the emergency model rather than the intended agent.
    served_by: Counter = field(default_factory=Counter)

    def summary(self) -> dict:
        return {
            "cache_hits": self.calls_served_from_cache,
            "groq_calls": self.calls_to_groq,
            "gemini_calls": self.calls_to_gemini,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "errors": len(self.errors),
            "served_by": dict(self.served_by),
        }


USAGE = Usage()

# Offline is the default so that an accidental full re-run cannot silently burn
# a day's quota. scripts pass live=True explicitly, or export HIVER_LIVE=1.
def _live_default() -> bool:
    return os.getenv("HIVER_LIVE", "0") == "1"


_last_call_at = 0.0
# (timestamp, tokens) for calls in the last 60s, per provider.
_recent: dict[str, list[tuple[float, int]]] = {"groq": [], "gemini": []}


def _estimate_tokens(system: str, user: str, max_tokens: int) -> int:
    """Reserve a slot in the budget before the call, at four characters a token.

    The completion length is unknown up front, so a slice of max_tokens is
    reserved. Reserving all of it wastes most of the quota: a reply plus its
    reasoning runs a few hundred tokens against a limit set far higher, and the
    over-reservation cut sustained throughput to roughly one call a minute in
    testing. The reservation is replaced with the provider's real count by
    _reconcile as soon as the response arrives.
    """
    return (len(system) + len(user)) // 4 + min(max_tokens // 2, 300)


def _reconcile(provider: str, actual_tokens: int) -> None:
    """Swap the reserved estimate for what the call actually cost."""
    window = _recent.get(provider)
    if window and actual_tokens > 0:
        ts, _ = window[-1]
        window[-1] = (ts, actual_tokens)


def _budget(provider: str) -> int:
    return C.GROQ_TOKENS_PER_MINUTE if provider == "groq" else C.GEMINI_TOKENS_PER_MINUTE


def _request_cap(provider: str) -> int:
    return (C.GROQ_REQUESTS_PER_MINUTE if provider == "groq"
            else C.GEMINI_REQUESTS_PER_MINUTE)


def _throttle(provider: str = "groq", tokens: int = 0) -> None:
    """Hold the caller until this call fits inside the provider's rolling budget."""
    global _last_call_at
    window = _recent.setdefault(provider, [])
    budget = _budget(provider)
    cap = _request_cap(provider)
    while True:
        now = time.time()
        window[:] = [(t, n) for t, n in window if now - t < 60.0]
        used = sum(n for _, n in window)
        over_tokens = used + tokens > budget
        over_requests = len(window) >= cap
        if not window or (not over_tokens and not over_requests):
            break
        # Sleep only until enough of the window has aged out to admit this call,
        # rather than always waiting for the oldest entry. Waiting on the oldest
        # entry regardless leaves the budget idle for most of each minute.
        need_tokens = used + tokens - budget
        release_at = window[0][0]
        if over_tokens:
            freed = 0
            for ts, n in window:
                freed += n
                release_at = ts
                if freed >= need_tokens:
                    break
        if over_requests:
            release_at = max(release_at, window[len(window) - cap][0])
        time.sleep(min(max(60.5 - (now - release_at), 0.05), 30.0))
    wait = C.MIN_SECONDS_BETWEEN_CALLS - (time.time() - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _last_call_at = time.time()
    window.append((time.time(), tokens))


def _cache_path(key: dict) -> Path:
    blob = json.dumps(key, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]
    return C.CACHE_DIR / f"{digest}.json"


_DAILY_MARKERS = ("tokens per day", "TPD", "PerDayPerProject", "requests per day", "RPD")


def _is_daily_cap(body: str) -> bool:
    return any(m in body for m in _DAILY_MARKERS)


def _daily_cap_message(body: str) -> str:
    """Pull the provider's own sentence out of the 429 so the operator sees it."""
    try:
        msg = json.loads(body).get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        msg = ""
    return ("daily provider allowance exhausted, so this run cannot continue: "
            + (msg[:400] if msg else body[:300])
            + "\n\nProgress already written to disk is kept and cached, so re-running "
              "after the reset resumes rather than repeats.")


def _post_with_retry(client: httpx.Client, url: str, **kw) -> httpx.Response:
    """Retry on 429 and 5xx. Honours Retry-After when the server sends one."""
    last = None
    for attempt in range(C.MAX_RETRIES):
        resp = client.post(url, **kw)
        if resp.status_code < 400:
            return resp
        last = f"{resp.status_code} {resp.text[:300]}"
        if resp.status_code == 429 and _is_daily_cap(resp.text):
            raise QuotaExhausted(_daily_cap_message(resp.text))
        retryable = resp.status_code == 429 or resp.status_code >= 500
        if not retryable:
            raise RuntimeError(f"non-retryable LLM error: {last}")
        delay = float(resp.headers.get("retry-after", 0)) or (2**attempt + random.random())
        time.sleep(min(delay, 65))
    raise RuntimeError(f"exhausted retries: {last}")


def _call_groq(system: str, user: str, model: str, temperature: float,
               max_tokens: int, json_mode: bool) -> tuple[str, dict]:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # reasoning_effort is a gpt-oss parameter. Sending it to Qwen made it spend
    # its whole budget thinking and return an empty completion, which Groq
    # rejects with a 400 json_validate_failed rather than a quota error, so the
    # failure looks nothing like its cause.
    if model.startswith("openai/gpt-oss"):
        payload["reasoning_effort"] = C.AGENT_REASONING_EFFORT
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {C.GROQ_API_KEY}"}
    with httpx.Client(timeout=C.REQUEST_TIMEOUT) as client:
        _throttle("groq", _estimate_tokens(system, user, max_tokens))
        resp = _post_with_retry(client, f"{C.GROQ_BASE}/chat/completions",
                                json=payload, headers=headers)
    body = resp.json()
    text = body["choices"][0]["message"]["content"]
    usage = body.get("usage", {})
    _reconcile("groq", int(usage.get("total_tokens", 0)))
    return text, usage


def _call_gemini(system: str, user: str, model: str, temperature: float,
                 max_tokens: int, json_mode: bool) -> tuple[str, dict]:
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temperature,
                             "maxOutputTokens": max_tokens},
    }
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"
    url = f"{C.GEMINI_BASE}/models/{model}:generateContent"
    with httpx.Client(timeout=C.REQUEST_TIMEOUT) as client:
        _throttle("gemini", _estimate_tokens(system, user, max_tokens))
        resp = _post_with_retry(client, url, json=payload,
                                headers={"x-goog-api-key": C.GEMINI_API_KEY})
    body = resp.json()
    cand = body["candidates"][0]
    text = "".join(p.get("text", "") for p in cand["content"]["parts"])
    um = body.get("usageMetadata", {})
    usage = {"prompt_tokens": um.get("promptTokenCount", 0),
             "completion_tokens": um.get("candidatesTokenCount", 0)}
    _reconcile("gemini", int(um.get("totalTokenCount", 0)))
    return text, usage


def complete(system: str, user: str, *, provider: str = "groq",
             model: str | None = None, temperature: float = 0.0,
             max_tokens: int = C.DEFAULT_MAX_TOKENS, json_mode: bool = False,
             live: bool | None = None, allow_failover: bool = True) -> str:
    """Return model text for one prompt, from cache when we have seen it before.

    provider selects the vendor; 'groq' is the agent, 'gemini' is the judge.
    """
    if live is None:
        live = _live_default()
    model = model or (C.AGENT_MODEL if provider == "groq" else C.JUDGE_MODEL)
    key = {"provider": provider, "model": model, "system": system, "user": user,
           "temperature": temperature, "max_tokens": max_tokens, "json": json_mode}
    path = _cache_path(key)

    if path.exists():
        rec = json.loads(path.read_text())
        USAGE.calls_served_from_cache += 1
        USAGE.served_by[rec.get("served_by", "unknown")] += 1
        return rec["text"]

    if not live:
        raise CacheMiss(
            "prompt not in cache and offline mode is on. Re-run with HIVER_LIVE=1 "
            "to call the API, or use the committed cache to reproduce reported results."
        )

    attempts: list[tuple[str, str]] = [(provider, model)]
    if allow_failover and provider == "groq":
        attempts.append(("groq", C.AGENT_MODEL_FALLBACK))
        attempts.append(("gemini", C.EMERGENCY_MODEL))

    last_error = None
    for prov, mdl in attempts:
        try:
            fn = _call_groq if prov == "groq" else _call_gemini
            text, usage = fn(system, user, mdl, temperature, max_tokens, json_mode)
        except QuotaExhausted:
            # A daily allowance is gone. Every later attempt on the same provider
            # is doomed and the caller needs to stop the whole run, so this must
            # propagate rather than be folded into "all providers failed". Without
            # this the loop kept calling a capped model once per item, turning one
            # clear stop into hundreds of identical failures.
            raise
        except Exception as exc:                      # noqa: BLE001 - recorded, then failover
            last_error = f"{prov}/{mdl}: {exc}"
            USAGE.errors.append(last_error)
            continue
        if prov == "groq":
            USAGE.calls_to_groq += 1
        else:
            USAGE.calls_to_gemini += 1
        USAGE.served_by[f"{prov}/{mdl}"] += 1
        USAGE.prompt_tokens += usage.get("prompt_tokens", 0)
        USAGE.completion_tokens += usage.get("completion_tokens", 0)
        # Cache under the requested key so a later run hits regardless of which
        # provider actually answered; served_by records the truth for the report.
        path.write_text(json.dumps(
            {"text": text, "served_by": f"{prov}/{mdl}", "key": key}, ensure_ascii=False))
        return text
    raise RuntimeError(f"all providers failed. last error: {last_error}")


def parse_json(text: str) -> dict:
    """Models sometimes wrap JSON in prose or fences. Recover the object."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text[4:] if text.lower().startswith("json") else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise
