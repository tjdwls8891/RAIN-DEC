"""LLM 호출. 역할마다 모델을 다르게 둘 수 있고, 모든 호출의 토큰·시간·비용을 잰다."""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# 100만 토큰당 달러. 제3자 집계 값이며 공식 가격표로 확인하지 못했다. 실측 전 추정용.
PRICES = {
    "flash": (0.50, 3.00),
    "flash-lite": (0.25, 1.50),
    "pro": (2.00, 12.00),
}
KRW_PER_USD = 1400


@dataclass
class Call:
    role: str
    model: str
    seconds: float
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_think: int = 0
    prompt: str = ""
    output: Any = None
    key: str = ""            # 같은 역할의 호출을 구별한다 (인물:주모)

    @property
    def won(self) -> float:
        tier = "flash-lite" if "lite" in self.model else "pro" if "pro" in self.model else "flash"
        pin, pout = PRICES[tier]
        usd = (self.tokens_in * pin + (self.tokens_out + self.tokens_think) * pout) / 1_000_000
        return usd * KRW_PER_USD


@dataclass
class Meter:
    calls: list[Call] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "호출": len(self.calls),
            "입력 토큰": sum(c.tokens_in for c in self.calls),
            "출력 토큰": sum(c.tokens_out for c in self.calls),
            "사고 토큰": sum(c.tokens_think for c in self.calls),
            "추정 비용(원)": round(sum(c.won for c in self.calls), 2),
        }


class FakeBackend:
    """시험용. 역할별로 정해 둔 응답을 돌려준다."""

    def __init__(self, script: dict[str, Any] | Callable[[str, str], Any]):
        self.script = script
        self.seen: list[Call] = []

    async def generate(self, role: str, system: str, prompt: str, schema: dict | None = None,
                       key: str | None = None) -> Call:
        if callable(self.script):
            out = self.script(key or role, prompt)
        else:
            out = self.script.get(key or role, self.script.get(role))
        call = Call(role, "fake", 0.0, len(system + prompt) // 2, len(str(out)) // 2, 0,
                    system + "\n" + prompt, out, key or role)
        self.seen.append(call)
        return call


class GeminiBackend:
    """Gemini API. 모델 이름은 역할별로 지정한다."""

    def __init__(self, models: dict[str, str], thinking: dict[str, int] | None = None):
        from google import genai
        self._genai = genai
        self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", "placeholder"))
        self.models = models
        self.thinking = thinking or {}

    def list_models(self) -> list[str]:
        return [m.name for m in self.client.models.list()]

    async def generate(self, role: str, system: str, prompt: str, schema: dict | None = None,
                       key: str | None = None) -> Call:
        from google.genai import types
        cfg: dict[str, Any] = {"system_instruction": system}
        if schema is not None:
            cfg["response_mime_type"] = "application/json"
            cfg["response_json_schema"] = schema
        if role in self.thinking:
            cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=self.thinking[role])
        model = self.models[role]
        t0 = time.monotonic()
        resp = await self.client.aio.models.generate_content(
            model=model, contents=prompt, config=types.GenerateContentConfig(**cfg))
        dt = time.monotonic() - t0
        text = resp.text or ""
        out: Any = text
        if schema is not None:
            try:
                out = json.loads(text)
            except json.JSONDecodeError:
                out = None
        u = resp.usage_metadata
        return Call(role, model, dt, getattr(u, "prompt_token_count", 0) or 0,
                    getattr(u, "candidates_token_count", 0) or 0,
                    getattr(u, "thoughts_token_count", 0) or 0, system + "\n" + prompt, out, key or role)


async def gather(*aws):
    return await asyncio.gather(*aws)
