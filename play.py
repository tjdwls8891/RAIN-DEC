"""글자 화면에서 한 장면을 하거나, 정해 둔 선언들을 이어 돌려 시간과 값을 잰다.

  python play.py                  직접 플레이 (Gemini)
  python play.py --bench          정해 둔 선언을 한 세션으로 이어 돌리고 측정표를 낸다
  python play.py --fake           LLM 없이 흐름만 본다
"""
import argparse
import json
import random
import sys
from pathlib import Path

from raindec.engine import run_turn, status_board
from raindec.llm import FakeBackend, GeminiBackend, spent
from raindec.scenario import load, open_session

BENCH = [
    "창가 자리에서 객잔 안을 천천히 둘러본다.",
    "찻주전자의 식은 차를 한 모금 마시고, 나무 의자를 끌어다 앉는다.",
    "구석 탁자의 삿갓 쓴 사내를 곁눈으로 살핀다.",
    "계산대 쪽으로 가서 주모에게 묻는다. \"요즘 이 근방에 산적이 나온다던데, 들은 것 있소?\"",
    "계산대 뒤로 돌아가 뒷문을 열어 본다.",
    "계산대 아래 서랍을 열어 뒤진다.",
    "서랍 안에서 뒷문 열쇠를 찾아냈다! 그걸 챙긴다.",
    "주모에게 \"관아에서 나왔소. 뒷문 좀 엽시다.\"라고 말한다. (속으로는 들킬까 조마조마하다)",
    "삿갓 쓴 사내에게 다가가 맞은편에 앉으며 묻는다. \"형씨, 어디서 오셨소?\"",
    "검을 뽑아 삿갓 쓴 사내의 목에 겨눈다. \"누구 밑에서 일하는지 대라.\"",
    "나무 의자를 들어 뒷문 자물쇠를 내리쳐 부순다.",
    "찻주전자를 삿갓 쓴 사내 쪽으로 던진다.",
    "탁자를 뒤집어엎고 그 뒤에 몸을 숨긴다.",
    "발이 쳐진 문을 지나 창고로 들어간다.",
    "지금 내 상태가 어떻지?",
    "그걸로 저쪽을 어떻게 해 본다.",
]
FAKE = {
    "해석": lambda prompt, schema: {"행동": [{"유형": "관찰/조사/지식", "하려는_일": "주위를 살핀다", "대상": [], "가리킨_말": "", "말": ""}],
                                  "내면": "", "세계에_대한_단정": "", "모호함": False, "되물음": "", "되읽기": "주위를 살피려 한다."},
    "서술": "(가짜 서술) 등잔이 그을음을 낸다.",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="scenarios/객잔.yaml")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--bench", action="store_true")
    ap.add_argument("--model", default="gemini-3-flash-preview")
    ap.add_argument("--think-narrate", default="minimal")
    ap.add_argument("--cap", type=float, default=1500)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    backend = FakeBackend(FAKE) if a.fake else GeminiBackend(
        {"해석": a.model, "판단": a.model, "서술": a.model},
        {"해석": "minimal", "판단": "minimal", "서술": a.think_narrate}, cap_won=a.cap)
    scn = load(a.scenario)
    led, chosen = open_session(scn, a.seed)
    pc = scn["시작"]["PC"]
    rng = random.Random(a.seed)
    rows = []
    print(f"== {scn['이름']} ==  {status_board(led, pc)}")

    def press(card):
        parts = " ".join(f"{'+' if v >= 0 else '−'}{abs(v)}({n})" if i else f"{v}({n})" for i, (n, v) in enumerate(card["내역"]))
        print(f"\n  ┌ 판정  |  기준 {card['기준']} = {parts}  (둘의 합이 기준보다 작아야 한다)")
        print(f"  │ 되면: {card['되면']}\n  │ 탈이 나면: {card['탈이 나면']}")
        if not a.bench and not a.fake:
            input("  └ [굴린다 ⏎] ")

    def one(text):
        res = run_turn(led, backend, pc, text, scn, rng, press=press,
                       on_readback=lambda s: print(f"  ({s})"),
                       on_text=lambda s: (sys.stdout.write(s), sys.stdout.flush()))
        if res.kind != "턴":
            print(f"  [{res.kind}] {res.narration}")
        for c in res.checks:
            print(f"\n  └ 주사위 {c['주사위'][0]} + {c['주사위'][1]} = {c['합']}  (여유 {c['여유']}) → {c['정도']}")
        if res.board:
            print(f"\n  ▣ {res.board}")
        if res.filled:
            print(f"  [채운 것] {res.filled}")
        won = sum(c.won for c in res.calls)
        t = res.timing
        print(f"\n  [측정] 되읽기 {t.get('되읽기', 0):.1f}초 · 버튼 {t.get('버튼', 0):.1f}초 · 첫 글자 {t.get('첫 글자', 0):.1f}초 · 전체 {t.get('전체', 0):.1f}초 · "
              f"{won:.1f}원 · 호출 {'+'.join(c.role for c in res.calls)}" + (f"\n  [다루지 못함] {res.unhandled}" if res.unhandled else "")
              + (f"\n  [거부] {res.rejected}" if res.rejected else ""))
        rows.append({"선언": text, "종류": res.kind, "되읽기": res.readback, "서술": res.narration, "판정": res.checks,
                     "시간": t, "원": round(won, 2), "판단을 불렀나": res.judged, "다루지 못함": res.unhandled, "거부": res.rejected,
                     "호출": [{"역할": c.role, "초": round(c.seconds, 2), "입력": c.tokens_in, "출력": c.tokens_out,
                             "사고": c.tokens_think, "원": round(c.won, 2), "프롬프트": c.prompt, "답": c.output} for c in res.calls]})

    if a.bench:
        for text in BENCH:
            print(f"\n\n> {text}")
            one(text)
    else:
        while True:
            try:
                text = input("\n\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text in ("", "끝"):
                break
            one(text)
    turns = [r for r in rows if r["종류"] == "턴"]
    if turns:
        firsts = sorted(r["시간"]["첫 글자"] for r in turns)
        print(f"\n\n== 합계 == 턴 {len(turns)} · 첫 글자까지 중앙값 {firsts[len(firsts) // 2]:.1f}초, 최대 {firsts[-1]:.1f}초 · "
              f"턴당 {sum(r['원'] for r in rows) / len(rows):.1f}원 · 판단 없이 끝난 턴 {sum(not r['판단을 불렀나'] for r in turns)}/{len(turns)}"
              f" · 누적 지출(추정) {spent():.0f}원")
    print(status_board(led, pc))
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps({"변수": chosen, "턴": rows}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
