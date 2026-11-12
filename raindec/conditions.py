"""조건 언어: 사실과 같은 모양으로 쓰는 조건을 세 값(참/거짓/모름)으로 계산한다.

설계: docs/14-조건-언어.md

조건의 모양
  "피로(이것) 이상 높음"                     낱개 조건
  ["...", "..."]                             모두
  {"모두": [...]} {"하나라도": [...]} {"아님": ...}
  {"어떤": "ㄱ", "표지": "인물", "조건": [...]}
  {"시야": "매복자", "조건": [...]}          그 마음이 아는 것에 대해 계산
"""
from __future__ import annotations

import re
from typing import Any

from .ledger import Ledger

COMPARE = ["이상", "이하", "초과", "미만", "포함", "≠", "="]
WORDS = {"=": "이다", "≠": "아니다", "이상": "이상이다", "이하": "이하이다",
         "초과": "보다 높다", "미만": "보다 낮다", "포함": "을(를) 포함한다"}
PREDICATES = {"같은 곳", "안에", "지닌다", "안다"}

_TERM = r"([^\s()]+(?: [^\s()]+)?)\(([^()]*)\)"
_ATOM = re.compile(rf"^{_TERM}\s*(?:(이상|이하|초과|미만|포함|≠|=)\s*(.+)|(있음|없음))?$")
_REF = re.compile(rf"^{_TERM}\s*(?:([+-])\s*(\d+)\s*(?:단계)?)?$")


class ConditionError(Exception):
    pass


def _args(text: str) -> list[str]:
    return [a.strip() for a in re.split(r"→|↔|,", text) if a.strip()]


_KNOWS = re.compile(r"^안다\(\s*(.+?)\s*,\s*«(.+)»\s*\)$")


def parse_atom(text: str) -> dict:
    k = _KNOWS.match(text.strip())
    if k:                                   # 명제를 품으므로 괄호가 겹친다
        return {"pred": "안다", "args": [k.group(1), k.group(2)]}
    m = _ATOM.match(text.strip())
    if not m:
        raise ConditionError(f"조건을 읽을 수 없다: {text!r}")
    name, args, op, rhs, exists = m.group(1), _args(m.group(2)), m.group(3), m.group(4), m.group(5)
    if name in PREDICATES:
        return {"pred": name, "args": args}
    if not 1 <= len(args) <= 2:
        raise ConditionError(f"주체와 대상은 하나씩만 쓴다: {text!r}")
    atom = {"attr": name, "subj": args[0], "obj": args[1] if len(args) > 1 else None}
    if exists:
        return {**atom, "op": exists}
    if not op:
        return {**atom, "op": "=", "rhs": "참", "bare": True}
    return {**atom, "op": op, "rhs": rhs.strip()}


class Scope:
    """지시어와 "어떤"으로 찾은 이름을 개체로 바꾼다."""

    def __init__(self, ledger: Ledger, bind: dict[str, str] | None = None):
        self.led = ledger
        self.bind = dict(bind or {})

    def resolve(self, name: str) -> str | None:
        if name in self.bind:
            return self.bind[name]
        this = self.bind.get("이것")
        if name == "이곳":
            return self.led.place_of(this) if this else None
        if name == "지닌 자":
            return self.led.holder_of(this) if this else None
        return name

    def child(self, name: str, ent: str) -> "Scope":
        return Scope(self.led, {**self.bind, name: ent})


def evaluate(cond: Any, ledger: Ledger, bind: dict[str, str] | None = None) -> bool | None:
    """참이면 True, 거짓이면 False, 모름이면 None."""
    return _eval(cond, Scope(ledger, bind), None)


def _eval(cond: Any, sc: Scope, viewer: str | None) -> bool | None:
    if isinstance(cond, str):
        return _eval_atom(parse_atom(cond), sc, viewer)
    if isinstance(cond, list):
        return _all([_eval(c, sc, viewer) for c in cond])
    if isinstance(cond, dict):
        if "모두" in cond:
            return _all([_eval(c, sc, viewer) for c in cond["모두"]])
        if "하나라도" in cond:
            return _any([_eval(c, sc, viewer) for c in cond["하나라도"]])
        if "아님" in cond:
            v = _eval(cond["아님"], sc, viewer)
            return None if v is None else not v
        if "어떤" in cond:
            return _any([_eval(cond.get("조건", []), sc.child(cond["어떤"], e), viewer)
                         for e in sc.led.entities if sc.led.has_tag(e, cond["표지"])])
        if "시야" in cond:
            who = sc.resolve(cond["시야"])
            return _eval(cond.get("조건", []), sc, who)
    raise ConditionError(f"조건의 모양이 아니다: {cond!r}")


def _all(vals: list) -> bool | None:
    if any(v is False for v in vals):
        return False
    return None if any(v is None for v in vals) else True


def _any(vals: list) -> bool | None:
    if any(v is True for v in vals):
        return True
    return None if any(v is None for v in vals) else False


