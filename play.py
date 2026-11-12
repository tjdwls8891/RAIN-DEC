"""터미널에서 한 장면을 플레이하거나, 정해 둔 선언들로 비용과 시간을 잰다.

  python play.py                      직접 플레이 (Gemini)
  python play.py --bench              정해 둔 선언 여섯 개를 돌리고 측정표를 낸다
  python play.py --models             쓸 수 있는 모델 이름을 본다
  python play.py --fake               LLM 없이 흐름만 확인한다
"""
import argparse
import asyncio
import json
import random

from raindec.llm import FakeBackend, GeminiBackend, Meter
from raindec.scenario import load, open_session
from raindec.turn import run_turn

BENCH = [
    "창가 자리에서 객잔 안을 천천히 둘러본다.",
    "주모에게 다가가 묻는다. \"요즘 이 근방에 산적이 나온다던데, 들은 것 있소?\"",
    "구석의 삿갓 쓴 사내를 곁눈으로 살핀다. 술을 안 마시는 게 수상하다고 생각한다.",
    "계산대 뒤로 돌아가 뒷문을 열어 본다.",
    "나는 계산대 서랍에서 뒷문 열쇠를 찾아냈다!",
    "삿갓 쓴 사내의 탁자에 마주 앉으며 검 손잡이에 손을 올린다. \"형씨, 어디서 오셨소?\"",
]
FAKE = {
    "심판": {"세계밖": False, "행동": [{"유형": "관찰"}], "내면": "", "소요_분": 1, "판정": {"필요": False, "명백": "성공"},
           "귀결": {"성공": {"PC지각": "특별한 것은 없다.", "변화": []}, "실패": {"PC지각": "", "변화": []}}, "지각": []},
    "인물": {"속마음": "…", "겉행동": "이쪽을 본다.", "대사": "", "의도": "지켜본다"},
    "서술자": "(가짜 서술) 등잔이 그을음을 낸다.",
}


def report(res, meter):
    for c in res.calls:
        meter.calls.append(c)
    if res.check.get("판정"):
        print(f"  [판정] {res.check['난이도']} 기준 {res.check['기준']} / 주사위 {res.check['주사위']} → {res.check['결과']}")
    for r in res.rejected:
        print(f"  [거부된 제안] {r}")
    won = sum(c.won for c in res.calls)
    parts = ", ".join(f"{c.key} {c.seconds:.1f}초" for c in res.calls)
    print(f"  [측정] {res.seconds:.1f}초, 약 {won:.1f}원, 반영 {res.accepted} / 거부 {len(res.rejected)}  ({parts})")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="scenarios/객잔.yaml")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--bench", action="store_true")
    ap.add_argument("--models", action="store_true")
    ap.add_argument("--referee", default="gemini-flash-latest")
    ap.add_argument("--persona", default="gemini-flash-lite-latest")
    ap.add_argument("--narrator", default="gemini-flash-latest")
    ap.add_argument("--log", default=None, help="호출 기록을 남길 파일(JSONL)")
    a = ap.parse_args()

    if a.models:
        print("\n".join(GeminiBackend({}).list_models()))
        return
    backend = FakeBackend(FAKE) if a.fake else GeminiBackend(
        {"심판": a.referee, "인물": a.persona, "서술자": a.narrator})
    scn = load(a.scenario)
    led, chosen = open_session(scn, a.seed)
    pc = scn["시작"]["PC"]
    rng, meter, last = random.Random(a.seed), Meter(), ""
    log = open(a.log, "w", encoding="utf-8") if a.log else None
    print(f"== {scn['이름']} ==  (PC: {pc})")

    async def one(text):
        nonlocal last
        res = await run_turn(led, backend, pc, text, scn, rng, last)
        print("\n" + res.narration + "\n")
        report(res, meter)
        if not res.out_of_world:
            last = res.narration
        if log:
            for c in res.calls:
                log.write(json.dumps({"선언": text, "역할": c.key, "모델": c.model, "초": round(c.seconds, 2),
                                      "입력": c.tokens_in, "출력": c.tokens_out, "사고": c.tokens_think,
                                      "프롬프트": c.prompt, "응답": c.output}, ensure_ascii=False) + "\n")

    if a.bench:
        for text in BENCH:
            print(f"\n> {text}")
            await one(text)
    else:
        while True:
            try:
                text = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text in ("", "끝"):
                break
            await one(text)
    s = meter.summary()
    turns = max(1, len({id(c) for c in meter.calls if c.role == "심판"}))
    print(f"\n== 합계 == {s}  / 턴당 약 {s['추정 비용(원)'] / turns:.1f}원")


if __name__ == "__main__":
    asyncio.run(main())
