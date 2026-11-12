"""한 턴의 처리.

선언 → ① 심판 → ② 판정(코드) → ③ 진행(코드) → ④ 인물(병렬) → ⑤ 정리(코드) → ⑥ 서술자 → ⑦ 마감(코드)
설계: docs/10-턴-처리-흐름.md

정보 격리는 지시가 아니라 문맥으로 한다.
  심판   — 장면의 진실을 받는다.
  인물   — 자기 시야와 자기 자신에 대한 사실만 받는다.
  서술자 — PC가 지각한 것만 받는다.
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any

from .ledger import Event, Ledger, LedgerError, LOC, fact_text
from .llm import Call
from .scenario import _value, perceive_scene

# PC의 내면에 해당하는 속성. 마스터 쪽의 어떤 제안도 PC에 대해 이것을 정할 수 없다(주권).
INNER = {"기분", "성격", "목표", "비밀", "호감", "말투"}

# 판정 수치는 임시 값이다. 주사위 체계와 기준값 표는 판정 체계 설계에서 정한다.
BASE = {"쉬움": 75, "보통": 60, "어려움": 45, "매우 어려움": 30}
WEIGHT = {"약": 5, "중": 10, "강": 15}

OP = {"type": "object", "properties": {
    "연산": {"type": "string", "enum": ["사실", "개체", "제거"]},
    "속성": {"type": "string"}, "주체": {"type": "string"}, "대상": {"type": "string"},
    "값": {"type": "string"}, "표지": {"type": "array", "items": {"type": "string"}}},
    "required": ["연산", "주체"]}
OUTCOME = {"type": "object", "properties": {
    "PC지각": {"type": "string"}, "변화": {"type": "array", "items": OP}}, "required": ["PC지각", "변화"]}
REFEREE_SCHEMA = {"type": "object", "properties": {
    "세계밖": {"type": "boolean"}, "답": {"type": "string"},
    "행동": {"type": "array", "items": {"type": "object", "properties": {
        "유형": {"type": "string"}, "대상": {"type": "array", "items": {"type": "string"}},
        "수단": {"type": "string"}, "방식": {"type": "string"}, "의도": {"type": "string"},
        "발화": {"type": "string"}}, "required": ["유형"]}},
    "내면": {"type": "string"}, "소요_분": {"type": "integer"},
    "판정": {"type": "object", "properties": {
        "필요": {"type": "boolean"}, "명백": {"type": "string", "enum": ["", "성공", "실패"]},
        "능력": {"type": "string"}, "난이도": {"type": "string", "enum": list(BASE)},
        "요인": {"type": "array", "items": {"type": "object", "properties": {
            "근거": {"type": "string"}, "방향": {"type": "string", "enum": ["유리", "불리"]},
            "정도": {"type": "string", "enum": list(WEIGHT)}}, "required": ["근거", "방향", "정도"]}}},
        "required": ["필요"]},
    "귀결": {"type": "object", "properties": {"성공": OUTCOME, "실패": OUTCOME}, "required": ["성공", "실패"]},
    "지각": {"type": "array", "items": {"type": "object", "properties": {
        "누구": {"type": "string"}, "감각": {"type": "string"}, "내용": {"type": "string"}},
        "required": ["누구", "내용"]}}},
    "required": ["세계밖", "행동", "판정", "귀결"]}
PERSONA_SCHEMA = {"type": "object", "properties": {
    "속마음": {"type": "string"}, "기분": {"type": "string"},
    "겉행동": {"type": "string"}, "대사": {"type": "string"},
    "의도": {"type": "string"}, "PC와_다툼": {"type": "boolean"}},
    "required": ["속마음", "겉행동", "대사", "의도"]}

REFEREE_SYS = """너는 TRPG의 심판이다. 산문을 쓰지 않는다. 주사위를 굴리지 않는다. 수치를 계산하지 않는다.
플레이어의 선언을 행동으로 구조화하고, 판정을 설계하고, 성공과 실패 각각의 귀결을 미리 제안한다.

