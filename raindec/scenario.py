"""시나리오 읽기와 세션 개설.

공용 사전 + 시나리오(정의의 수정·추가, 개체, 사실, 변수) + 변수 값 결정 = 첫 사건 → 세계 장부
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import yaml

from .conditions import evaluate, parse_atom
from .ledger import Event, Ledger, LOC

COMMON = Path(__file__).with_name("common.yaml")


def parse_fact(text: str) -> dict:
    """ "위치(강호민 → 창가) = 곁에" → set 연산."""
    a = parse_atom(text)
    if a.get("op") != "=":
        raise ValueError(f"사실은 '속성(주체) = 값' 꼴로 쓴다: {text!r}")
    return {"op": "set", "attr": a["attr"], "subj": a["subj"], "obj": a["obj"], "value": _value(a["rhs"])}


def _value(text: str) -> Any:
    text = text.strip()
    if text.startswith("[") or text.startswith('"'):
        return yaml.safe_load(text)
    try:
        return int(text)
    except ValueError:
        return text


def load(path: str | Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    common = yaml.safe_load(COMMON.read_text(encoding="utf-8"))
    data["정의"] = {**common["정의"], **(data.get("정의") or {})}
    data["규칙"] = common.get("규칙", []) + (data.get("규칙") or [])
    data["유형"] = {**common.get("유형", {}), **(data.get("유형") or {})}
    data["버팀값"] = {**common.get("버팀값", {}), **(data.get("버팀값") or {})}
    data["시간등급"] = data.get("시간등급") or common.get("시간등급", {})
    data["맞섬"] = {**common.get("맞섬", {}), **(data.get("맞섬") or {})}
    data["가이드"] = {"사람 일반": common.get("가이드", ""), "세계관": data.get("가이드", "")}
    return data


def open_session(scn: dict, seed: int | None = None) -> tuple[Ledger, dict]:
    """세션을 연다. 변수 값을 정해 유일한 세계 상태 하나를 만든다."""
    rng = random.Random(seed)
    led = Ledger(scn["정의"])
    changes: list[dict] = []
    for ent, body in (scn.get("개체") or {}).items():
        changes.append({"op": "entity", "id": ent, "tags": body.get("표지", [])})
        for text in body.get("사실", []):
            changes.append(parse_fact(text.replace("이것", ent)))
    for text in scn.get("사실") or []:
        changes.append(parse_fact(text))
    led.append(Event(time=scn.get("시작", {}).get("시각", 0), kind="개설", summary="세계의 초기 상태", changes=changes))

    chosen: dict[str, str] = {}
    var_changes: list[dict] = []
    for name, var in (scn.get("변수") or {}).items():
        ok = []
        for cand in var["후보"]:
            if "제약" in var and evaluate(var["제약"], led, {"값": cand}) is False:
                continue
            ok.append(cand)
        if not ok:
            raise ValueError(f"변수 {name}: 제약을 만족하는 후보가 없다")
        chosen[name] = rng.choice(ok)
        for text in var.get("적용", []):
            var_changes.append(parse_fact(text.replace("{값}", chosen[name])))
    if var_changes:
        led.append(Event(time=led.now, kind="개설", summary="변수 결정", changes=var_changes, detail={"변수": chosen}))

    know: list[dict] = []
    for holder, texts in (scn.get("시야") or {}).items():
        for text in texts:
            know.append({**parse_fact(text), "op": "know", "holder": holder, "source": "원래 아는 것"})
    for who in [e for e in led.entities if led.has_tag(e, "인물")]:
        know.extend(perceive_scene(led, who))
    led.append(Event(time=led.now, kind="개설", summary="처음 아는 것", changes=know))
    return led, chosen


# 위치의 방식은 자연어다("삿갓 쓴 사내의 맞은편에 앉아", "손에 쥐고 목에 겨눈 채"). 목록에서 고르지 않는다.
# 코드가 방식의 글에서 읽어야 하는 것은 둘뿐이다: 무언가의 속에 있는가, 지닌 이가 감춰 지니고 있는가.
def is_inside(how: str) -> bool:
    return any(k in (how or "") for k in ("안", "속"))


def is_concealed(how: str) -> bool:
    return any(k in (how or "") for k in ("품", "속", "안", "주머니", "소매", "숨", "감춰", "감추"))


def in_plain_sight(led: Ledger, ent: str, who: str) -> bool:
    """ent가 who의 눈에 그냥 보이는 자리에 있는가. 닫힌 것 속, 남의 품속, 숨겨진 것은 아니다."""
    cur = ent
    while True:
        if led.get("숨김", cur) == "참":
            return False
        loc = led.where(cur)
        if loc is None or led.has_tag(cur, "장소"):
            return True
        parent, how = loc
        if led.has_tag(parent, "인물"):
            if parent != who and is_concealed(how):
                return False
        elif not (led.has_tag(parent, "장소") or led.has_tag(parent, "지점")):
            if is_inside(how) and led.get("열림", parent) != "참":   # 닫힌 서랍 속, 술독 속
                return False
        cur = parent


def perceive_scene(led: Ledger, who: str) -> list[dict]:
    """명백한 지각: 같은 장소에서 그냥 보이는 것의 겉으로 드러난 사실. (경계 사례는 심판이 정한다)"""
    place = led.place_of(who)
    if place is None:
        return []
    out = []
    for ent in [place] + led.present_in(place):
        if not in_plain_sight(led, ent, who):
            continue
        for f in led.facts_about(ent):
            if f.subj != ent or not led.visible(f.attr):
                continue
            out.append({"op": "know", "holder": who, "attr": f.attr, "subj": f.subj,
                        "obj": f.obj, "value": f.value, "source": "직접 봄"})
    return out
