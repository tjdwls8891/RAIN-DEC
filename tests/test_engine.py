"""턴의 일곱 단계. LLM은 가짜 답으로 대신한다."""
import random

from raindec.engine import run_turn
from raindec.llm import FakeBackend, LLMError
from raindec.scenario import load, open_session

SCN = load("scenarios/객잔.yaml")
SECRETS = ["흑풍채", "척후", "두목", "동생"]


def world(seed=1):
    for s in range(seed, seed + 50):                 # 열쇠를 주모가 지닌 세계를 고른다
        led, chosen = open_session(SCN, s)
        if chosen["열쇠가_있는_곳"] == "주모":
            return led
    raise AssertionError


def interp(*acts, **over):
    return {"행동": [{"유형": "물체/설비 조작", "가리킨_말": "", "말": "", "요구": "", **a} for a in acts],
            "내면": "", "세계에_대한_단정": "", "모호함": False, "되물음": "", "되읽기": "…하려 한다.", **over}


def named(led, script):
    """시험에서는 내부 이름으로 적고, 해석이 실제로 내는 부름말로 바꿔 준다."""
    from raindec.engine import label
    it = script.get("해석")
    if isinstance(it, dict):
        for a in it["행동"]:
            if a["대상"] in led.entities:
                a["대상"] = label(led, a["대상"])
    return script


def play(led, script, text="…", seed=1):
    script = named(led, dict(script))
    be = FakeBackend({"서술": "(서술)", **script})
    return run_turn(led, be, "강호민", text, SCN, random.Random(seed)), be


def test_뻔한_행동은_판단을_부르지_않는다():
    led = world()
    res, be = play(led, {"해석": interp({"동작": "연다", "대상": "뒷문"})})
    assert [c.role for c in be.seen] == ["해석", "서술"] and not res.judged
    assert led.get("잠김", "뒷문") == "참"
    assert led.knows("강호민", "잠김", "뒷문").value == "참"       # 해 보고 알게 되었다
    assert "잠겨 있다" in be.seen[-1].prompt


def test_해석과_서술은_진실을_받지_않는다():
    led = world()
    judge = {"난이도": "어려움", "방법": "나쁨", "성공시": {"태도": "마지못해 따른다", "말": "알았수.", "하는_일": "말로만 답한다"},
             "실패시": {"태도": "거절한다", "말": "패도 없이?"}, "곁:척후": {"태도": "지켜본다", "말": ""}}
    res, be = play(led, {"해석": interp({"동작": "속인다", "대상": "주모", "말": "관아에서 나왔소.", "요구": "뒷문을 연다"}), "판단": judge})
    by = {c.role: c.prompt for c in be.seen}
    assert any(s in by["판단"] for s in SECRETS)                   # 판단은 진실을 본다
    for role in ("해석", "서술"):
        assert not any(s in by[role] for s in SECRETS), role
    assert "삿갓 쓴 사내" in by["서술"]                             # 부름말로만 나온다


def test_걸린_것은_코드가_쓴다():
    led = world()
    judge = {"난이도": "어려움", "방법": "나쁨", "성공시": {"태도": "따른다", "말": "", "하는_일": "말로만 답한다"},
             "실패시": {"태도": "거절한다", "말": ""}, "곁:척후": {"태도": "무시한다", "말": ""}}
    seen = []
    be = FakeBackend(named(led, {"해석": interp({"동작": "속인다", "대상": "주모", "말": "관아요.", "요구": "뒷문을 연다"}), "판단": judge, "서술": "."}))
    res = run_turn(led, be, "강호민", "…", SCN, random.Random(3), press=seen.append)
    assert seen and not any(s in str(seen[0]) for s in SECRETS)
    assert res.checks[0]["기준"] == 45 + (11 - 10) * 2 - 5 - (13 - 10) * 2


def test_속임이_성공하면_구속하고_요구된_일은_코드가_한다():
    led = world()
    judge = {"난이도": "매우 쉬움", "방법": "매우 좋음", "성공시": {"태도": "마지못해 따른다", "말": "열어 줄게.", "하는_일": "뒷문을(를) 열어 준다"},
             "실패시": {"태도": "거절한다", "말": "안 돼."}, "곁:척후": {"태도": "지켜본다", "말": ""}}
    for seed in range(20):
        w = world()
        res, _ = play(w, {"해석": interp({"동작": "속인다", "대상": "주모", "말": "관아요.", "요구": "뒷문을 연다"}), "판단": judge}, seed=seed)
        if res.checks[0]["성공"]:
            assert w.get("잠김", "뒷문") == "거짓" and w.get("열림", "뒷문") == "참"
        else:
            assert w.get("잠김", "뒷문") == "참" and w.get("호감", "주모", "강호민") == "경계"


def test_서랍_속은_후보에서만_채워진다():
    led = world()
    judge = {"내용물": ["주판", "치부책", "뒷문_열쇠", "용의 비늘"]}       # 후보 밖의 답이 섞였다
    res, be = play(led, {"해석": interp({"동작": "뒤진다", "대상": "계산대_서랍"}), "판단": judge})
    assert led.contents("계산대_서랍") == []                            # 꼴이 맞지 않으면 기본값(없음)
    led2 = world()
    play(led2, {"해석": interp({"동작": "뒤진다", "대상": "계산대_서랍"}), "판단": {"내용물": ["주판", "치부책"]}})
    assert sorted(led2.get("이름", x) for x in led2.contents("계산대_서랍")) == ["주판", "치부책"]
    n = len(led2.contents("계산대_서랍"))
    res, be = play(led2, {"해석": interp({"동작": "뒤진다", "대상": "계산대_서랍"}), "판단": {"내용물": ["부싯돌"]}})
    assert len(led2.contents("계산대_서랍")) == n and not res.judged     # 한 번 정해진 것은 다시 정하지 않는다


def test_판단이_실패해도_기본값으로_턴이_돈다():
    led = world()
    res, be = play(led, {"해석": interp({"동작": "말한다", "대상": "주모", "말": "술 한 병 주시오."}), "판단": LLMError("과부하")})
    assert res.kind == "턴" and len(led.events) == 4


def test_서술이_실패해도_세계는_확정되고_글만_준다():
    led = world()
    res, be = play(led, {"해석": interp({"동작": "간다", "대상": "계산대"}), "서술": LLMError("끊김")})
    assert led.where("강호민") == ("계산대", "곁에") and res.readback in res.narration


def test_해석이_실패하면_아무것도_바뀌지_않는다():
    led = world()
    n = len(led.events)
    res, _ = play(led, {"해석": LLMError("끊김")})
    assert res.kind == "실패" and len(led.events) == n


def test_목록에_없는_대상은_만들어지지_않는다():
    led = world()
    ents = set(led.entities)
    res, _ = play(led, {"해석": interp({"동작": "집는다", "대상": "목록에_없는_것", "가리킨_말": "들보 위의 암기 주머니"})})
    assert set(led.entities) == ents and res.unhandled


def test_모호하면_되묻고_세계는_그대로다():
    led = world()
    n = len(led.events)
    res, _ = play(led, {"해석": interp(모호함=True, 되물음="무엇을요?")})
    assert res.kind == "되물음" and len(led.events) == n