규칙
- 플레이어는 PC의 생각·말·행동·의도만 정한다. 세계에 대한 단정("~를 발견했다")은 시도("~를 찾는다")로 바꾼다.
- 결과가 뻔하면 판정.필요=false, 명백에 성공 또는 실패를 적는다. 불확실할 때만 판정한다.
- 요인의 근거는 아래 [장면의 진실]에 있는 사실을 그대로 가리킨다. 없는 사실을 근거로 들지 않는다.
- 변화는 [쓸 수 있는 속성]만 쓴다. 값이 등급이면 그 등급 중 하나만 쓴다. 개체 이름은 [장면의 진실]의 것을 그대로 쓴다.
- 장면에 없는 것을 건드리면, 있을 법한 경우에만 연산 "개체"로 먼저 만든 뒤 사실을 붙인다.
- PC의 기분·생각·의도는 어떤 변화로도 정하지 않는다.
- "PC지각"에는 PC가 보고 듣고 느낀 것만 적는다. PC가 알 수 없는 진실은 절대 적지 않는다.
- "지각"에는 장면의 다른 인물이 PC의 행동에서 무엇을 보고 들었는지 인물별로 적는다. PC의 속마음은 적지 않는다.
- 규칙 질문이나 진행에 대한 말이면 세계밖=true로 하고 "답"에 답한다."""

PERSONA_SYS = """너는 한 사람이다. 아래 [나]가 너 자신이고, [내가 아는 것]이 네가 아는 전부다.
거기 없는 것은 모른다. 모르는 것을 아는 척하지 않는다.
너는 네 목표와 성격대로 움직인다. 상대를 만족시킬 이유가 없다.
방금 지각한 일에 어떻게 반응할지 정한다. 결과를 확정하지 않는다. 네가 하려는 것만 정한다.
- 속마음: 한두 문장. 누구에게도 전달되지 않는다.
- 겉행동: 남이 볼 수 있는 몸짓과 행동만.
- 대사: 네 말투로. 말하지 않으면 빈 문자열.
- 의도: 다음에 하려는 것 한 문장."""

NARRATOR_SYS = """너는 소설의 서술자다. 아래 [재료]만으로 장면을 쓴다.
- 재료에 없는 사람, 물건, 출입구, 사건을 만들지 않는다. 빛·소리·냄새·촉감 같은 질감만 더할 수 있다.
- 주인공의 생각, 감정, 의도, 추가 행동을 쓰지 않는다. [주인공이 밝힌 내면]에 있는 것만 쓸 수 있다.
- 인물의 대사는 한 글자도 고치지 않고 넣는다.
- 주인공이 보고 듣고 느끼는 범위에서만 쓴다. 2인칭이나 이름 대신 "그"를 쓰지 말고 주인공의 이름을 쓴다.
- 한국어, 400~800자. 판정 수치나 규칙 용어를 쓰지 않는다. 마지막을 질문으로 끝내지 않는다."""


@dataclass
class TurnResult:
    narration: str
    out_of_world: bool = False
    check: dict = field(default_factory=dict)
    rejected: list[str] = field(default_factory=list)
    accepted: int = 0
    calls: list[Call] = field(default_factory=list)
    seconds: float = 0.0


def lines(items) -> str:
    return "\n".join(f"- {x}" for x in items) or "- (없음)"


def truth_scene(led: Ledger, pc: str) -> list[str]:
    """심판에게 주는 장면의 진실: PC가 있는 장소, 그 안의 모든 것, 이어진 통로 너머."""
    place = led.place_of(pc)
    ents = [place] + led.present_in(place)
    for e in list(ents):
        if led.has_tag(e, "통로"):
            ents += [p for p in (led.get("잇는다", e) or []) if p not in ents]
    out = []
    for e in ents:
        tags = ", ".join(sorted(led.entities.get(e, ())))
        out.append(f"[{e}] ({tags})")
        out += [f"  {f.text()}" for f in led.facts.values() if f.subj == e]
    return out


def persona_context(led: Ledger, who: str) -> tuple[list[str], list[str]]:
    me = [f.text() for f in led.facts.values() if f.subj == who]
    known = [b.text() for b in led.view(who) if b.subj != who]
    return me, known


def writable(led: Ledger) -> list[str]:
    out = []
    for name, d in led.definitions.items():
        g = d.get("값")
        out.append(f"{name}: {g}" if isinstance(g, list) else name)
    return out


def to_change(led: Ledger, op: dict, pc: str) -> dict:
    """심판의 제안 하나를 장부의 연산으로 바꾸고 검사한다. 통과하지 못하면 LedgerError."""
    kind, subj = op.get("연산"), op.get("주체")
    if not subj:
        raise LedgerError("주체가 없다")
    if kind == "개체":
        if subj in led.entities:
            raise LedgerError(f"이미 있는 개체: {subj}")
        return {"op": "entity", "id": subj, "tags": op.get("표지") or ["물건"]}
    attr, obj = op.get("속성"), op.get("대상") or None
    if not attr:
        raise LedgerError("속성이 없다")
    if subj == pc and attr in INNER:
        raise LedgerError(f"주권 침범: PC의 {attr}은(는) 플레이어만 정한다")
    if subj not in led.entities:
        raise LedgerError(f"없는 개체: {subj}")
    if attr == LOC and obj not in led.entities:
        raise LedgerError(f"없는 곳: {obj}")
    if kind == "제거":
        ch = {"op": "unset", "attr": attr, "subj": subj, "obj": obj}
    else:
        ch = {"op": "set", "attr": attr, "subj": subj, "obj": obj, "value": _value(str(op.get("값", "")))}
    led.check(ch)
    return ch


def roll_check(led: Ledger, pc: str, spec: dict, rng: random.Random) -> dict:
    if not spec.get("필요"):
        return {"판정": False, "결과": spec.get("명백") or "성공"}
    ability = led.get(spec.get("능력", ""), pc) if spec.get("능력") in led.definitions else None
    target = BASE.get(spec.get("난이도", "보통"), 60)
    if isinstance(ability, int):
        target += (ability - 10) * 2
    for f in spec.get("요인", []):
        target += WEIGHT.get(f.get("정도"), 0) * (1 if f.get("방향") == "유리" else -1)
    dice = rng.randint(1, 50) + rng.randint(1, 50)
    return {"판정": True, "기준": target, "주사위": dice, "결과": "성공" if dice <= target else "실패",
            "난이도": spec.get("난이도"), "요인": spec.get("요인", [])}


async def run_turn(led: Ledger, backend, pc: str, declaration: str, scn: dict,
                   rng: random.Random | None = None, last_narration: str = "") -> TurnResult:
    rng = rng or random.Random()
    loop = asyncio.get_event_loop()
    t0 = loop.time()
    calls: list[Call] = []
    work = Ledger.replay(led.definitions, led.events)     # 실패하면 원본은 그대로다

    # ① 심판
    prompt = (f"[시나리오 전제]\n{scn.get('전제', '')}\n\n[PC]\n{pc}\n\n[장면의 진실]\n" + "\n".join(truth_scene(work, pc))
              + f"\n\n[쓸 수 있는 속성]\n{lines(writable(work))}\n\n[플레이어의 선언]\n{declaration}")
    c = await backend.generate("심판", REFEREE_SYS, prompt, REFEREE_SCHEMA)
    calls.append(c)
    ref = c.output
    if not isinstance(ref, dict):
        raise RuntimeError("심판의 출력을 읽을 수 없다")
    if ref.get("세계밖"):
        return TurnResult(ref.get("답", ""), True, calls=calls, seconds=loop.time() - t0)

    # ② 판정
    check = roll_check(work, pc, ref.get("판정", {}), rng)
    outcome = ref["귀결"][check["결과"]]
    changes, rejected = [], []
    for op in outcome.get("변화", []):
        try:
            ch = to_change(work, op, pc)
            work.append(Event(work.now, "임시", changes=[ch]))   # 뒤의 제안이 앞의 것을 참조할 수 있게
            changes.append(ch)
        except LedgerError as e:
            rejected.append(f"{op} → {e}")

    # ③ 진행
    now = work.now + max(0, int(ref.get("소요_분") or 0))

    # ④ 인물 (병렬) — 각자 자기 시야만 받는다
    place = work.place_of(pc)
    npcs = [e for e in work.present_in(place) if work.has_tag(e, "인물") and e != pc]
    saw = {p.get("누구"): p for p in ref.get("지각", [])}

    async def persona(who: str) -> tuple[str, Call]:
        me, known = persona_context(work, who)
        seen = saw.get(who, {}).get("내용") or "(특별히 지각한 것이 없다)"
        p = f"[나]\n{lines(me)}\n\n[내가 아는 것]\n{lines(known)}\n\n[방금 지각한 것]\n{seen}"
        return who, await backend.generate("인물", PERSONA_SYS, p, PERSONA_SCHEMA, key=f"인물:{who}")

    reactions = dict(await asyncio.gather(*[persona(n) for n in npcs])) if npcs else {}
    calls += list(reactions.values())

    # ⑤ 정리
    shown = []
    for who, call in reactions.items():
        r = call.output if isinstance(call.output, dict) else {}
        mood = r.get("기분")
        if mood in (work.definitions.get("기분", {}).get("값") or []):
            ch = {"op": "set", "attr": "기분", "subj": who, "obj": None, "value": mood}
            work.append(Event(work.now, "임시", changes=[ch]))
            changes.append(ch)
        name = work.get("이름", who) or who
        if r.get("겉행동") or r.get("대사"):
            shown.append(f"{name}: {r.get('겉행동', '')}" + (f' 대사: "{r["대사"]}"' if r.get("대사") else ""))

    before = {(b.attr, b.subj, b.obj): b.value for b in work.view(pc)}
    know = [k for k in perceive_scene(work, pc) if before.get((k["attr"], k["subj"], k["obj"])) != k["value"]]
    newly = [fact_text(k["attr"], k["subj"], k["obj"], k["value"]) for k in know]

    # ⑥ 서술자 — PC가 지각한 것만 받는다
    senses = [b.text() for b in work.view(pc)
              if work.definitions.get(b.attr, {}).get("서술") or b.attr in ("조도", "소음")]
    material = (f"[어조]\n{scn.get('어조', '')}\n\n[주인공]\n{pc}\n\n[주인공의 선언]\n{declaration}\n\n"
                f"[주인공이 밝힌 내면]\n{ref.get('내면') or '(없음)'}\n\n"
                f"[행동의 결과]\n{outcome.get('PC지각', '')}\n\n[새로 지각한 것]\n{lines(newly)}\n\n"
                f"[다른 인물의 겉모습과 말]\n{lines(shown)}\n\n[주인공이 아는 장면]\n{lines(senses)}\n\n"
                f"[직전 서술]\n{last_narration or '(첫 장면)'}")
    n = await backend.generate("서술자", NARRATOR_SYS, f"[재료]\n{material}")
    calls.append(n)
    narration = n.output if isinstance(n.output, str) else ""

    # ⑦ 마감 — 이번 턴의 모든 변화를 사건 하나로 확정한다
    led.append(Event(time=now, kind="턴", actor=pc, summary=declaration, changes=changes + know,
                     perceived_by={pc: "직접", **{w: saw.get(w, {}).get("감각", "") for w in npcs}},
                     detail={"판정": check, "거부된 제안": rejected,
                             "속마음": {w: (c.output or {}).get("속마음") for w, c in reactions.items()
                                      if isinstance(c.output, dict)}}))
    return TurnResult(narration, False, check, rejected, len(changes), calls, loop.time() - t0)
