"""LLM providers behind one interface: structured parse(), web-search text, usage accounting.

Two providers, selected per run (--provider / CURRICULUM_PROVIDER):
- anthropic: Haiku 4.5 (fast) + Sonnet 5 (smart), structured outputs via messages.parse,
  server-side web_search tool. Sonnet 5 notes: never set temperature (rejected);
  adaptive thinking shares the max_tokens budget with the output.
- gemini: flash models via the REST generateContent API (no SDK dependency),
  structured outputs via responseJsonSchema, google_search grounding for web search.
"""

import json
import os
import re
import time

import requests
from anthropic import Anthropic
from pydantic import BaseModel, ValidationError

from . import config

_PARSE_TOKEN_CEILING = 16000  # anthropic non-streaming max before SDK timeout guards kick in


class BaseLLM:
    """Shared usage accounting; subclasses implement parse() and text_with_web_search()."""

    provider: str = ""

    def __init__(self) -> None:
        models = config.PROVIDER_MODELS[self.provider]
        self.model_fast: str = models["fast"]
        self.model_smart: str = models["smart"]
        self.calls: list[dict] = []

    def _log(self, stage: str, model: str, seconds: float, input_tokens: int,
             output_tokens: int, cache_read: int = 0, searches: int = 0) -> None:
        in_price, out_price = config.PRICES_PER_MTOK.get(model, (0.0, 0.0))
        cost = (
            input_tokens / 1e6 * in_price
            + output_tokens / 1e6 * out_price
            + searches * config.WEB_SEARCH_PRICE_PER_CALL[self.provider]
        )
        self.calls.append({
            "stage": stage, "provider": self.provider, "model": model,
            "seconds": round(seconds, 2), "input_tokens": input_tokens,
            "output_tokens": output_tokens, "cache_read_tokens": cache_read,
            "web_searches": searches, "cost_usd": round(cost, 6),
        })

    @property
    def total_cost_usd(self) -> float:
        return round(sum(c["cost_usd"] for c in self.calls), 4)


# --- Anthropic -------------------------------------------------------------------

class AnthropicLLM(BaseLLM):
    provider = "anthropic"

    def __init__(self) -> None:
        super().__init__()
        self._client = Anthropic()

    def parse(self, *, stage: str, model: str, system: str, user: str,
              output_model: type[BaseModel], max_tokens: int = 4096,
              effort: str | None = None) -> BaseModel:
        # Sonnet 5's adaptive thinking spends from the same max_tokens budget as the
        # output JSON. Truncation shows up two ways (both observed live): the SDK
        # returns parsed_output=None, or raises ValidationError on the cut-off JSON.
        # Self-heal once: token ceiling + one effort step down (less thinking = more
        # room for output), then fail loudly.
        step_down = {"high": "medium", "medium": "low", "low": "low", None: "medium"}
        ladder = [(max_tokens, effort), (_PARSE_TOKEN_CEILING, step_down[effort])]
        if model != self.model_smart:  # effort unsupported on Haiku 4.5
            ladder = [(t, None) for t, _ in ladder]

        failure = ""
        for i, (tokens, eff) in enumerate(dict.fromkeys(ladder)):
            kwargs = {"output_config": {"effort": eff}} if eff else {}
            t0 = time.perf_counter()
            try:
                resp = self._client.messages.parse(
                    model=model,
                    max_tokens=tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    output_format=output_model,
                    **kwargs,
                )
            except ValidationError as e:
                failure = f"truncated JSON at max_tokens={tokens}, effort={eff}: {e}"
                print(f"  [{stage}] output truncated (attempt {i + 1}); retrying tighter")
                continue
            u = resp.usage
            self._log(stage, model, time.perf_counter() - t0, u.input_tokens,
                      u.output_tokens, getattr(u, "cache_read_input_tokens", 0) or 0)
            if resp.parsed_output is not None:
                return resp.parsed_output
            failure = f"stop_reason={resp.stop_reason} at max_tokens={tokens}, effort={eff}"
            if resp.stop_reason != "max_tokens":
                break
        raise RuntimeError(f"[{stage}] no parseable {output_model.__name__} ({failure})")

    def text_with_web_search(self, *, stage: str, model: str, system: str, user: str,
                             max_uses: int = config.WEB_SEARCH_MAX_USES,
                             max_tokens: int = 2048, effort: str = "low") -> str:
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": max_uses}]
        messages: list[dict] = [{"role": "user", "content": user}]
        while True:
            t0 = time.perf_counter()
            resp = self._client.messages.create(
                model=model, max_tokens=max_tokens, system=system,
                messages=messages, tools=tools, output_config={"effort": effort},
            )
            u = resp.usage
            searches = getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0) or 0
            self._log(stage, model, time.perf_counter() - t0, u.input_tokens,
                      u.output_tokens, getattr(u, "cache_read_input_tokens", 0) or 0, searches)
            if resp.stop_reason == "pause_turn":  # server tool loop paused; resume
                messages = messages[:1] + [{"role": "assistant", "content": resp.content}]
                continue
            break
        return "".join(b.text for b in resp.content if b.type == "text")


