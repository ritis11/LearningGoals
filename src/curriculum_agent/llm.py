"""Thin Anthropic client wrapper: structured-output calls, web search, usage accounting.

Sonnet 5 notes: never set temperature/top_p (rejected); adaptive thinking is on by
default. All structured outputs go through messages.parse() with a pydantic model.
"""

import time

from anthropic import Anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

from . import config

load_dotenv('.env')


class LLM:
    """One instance per pipeline run; accumulates usage for run_meta."""

    def __init__(self) -> None:
        self._client = Anthropic()
        self.calls: list[dict] = []

    # --- structured output -----------------------------------------------------
    def parse(
        self,
        *,
        stage: str,
        model: str,
        system: str,
        user: str,
        output_model: type[BaseModel],
        max_tokens: int = 4096,
    ) -> BaseModel:
        t0 = time.perf_counter()
        resp = self._client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=output_model,
        )
        self._record(stage, model, resp, time.perf_counter() - t0)
        return resp.parsed_output

    # --- plain text with server-side web search ---------------------------------
    def text_with_web_search(
        self,
        *,
        stage: str,
        model: str,
        system: str,
        user: str,
        max_uses: int = config.WEB_SEARCH_MAX_USES,
        max_tokens: int = 2048,
    ) -> str:
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": max_uses}]
        messages: list[dict] = [{"role": "user", "content": user}]
        while True:
            t0 = time.perf_counter()
            resp = self._client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=tools,
            )
            self._record(stage, model, resp, time.perf_counter() - t0)
            if resp.stop_reason == "pause_turn":  # server tool loop paused; resume
                messages = messages[:1] + [{"role": "assistant", "content": resp.content}]
                continue
            break
        return "".join(b.text for b in resp.content if b.type == "text")

    # --- accounting ---------------------------------------------------------------
    def _record(self, stage: str, model: str, resp, seconds: float) -> None:
        u = resp.usage
        searches = getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0) or 0
        in_price, out_price = config.PRICES_PER_MTOK.get(model, (0.0, 0.0))
        cost = (
            u.input_tokens / 1e6 * in_price
            + u.output_tokens / 1e6 * out_price
            + searches * config.WEB_SEARCH_PRICE_PER_CALL
        )
        self.calls.append(
            {
                "stage": stage,
                "model": model,
                "seconds": round(seconds, 2),
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "cache_read_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
                "web_searches": searches,
                "cost_usd": round(cost, 6),
            }
        )

    @property
    def total_cost_usd(self) -> float:
        return round(sum(c["cost_usd"] for c in self.calls), 4)
