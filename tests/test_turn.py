import asyncio
import random

import pytest

from raindec.llm import FakeBackend
from raindec.scenario import load, open_session
from raindec.turn import run_turn

SCN = "scenarios/객잔.yaml"

REFEREE = {
    "세계밖": False,
    "행동": [{"유형": "조작", "대상": ["뒷문"], "수단": "철사", "의도": "뒷문을 연다"}],
    "내면": "주모가 뭔가 숨긴다고 의심한다",
    "소요_분": 3,
    "판정": {"필요": False, "명백": "성공"},
    "귀결": {
        "성공": {"PC지각": "자물쇠가 철컥 풀린다.", "변화": [
            {"연산": "사실", "속성": "잠김", "주체": "뒷문", "값": "거짓"},
            {"연산": "사실", "속성": "내공", "주체": "강호민", "값": "상"},          # 정의에 없는 속성
            {"연산": "사실", "속성": "기분", "주체": "강호민", "값": "불안"},         # 주권 침범
            {"연산": "사실", "속성": "피로", "주체": "강호민", "값": "엄청남"},       # 등급에 없는 값
            {"연산": "사실", "속성": "위치", "주체": "철검", "대상": "용의_둥지", "값": "안에"},  # 없는 곳
            {"연산": "개체", "주체": "휘어진_철사", "표지": ["물건"]},
            {"연산": "사실", "속성": "위치", "주체": "휘어진_철사", "대상": "강호민", "값": "손에"},
        ]},
        "실패": {"PC지각": "자물쇠는 꿈쩍도 하지 않는다.", "변화": []},
    },
    "지각": [{"누구": "주모", "감각": "보고 들음", "내용": "젊은 검객이 계산대 뒤 뒷문 자물쇠를 철사로 따고 있다."},
           {"누구": "척후", "감각": "소리만", "내용": "계산대 쪽에서 쇠 긁는 소리가 난다."}],
}
PERSONA = {
    "인물:주모": {"속마음": "저 문이 열리면 곤란하다.", "기분": "분노",
               "겉행동": "행주를 내려놓고 계산대를 돌아 나온다.", "대사": "거기 손 떼.", "의도": "문에서 떼어 놓는다"},
    "인물:척후": {"속마음": "소란을 틈타 나갈 수 있겠다.", "기분": "경계",
               "겉행동": "삿갓 챙을 조금 든다.", "대사": "", "의도": "지켜본다"},
}


def backend(**over):
    return FakeBackend({"심판": REFEREE, "서술자": "자물쇠가 풀렸다.", **PERSONA, **over})


def play(led, be, text="철사로 뒷문 자물쇠를 딴다. (주모가 뭔가 숨긴다고 의심한다)"):
    return asyncio.run(run_turn(led, be, "강호민", text, load(SCN), random.Random(1)))


def test_제안은_검사를_거쳐_기록된다():
    led, _ = open_session(load(SCN), seed=1)
    res = play(led, backend())
    assert led.get("잠김", "뒷문") == "거짓"
    assert led.holder_of("휘어진_철사") == "강호민"            # 새 개체는 만든 뒤에 쓸 수 있다
    assert res.accepted == 5                                   # 잠김, 철사 개체, 철사 위치, 기분 둘
    assert len(res.rejected) == 4
    reasons = " ".join(res.rejected)
    for word in ("정의되지 않은 속성", "주권 침범", "값이 아니다", "없는 곳"):
        assert word in reasons
    assert led.get("기분", "강호민") != "불안"                  # PC의 내면은 정해지지 않았다
    assert led.get("기분", "주모") == "분노"                    # 인물은 자기 기분을 정한다
    assert led.now == 1263


def test_정보_격리는_문맥으로_한다():
    led, chosen = open_session(load(SCN), seed=1)
    be = backend()
    play(led, be)
    prompt = {c.key.replace("인물:", ""): c.prompt for c in be.seen}

    assert "흑풍채 척후" in prompt["심판"] and "친동생" in prompt["심판"]      # 심판은 진실을 본다

    assert "흑풍채 척후" in prompt["주모"]                 # 주모는 척후의 정체를 안다
    assert "상단의 호위 수" not in prompt["주모"]          # 그러나 척후의 목표는 모른다
    assert "단도" not in prompt["주모"]                    # 품속의 단도도 모른다
    assert "친동생" not in prompt["척후"]                  # 척후는 주모의 비밀 원문을 모른다
    assert "셈이 빠르고" not in prompt["척후"]             # 주모의 성격도 모른다

    for who in ("주모", "척후"):
        assert "의심한다" not in prompt[who]               # PC가 밝힌 내면은 인물에게 가지 않는다
    assert "쇠 긁는 소리" in prompt["척후"] and "철사로 따고" not in prompt["척후"]   # 각자 지각한 만큼만

    n = prompt["서술자"]
    for secret in ("흑풍채 척후", "친동생", "단도", "상단의 호위 수", "저 문이 열리면 곤란하다", "셈이 빠르고"):
        assert secret not in n                             # 서술자는 진실도 속마음도 받지 않는다
    assert "거기 손 떼." in n and "의심한다" in n          # 대사와, PC가 밝힌 내면은 받는다
    assert "뒷문_열쇠" not in n and "뒷문_열쇠" not in prompt["척후"]      # 숨겨진 열쇠의 존재


def test_도중에_실패하면_아무것도_기록되지_않는다():
    led, _ = open_session(load(SCN), seed=1)
    n = len(led.events)

    def boom(key, prompt):
        if key == "서술자":
            raise RuntimeError("호출 실패")
        return {"심판": REFEREE, **PERSONA}[key]

    with pytest.raises(RuntimeError):
        play(led, FakeBackend(boom))
    assert len(led.events) == n and led.get("잠김", "뒷문") == "참"


def test_세계_밖의_말은_세계를_움직이지_않는다():
    led, _ = open_session(load(SCN), seed=1)
    n, now = len(led.events), led.now
    res = play(led, backend(심판={"세계밖": True, "답": "판정은 2d50입니다.", "행동": [], "판정": {"필요": False},
                                 "귀결": {"성공": {"PC지각": "", "변화": []}, "실패": {"PC지각": "", "변화": []}}}))
    assert res.out_of_world and res.narration == "판정은 2d50입니다."
    assert len(led.events) == n and led.now == now


def test_새로_지각한_것만_PC의_시야에_더해진다():
    led, _ = open_session(load(SCN), seed=1)
    assert led.knows("강호민", "잠김", "뒷문") is None          # 관찰해야 보이는 것은 아직 모른다
    play(led, backend())
    assert led.knows("강호민", "기분", "주모") is None           # 기분도 관찰해야 보인다
    assert led.knows("강호민", "위치", "휘어진_철사", "강호민").value == "손에"
