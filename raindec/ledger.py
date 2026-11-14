"""장부: 개체, 사실, 정의, 사건, 시야.

세계의 현재 상태는 사건을 처음부터 쌓은 결과다. 사건은 고치거나 지우지 않는다.
설계: docs/09-장부-설계.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

LOC = "위치"          # 위치(무엇 → 어디) = 방식
PROTO = "원형"        # 원형(실물) = 원형 개체
HEAD = "소속"         # 소속(장소) = 분류 헤드
PLACE = "장소"
PERSON = "인물"


@dataclass(frozen=True)
class Fact:
    attr: str
    subj: str
    obj: str | None
    value: Any
    since: int = 0          # 세계 시각(분)
    event: int = -1         # 비롯된 사건 번호

    @property
    def key(self) -> tuple[str, str, str | None]:
        return (self.attr, self.subj, self.obj)

    def text(self) -> str:
        return fact_text(self.attr, self.subj, self.obj, self.value)


def fact_text(attr: str, subj: str, obj: str | None, value: Any) -> str:
    head = f"{attr}({subj} → {obj})" if obj else f"{attr}({subj})"
    return f"{head} = {value}"


@dataclass
class Belief:
    """시야에 담긴 명제. 참인지는 별개다."""
    attr: str
    subj: str
    obj: str | None
    value: Any
    confidence: str = "확실"
    source: str = "직접 지각"
    when: int = 0

    def text(self) -> str:
        base = fact_text(self.attr, self.subj, self.obj, self.value)
        return f"{base}  [{self.source}, {self.confidence}]"


@dataclass
class Event:
    """일어난 일의 기록. changes는 장부를 바꾸는 연산의 목록이다."""
    time: int
    kind: str
    actor: str | None = None
    summary: str = ""
    changes: list[dict] = field(default_factory=list)
    perceived_by: dict[str, str] = field(default_factory=dict)   # 누가 → 어떤 감각으로
    detail: dict = field(default_factory=dict)                   # 판정, 호출 기록 등


class LedgerError(Exception):
    pass


class Ledger:
    def __init__(self, definitions: dict[str, dict] | None = None):
        self.base_definitions: dict[str, dict] = definitions or {}
        self.definitions: dict[str, dict] = dict(self.base_definitions)
        self.entities: dict[str, set[str]] = {}
        self.facts: dict[tuple, Fact] = {}
        self.views: dict[str, dict[tuple, Belief]] = {}
        self.events: list[Event] = []
        self.now: int = 0

    # ---- 사건 쌓기 ---------------------------------------------------
    def append(self, event: Event) -> int:
        """사건을 기록하고 그 변화를 반영한다. 검사에 실패하면 아무것도 바뀌지 않는다."""
        saved = dict(self.definitions)
        try:
            for ch in event.changes:
                self.check(ch)
                if ch.get("op") == "define":         # 같은 사건의 뒤따르는 변화가 새 항목을 쓸 수 있게
                    self.definitions.setdefault(ch["attr"], ch["definition"])
        except LedgerError:
            self.definitions = saved
            raise
        number = len(self.events)
        self.events.append(event)
        self.now = max(self.now, event.time)
        for ch in event.changes:
            self._apply(ch, number, event.time)
        return number

    @classmethod
    def replay(cls, definitions: dict, events: list[Event], upto: int | None = None) -> "Ledger":
        """사건 기록에서 장부를 다시 쌓는다. upto를 주면 그 번호까지만 쌓는다(되감기)."""
        led = cls(dict(definitions))         # 세션 중에 채운 정의가 원본 사전을 건드리지 않게
        for ev in events[: None if upto is None else upto + 1]:
            led.append(ev)
        return led

    def check(self, ch: dict) -> None:
        op = ch.get("op")
        if op == "entity":
            if not ch.get("id"):
                raise LedgerError("개체에 식별자가 없다")
        elif op == "define":
            if not ch.get("attr") or not isinstance(ch.get("definition"), dict):
                raise LedgerError("정의를 읽을 수 없다")
        elif op in ("set", "unset", "know"):
            attr = ch.get("attr")
            if attr not in self.definitions:
                raise LedgerError(f"정의되지 않은 속성: {attr}")
            if op == "unset":
                return
            d = self.definitions[attr]
            grades = d.get("값")
            if isinstance(grades, list) and ch.get("value") not in grades:
                raise LedgerError(f"{attr}의 값이 아니다: {ch.get('value')} (가능: {grades})")
        else:
            raise LedgerError(f"알 수 없는 연산: {op}")

    def _apply(self, ch: dict, number: int, time: int) -> None:
        op = ch["op"]
        if op == "entity":
            self.entities.setdefault(ch["id"], set()).update(ch.get("tags", []))
        elif op == "define":                 # 사전에 없던 항목을 채웠다. 사건으로 남으므로 되감기와 편입 검토가 된다
            self.definitions.setdefault(ch["attr"], ch["definition"])
        elif op == "set":
            self.entities.setdefault(ch["subj"], set())
            f = Fact(ch["attr"], ch["subj"], ch.get("obj"), ch["value"], time, number)
            if ch["attr"] == LOC:
                # 어떤 것은 한 번에 한 곳에만 있다.
                for k in [k for k in self.facts if k[0] == LOC and k[1] == ch["subj"]]:
                    del self.facts[k]
            self.facts[f.key] = f
        elif op == "unset":
            self.facts.pop((ch["attr"], ch["subj"], ch.get("obj")), None)
        elif op == "know":
            b = Belief(ch["attr"], ch["subj"], ch.get("obj"), ch["value"],
                       ch.get("confidence", "확실"), ch.get("source", "직접 지각"), time)
            self.views.setdefault(ch["holder"], {})[(b.attr, b.subj, b.obj)] = b

    # ---- 읽기 ---------------------------------------------------------
    def has_tag(self, ent: str, tag: str) -> bool:
        return tag in self.entities.get(ent, ())

    def get(self, attr: str, subj: str, obj: str | None = None, inherit: bool = True) -> Any:
        """사실의 값. 없으면 계승을 따라 올라가고, 그래도 없으면 정의의 기본값, 그것도 없으면 None(모름)."""
        f = self.facts.get((attr, subj, obj))
        if f is not None:
            return f.value
        d = self.definitions.get(attr, {})
        if inherit:
            for parent in self._parents(subj, d):
                v = self.get(attr, parent, obj, inherit=True)
                if v is not None:
                    return v
        return d.get("기본")

    def _parents(self, subj: str, definition: dict) -> list[str]:
        out = []
        proto = self.facts.get((PROTO, subj, None))
        if proto:
            out.append(proto.value)          # 실물 ← 원형: 언제나 계승
        mat = self.facts.get(("재질", subj, None))
        if mat and mat.value in self.entities and mat.value != subj:
            out.append(mat.value)            # 물건 ← 재질: 재질의 성질을 물려받는다
        if definition.get("계승"):
            loc = self.where(subj)
            if loc and self.has_tag(subj, PLACE):
                out.append(loc[0])           # 장소 ← 상위 장소
            head = self.facts.get((HEAD, subj, None))
            if head:
                out.append(head.value)       # 장소 ← 분류 헤드
        return out

    def facts_about(self, subj: str) -> list[Fact]:
        return [f for f in self.facts.values() if f.subj == subj or f.obj == subj]

    # ---- 위치: 하나의 관계 ---------------------------------------------
    def where(self, x: str) -> tuple[str, str] | None:
        for (attr, subj, obj), f in self.facts.items():
            if attr == LOC and subj == x:
                return (obj, f.value)
        return None

    def chain(self, x: str) -> list[str]:
        """x가 들어 있는 것들을 가까운 순서로."""
        out, seen = [], {x}
        cur = self.where(x)
        while cur and cur[0] not in seen:
            out.append(cur[0])
            seen.add(cur[0])
            cur = self.where(cur[0])
        return out

    def place_of(self, x: str) -> str | None:
        """x가 있는 최하위 장소."""
        if self.has_tag(x, PLACE):
            return x
        for up in self.chain(x):
            if self.has_tag(up, PLACE):
                return up
        return None

    def holder_of(self, x: str) -> str | None:
        """x를 들거나 입거나 지닌 인물."""
        for up in self.chain(x):
            if self.has_tag(up, PERSON):
                return up
        return None

    def inside(self, a: str, b: str) -> bool:
        return b in self.chain(a)

    def same_place(self, a: str, b: str) -> bool:
        pa, pb = self.place_of(a), self.place_of(b)
        return pa is not None and pa == pb

    def contents(self, y: str, deep: bool = False) -> list[str]:
        direct = [s for (attr, s, o) in self.facts if attr == LOC and o == y]
        if not deep:
            return direct
        out = list(direct)
        for d in direct:
            out.extend(self.contents(d, deep=True))
        return out

    def present_in(self, place: str) -> list[str]:
        """그 장소에 있는 모든 것(지점 위, 인물이 지닌 것 포함)."""
        return [e for e in self.entities if e != place and self.place_of(e) == place
                and not self.has_tag(e, PLACE)]

    # ---- 시야 ---------------------------------------------------------
    def view(self, holder: str) -> list[Belief]:
        return list(self.views.get(holder, {}).values())

    def knows(self, holder: str, attr: str, subj: str, obj: str | None = None) -> Belief | None:
        return self.views.get(holder, {}).get((attr, subj, obj))

    def visible(self, attr: str) -> bool:
        return self.definitions.get(attr, {}).get("겉보기", "누구나") == "누구나"