def _lookup(sc: Scope, viewer: str | None, attr: str, subj: str, obj: str | None) -> Any:
    if viewer is None:
        return sc.led.get(attr, subj, obj)
    b = sc.led.knows(viewer, attr, subj, obj)
    return None if b is None else b.value


def _eval_atom(a: dict, sc: Scope, viewer: str | None) -> bool | None:
    led = sc.led
    if "pred" in a:
        args = [sc.resolve(a["args"][0]), a["args"][1]] if a["pred"] == "안다" \
            else [sc.resolve(x) for x in a["args"]]
        if any(x is None for x in args):
            return None
        if a["pred"] == "같은 곳":
            return led.same_place(args[0], args[1])
        if a["pred"] == "안에":
            return led.inside(args[0], args[1])
        if a["pred"] == "지닌다":
            return led.inside(args[1], args[0])
        if a["pred"] == "안다":
            inner = parse_atom(args[1].strip("«» "))
            b = led.knows(args[0], inner["attr"], sc.resolve(inner["subj"]),
                          sc.resolve(inner["obj"]) if inner["obj"] else None)
            if b is None:
                return False
            return True if inner.get("bare") or "rhs" not in inner else str(b.value) == inner["rhs"]
    subj = sc.resolve(a["subj"])
    obj = sc.resolve(a["obj"]) if a["obj"] else None
    if subj is None or (a["obj"] and obj is None):
        return None
    left = _lookup(sc, viewer, a["attr"], subj, obj)
    if a["op"] == "있음":
        return left is not None
    if a["op"] == "없음":
        return left is None
    if left is None:
        return None
    right, shift = _rhs(a["rhs"], sc, viewer)
    if right is None:
        return None
    return _compare(left, a["op"], right, shift, led.definitions.get(a["attr"], {}).get("값"))


def _rhs(text: str, sc: Scope, viewer: str | None) -> tuple[Any, int]:
    m = _REF.match(text)
    if m and m.group(1) in sc.led.definitions:
        args = _args(m.group(2))
        val = _lookup(sc, viewer, m.group(1), sc.resolve(args[0]),
                      sc.resolve(args[1]) if len(args) > 1 else None)
        shift = int(m.group(4) or 0) * (-1 if m.group(3) == "-" else 1)
        return val, shift
    resolved = sc.resolve(text)
    return (resolved if resolved is not None else text), 0


def _rank(v: Any, grades: Any) -> float | None:
    if isinstance(grades, list) and v in grades:
        return float(grades.index(v))
    if isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _compare(left: Any, op: str, right: Any, shift: int, grades: Any) -> bool | None:
    if op == "포함":
        return right in left if isinstance(left, (list, set, tuple)) else None
    lr, rr = _rank(left, grades), _rank(right, grades)
    if lr is not None and rr is not None:
        rr += shift
        return {"=": lr == rr, "≠": lr != rr, "이상": lr >= rr, "이하": lr <= rr,
                "초과": lr > rr, "미만": lr < rr}[op]
    if op in ("=", "≠"):
        same = _norm(left) == _norm(right)
        return same if op == "=" else not same
    return None


def _norm(v: Any) -> str:
    if v is True:
        return "참"
    if v is False:
        return "거짓"
    return str(v)


# ---- 되읽기: 조건을 다시 한국어로 풀어 쓴다 (LLM이 아니라 코드가 한다) -------------

def paraphrase(cond: Any) -> str:
    if isinstance(cond, str):
        a = parse_atom(cond)
        if "pred" in a:
            x = a["args"]
            return {"같은 곳": f"{x[0]}와(과) {x[1]}이(가) 같은 곳에 있다",
                    "안에": f"{x[0]}이(가) {x[1]}의 안에 있다",
                    "지닌다": f"{x[0]}이(가) {x[1]}을(를) 지니고 있다",
                    "안다": f"{x[0]}이(가) {x[1]}을(를) 안다"}[a["pred"]]
        head = f"{a['subj']}의 {a['attr']}" if not a["obj"] else f"{a['subj']}의 {a['obj']}에 대한 {a['attr']}"
        if a["op"] in ("있음", "없음"):
            return f"{head}이(가) 정해져 {'있다' if a['op'] == '있음' else '있지 않다'}"
        return f"{head}이(가) {a['rhs']} {WORDS[a['op']]}"
    if isinstance(cond, list):
        return " 그리고 ".join(paraphrase(c) for c in cond)
    if "모두" in cond:
        return "(" + " 그리고 ".join(paraphrase(c) for c in cond["모두"]) + ")"
    if "하나라도" in cond:
        return "(" + " 또는 ".join(paraphrase(c) for c in cond["하나라도"]) + ")"
    if "아님" in cond:
        return f"다음이 아니다: {paraphrase(cond['아님'])}"
    if "어떤" in cond:
        return f"어떤 {cond['표지']}({cond['어떤']})에 대해: {paraphrase(cond.get('조건', []))}"
    if "시야" in cond:
        return f"{cond['시야']}이(가) 아는 바로는: {paraphrase(cond.get('조건', []))}"
    raise ConditionError(f"조건의 모양이 아니다: {cond!r}")
