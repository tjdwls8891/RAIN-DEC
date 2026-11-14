"""LLM 호출. 역할마다 모델과 사고량을 따로 두고, 모든 호출의 토큰·시간·값을 잰다.

키는 코드에 없다. 실행 환경이 요청에 붙인다(없으면 GEMINI_API_KEY를 읽는다).
누적 지출을 파일에 적고, 상한을 넘을 것 같으면 호출하지 않는다.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

KRW_PER_USD = 1500
# 100만 토큰당 달러 (입력, 출력·사고). 공식 가격표로 확인하지 못한 추정값이다. docs/36 참고.
PRICES = {
    "gemini-3-flash-preview": (0.50, 3.00),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.8-flash": (0.75, 3.75),
}
SPEND_FILE = Path(__file__).resolve().parent.parent / ".spend.json"
WORST_CALL_WON = 40


class LLMError(Exception):
    pass


class BudgetError(LLMError):
    pass


@dataclass
class Call:
    role: str
    model: str
    seconds: float = 0.0
    first: float = 0.0           # 첫 글자까지
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_think: int = 0
    won: float = 0.0
    prompt: str = ""
    output: Any = None


@dataclass
class Meter:
    calls: list[Call] = field(default_factory=list)

    def summary(self) -> dict:
        return {"호출": len(self.calls), "입력": sum(c.tokens_in for c in self.calls),
                "출력": sum(c.tokens_out for c in self.calls), "사고": sum(c.tokens_think for c in self.calls),
                "추정 비용(원)": round(sum(c.won for c in self.calls), 2)}


def spent() -> float:
    return json.loads(SPEND_FILE.read_text())["won"] if SPEND_FILE.exists() else 0.0


class FakeBackend:
    """시험용. 역할별로 정해 둔 답(또는 프롬프트를 받아 답을 내는 함수)을 돌려준다."""

    def __init__(self, script: dict[str, Any]):
        self.script = script
        self.seen: list[Call] = []

    def generate(self, role: str, system: str, prompt: str, schema: dict | None = None,
                 on_text: Callable[[str], None] | None = None) -> Call:
        out = self.script.get(role)
        if callable(out):
            out = out(prompt, schema)
        if isinstance(out, Exception):
            raise out
        if on_text and isinstance(out, str):
            on_text(out)
        c = Call(role, "fake", prompt=system + "\n" + prompt, output=out)
        self.seen.append(c)
        return c


class GeminiBackend:
    """Gemini API (REST, 흘려 받기)."""

    URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:streamGenerateContent?alt=sse"

    def __init__(self, models: dict[str, str], thinking: dict[str, str] | None = None,
                 cap_won: float = 1500, timeout: float = 60, retries: int = 2):
        self.models, self.thinking = models, thinking or {}
        self.cap, self.timeout, self.retries = cap_won, timeout, retries

    def generate(self, role: str, system: str, prompt: str, schema: dict | None = None,
                 on_text: Callable[[str], None] | None = None) -> Call:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return self._once(role, system, prompt, schema, on_text)
            except BudgetError:
                raise
            except LLMError as e:               # 과부하, 끊김, 깨진 꼴: 간격을 늘리며 다시
                last = e
                time.sleep(1.5 * (attempt + 1))
        raise LLMError(f"{role}: {last}")

    def _once(self, role, system, prompt, schema, on_text) -> Call:
        import requests
        if spent() + WORST_CALL_WON > self.cap:
            raise BudgetError(f"지출 상한에 닿았다: {spent():.0f}원 / {self.cap}원")
        model = self.models[role]
        gen: dict = {"maxOutputTokens": 4000}
        if schema is not None:
            gen["responseMimeType"] = "application/json"
            gen["responseSchema"] = schema
        if self.thinking.get(role):
            gen["thinkingConfig"] = {"thinkingLevel": self.thinking[role]}
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": gen}
        t0 = time.monotonic()
        try:
            r = requests.post(self.URL.format(m=model), json=body, stream=True, timeout=self.timeout,
                              headers={"x-goog-api-key": os.environ.get("GEMINI_API_KEY", "placeholder")})
        except requests.RequestException as e:
            raise LLMError(f"연결 실패: {e}") from e
        if r.status_code != 200:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
        text, first, usage, finish = "", 0.0, {}, None
        for raw in r.iter_lines():               # 바이트로 읽는다
            line = raw.decode("utf-8")
            if not line.startswith("data: "):
                continue
            d = json.loads(line[6:])
            usage = d.get("usageMetadata", usage)
            for cand in d.get("candidates", []):
                finish = cand.get("finishReason", finish)
                for p in cand.get("content", {}).get("parts", []):
                    if p.get("text") and not p.get("thought"):
                        first = first or time.monotonic() - t0
                        text += p["text"]
                        if on_text and schema is None:
                            on_text(p["text"])
        tin, tout, tth = (usage.get(k, 0) for k in ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount"))
        pin, pout = PRICES.get(model, (1.0, 6.0))
        won = (tin * pin + (tout + tth) * pout) / 1e6 * KRW_PER_USD
        SPEND_FILE.write_text(json.dumps({"won": spent() + won}))
        if not text:
            raise LLMError(f"빈 응답 (끝난 이유: {finish})")
        out: Any = text
        if schema is not None:
            try:
                out = json.loads(text)
            except json.JSONDecodeError as e:
                raise LLMError("꼴이 깨진 답") from e
        return Call(role, model, time.monotonic() - t0, first, tin, tout, tth, won, system + "\n" + prompt, out)