# --- Gemini (REST, no SDK) -----------------------------------------------------------

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# effort -> thinkingBudget (tokens). None/high = dynamic (API default for flash).
_THINKING_BUDGET = {"low": 0, "medium": 2048}


class GeminiLLM(BaseLLM):
    provider = "gemini"

    def __init__(self) -> None:
        super().__init__()
        self._api_key = os.environ.get("GEMINI_API_KEY", "")
        if not self._api_key:
            raise RuntimeError("GEMINI_API_KEY is not set (put it in .env)")

    def _generate(self, stage: str, model: str, body: dict) -> dict:
        t0 = time.perf_counter()
        for attempt in range(3):
            r = requests.post(
                _GEMINI_URL.format(model=model),
                headers={"Content-Type": "application/json", "X-goog-api-key": self._api_key},
                json=body, timeout=300,
            )
            if r.status_code in (429, 503) and attempt < 2:  # rate limit: honor retryDelay
                m = re.search(r'"retryDelay":\s*"(\d+)', r.text)
                delay = int(m.group(1)) if m else 15 * (attempt + 1)
                print(f"  [{stage}] gemini {r.status_code}; retrying in {delay}s")
                time.sleep(min(delay, 60))
                continue
            break
        if r.status_code != 200:
            raise requests.HTTPError(
                f"gemini {r.status_code}: {r.text[:400]}", response=r)
        data = r.json()
        u = data.get("usageMetadata", {})
        cand = (data.get("candidates") or [{}])[0]
        searches = len((cand.get("groundingMetadata") or {}).get("webSearchQueries") or [])
        self._log(stage, model, time.perf_counter() - t0,
                  u.get("promptTokenCount", 0),
                  u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0),
                  u.get("cachedContentTokenCount", 0), searches)
        return data

    @staticmethod
    def _text(data: dict) -> str:
        cand = (data.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text:
            raise RuntimeError(f"gemini returned no text (finishReason="
                               f"{cand.get('finishReason')})")
        return text

    def parse(self, *, stage: str, model: str, system: str, user: str,
              output_model: type[BaseModel], max_tokens: int = 4096,
              effort: str | None = None) -> BaseModel:
        schema = output_model.model_json_schema()
        gen_config: dict = {
            "responseMimeType": "application/json",
            "maxOutputTokens": max(max_tokens, 8192),
        }
        if effort in _THINKING_BUDGET:
            gen_config["thinkingConfig"] = {"thinkingBudget": _THINKING_BUDGET[effort]}

        def body(prompt: str, with_schema: bool) -> dict:
            gc = dict(gen_config)
            if with_schema:
                gc["responseJsonSchema"] = schema
            return {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": gc,
            }

        # attempt 1: native JSON-schema enforcement; on a 400 (older models reject
        # responseJsonSchema) fall back to schema-in-prompt. Either way, validate with
        # pydantic and retry once with the validation error quoted.
        prompt, with_schema = user, True
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                data = self._generate(stage, model, body(prompt, with_schema))
                return output_model.model_validate_json(self._text(data).strip())
            except requests.HTTPError as e:
                if with_schema and e.response is not None and e.response.status_code == 400:
                    with_schema = False
                    prompt = (f"{user}\n\nRespond ONLY with JSON matching this schema "
                              f"exactly:\n{json.dumps(schema)}")
                    last_err = e
                    continue
                raise
            except (ValidationError, RuntimeError) as e:
                last_err = e
                prompt = (f"{prompt}\n\nYour previous JSON response was invalid "
                          f"({str(e)[:300]}). Respond again with corrected, complete JSON.")
        raise RuntimeError(f"[{stage}] no parseable {output_model.__name__}: {last_err}")

    def text_with_web_search(self, *, stage: str, model: str, system: str, user: str,
                             max_uses: int = config.WEB_SEARCH_MAX_USES,
                             max_tokens: int = 2048, effort: str = "low") -> str:
        # google_search grounding; max_uses has no direct equivalent (prompt-bounded)
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"maxOutputTokens": max_tokens,
                                 "thinkingConfig": {"thinkingBudget": _THINKING_BUDGET["low"]}},
        }
        return self._text(self._generate(stage, model, body))


# --- factory ---------------------------------------------------------------------------

def make_llm(provider: str) -> BaseLLM:
    try:
        return {"anthropic": AnthropicLLM, "gemini": GeminiLLM}[provider]()
    except KeyError:
        raise ValueError(f"unknown provider {provider!r} (anthropic|gemini)") from None
