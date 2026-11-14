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
    return {"행동": [{"유형": "물체/설비 조작", "가리킨_말": "", "말": "", "요구": "", "하는_일": "", "상대": "없음", **a} for a in acts],
            "내면": "", "세계에_대한_단정": "", "모호함": False, "되물음": "", "되읽기": "…하려 한다.", **over}


def named(led, script):
    """시험에서는 내부 이름으로 적고, 해석이 실제로 내는 부름말로 바꿔 준다."""
    from raindec.engine import label
    it = script.get("해석")
    if isinstance(it, dict):
        for a in it["행동"]:
            for k in ("대상", "상대"):
                if a[k] in led.entities:
                    a[k] = label(led, a[k])
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
    judge = {"닿는것": "없음", "방법": "나쁨", "성공시": {"태도": "마지못해 따른다", "말": "알았수.", "하는_일": "말로만 답한다"},
             "실패시": {"태도": "거절한다", "말": "패도 없이?"}, "곁:척후": {"태도": "지켜본다", "말": ""}}
    res, be = play(led, {"해석": interp({"동작": "속인다", "대상": "주모", "말": "관아에서 나왔소.", "요구": "뒷문을 연다"}), "판단": judge})
    by = {c.role: c.prompt for c in be.seen}
    assert any(s in by["판단"] for s in SECRETS)                   # 판단은 진실을 본다
    for role in ("해석", "서술"):
        assert not any(s in by[role] for s in SECRETS), role
    assert "삿갓 쓴 사내" in by["서술"]                             # 부름말로만 나온다


def test_걸린_것은_코드가_쓴다():
    led = world()
    judge = {"닿는것": "뒷문을 아무에게나 열어 주지 않는 것", "방법": "나쁨", "성공시": {"태도": "따른다", "말": "", "하는_일": "말로만 답한다"},
             "실패시": {"태도": "거절한다", "말": ""}, "곁:척후": {"태도": "무시한다", "말": ""}}
    seen = []
    be = FakeBackend(named(led, {"해석": interp({"동작": "속인다", "대상": "주모", "말": "관아요.", "요구": "뒷문을 연다"}), "판단": judge, "서술": "."}))
    res = run_turn(led, be, "강호민", "…", SCN, random.Random(3), press=seen.append)
    assert seen and not any(s in str(seen[0]) for s in SECRETS)
    assert res.checks[0]["기준"] == 52 + 2 * (11 - 10) - 6 - 2 * (13 - 10) - 20 == 22      # 능력, 방법, 상대의 통찰, 지키려는 것


def test_속임이_성공하면_구속하고_요구된_일은_코드가_한다():
    led = world()
    judge = {"닿는것": "없음", "방법": "매우 좋음", "성공시": {"태도": "마지못해 따른다", "말": "열어 줄게.", "하는_일": "뒷문을(를) 열어 준다"},
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
    res, be = play(led, {"해석": interp({"동작": "집는다", "대상": "목록에_없는_것", "가리킨_말": "들보 위의 암기 주머니"}), "판단": {"가리킨것": "여기에 없다"}})
    assert set(led.entities) == ents and res.unhandled and "보이지 않는다" in be.seen[-1].prompt


def test_있는_것의_일부를_가리키면_그것으로_잇는다():
    led = world()
    seen = {}

    def judge(prompt, schema):
        if "가리킨것" in schema["properties"]:
            return {"가리킨것": "뒷문"}
        seen["대상"] = "대상: 뒷문" in prompt
        return {**GEN, "성립": "뻔히 된다", "되면_자리": "있던 자리 그대로", "되면_바뀌는것": ["뒷문의 잠금이 풀린다", "뒷문이 흠이 난다"]}
    res, be = play(led, {"해석": interp({"동작": "그밖", "하는_일": "자물쇠를 내리쳐 부순다", "대상": "목록에_없는_것", "가리킨_말": "자물쇠"}), "판단": judge})
    assert seen["대상"] and led.get("잠김", "뒷문") == "거짓" and led.get("손상", "뒷문") == "흠"


def test_모호하면_되묻고_세계는_그대로다():
    led = world()
    n = len(led.events)
    res, _ = play(led, {"해석": interp(모호함=True, 되물음="무엇을요?")})
    assert res.kind == "되물음" and len(led.events) == n


def test_닿는것을_못_고르면_가장_무거운_것으로_본다():
    led = world()
    judge = {"닿는것": "용의 비늘", "방법": "무난함", "성공시": {"태도": "따른다", "말": "", "하는_일": "말로만 답한다"},
             "실패시": {"태도": "거절한다", "말": ""}, "곁:척후": {"태도": "무시한다", "말": ""}}
    res, _ = play(led, {"해석": interp({"동작": "설득한다", "대상": "주모", "말": "…", "요구": "…"}), "판단": judge})
    assert ("상대가 지키려는 것 (매우 큼)", -30) in res.checks[0]["내역"]


def test_정도는_여유로_갈린다():
    from raindec.engine import DEGREES
    name = lambda m: next(n for f, n in (DEGREES[:3] if m > 0 else DEGREES[3:]) if m >= f)
    assert [name(m) for m in (30, 29, 10, 9, 1, 0, -9, -10, -39, -40)] == [
        "큰 성공", "성공", "성공", "아슬한 성공", "아슬한 성공", "아슬한 실패", "아슬한 실패", "실패", "실패", "큰 실패"]


def test_말에_든_요구가_지키려는_것에_닿으면_굴린다():
    """해석은 거짓인지 모른다. '말한다'로 왔어도 판단이 닿는 것을 고르면 판정이 선다."""
    base = {"방법": "무난함", "성공시": {"태도": "따른다", "말": "", "하는_일": "말로만 답한다"}, "실패시": {"태도": "거절한다", "말": ""},
            "반응": {"태도": "따른다", "말": "여기.", "하는_일": "말로만 답한다"}, "곁:척후": {"태도": "무시한다", "말": ""}}
    act = {"동작": "말한다", "대상": "주모", "말": "관아에서 나왔소.", "요구": "뒷문을 연다"}
    res, _ = play(world(), {"해석": interp(dict(act)), "판단": {**base, "닿는것": "뒷문을 아무에게나 열어 주지 않는 것", "말의_참거짓": "거짓"}})
    assert res.checks and res.checks[0]["일"] == "속인다"
    res, _ = play(world(), {"해석": interp({**act, "말": "술 한 병 주시오.", "요구": "술을 준다"}), "판단": {**base, "닿는것": "없음", "말의_참거짓": "참말"}})
    assert not res.checks
    # 참말로 그냥 물었는데 지키려는 것에 닿으면: 굴리지 않고 인물이 지킨다
    res, be = play(world(), {"해석": interp({**act, "말": "저 사내는 누구요?", "요구": ""}),
                             "판단": {**base, "닿는것": "흑풍채 두목이 동생이라는 것", "말의_참거짓": "참말", "실패시": {"태도": "얼버무린다", "말": "손님이지."}}})
    assert not res.checks and "얼버무린다" in be.seen[-1].prompt


GEN = {"담기는가": "담긴다", "성립": "판정이 필요하다", "능력": "민첩", "난이도": "보통", "방법": "무난함", "소리": "크게 난다", "후보에_없는_변화": "",
       "곁:주모": {"태도": "지켜본다", "말": ""}, "곁:척후": {"태도": "지켜본다", "말": ""}}


def test_모르는_행동은_후보에서_고른_변화만_일으킨다():
    act = {"동작": "그밖", "하는_일": "찻주전자를 주모에게 던진다", "대상": "찻주전자", "상대": "주모"}
    for seed in range(12):
        led = world()
        ents = set(led.entities)
        judge = {**GEN, "되면_자리": "있던 자리 그대로", "되면_바뀌는것": ["찻주전자가 부서진다", "주모가 크게 다친다", "찻주전자가 금으로 변한다"]}
        res, be = play(led, {"해석": interp(dict(act)), "판단": judge}, seed=seed)
        assert set(led.entities) == ents and res.checks[0]["기준"] == 52 + 2 * (14 - 10)
        if res.checks[0]["성공"]:      # 후보 밖의 답이 섞이면 그 물음은 기본값(바뀌는 것 없음)
            assert led.get("손상", "찻주전자") == "없음"
    led = world()
    judge = {**GEN, "성립": "뻔히 된다", "되면_자리": "찻주전자가 바닥에 놓인다(떨어진다)", "되면_바뀌는것": ["찻주전자가 부서진다"]}
    res, be = play(led, {"해석": interp(dict(act)), "판단": judge})
    assert not res.checks and led.get("손상", "찻주전자") == "파손" and led.where("찻주전자") == ("객잔_1층", "안에")
    assert "큰 소리가 난다" in be.seen[-1].prompt


def test_지닌_것을_꺼내는_일은_판단_없이():
    led = world()
    res, be = play(led, {"해석": interp({"동작": "꺼낸다", "대상": "철검"})})
    assert led.where("철검") == ("강호민", "손에") and not res.judged


def test_장부가_담지_못하는_결과는_일어난_것으로_전하지_않는다():
    led = world()
    judge = {**GEN, "성립": "뻔히 된다", "되면_자리": "찻주전자가 PC의 손에 들린다", "되면_바뀌는것": [], "담기는가": "핵심이 후보에 없다", "후보에_없는_변화": "찻주전자가 들보 위에 놓인다"}
    res, be = play(led, {"해석": interp({"동작": "그밖", "하는_일": "찻주전자를 들보 위에 올려 둔다", "대상": "찻주전자"}), "판단": judge})
    assert led.where("찻주전자") == ("창가", "위에") and res.unhandled and "뜻대로 되지 않는다" in be.seen[-1].prompt


def test_문으로_가는_것은_지나가는_것이_아니다():
    led = world()
    play(led, {"해석": interp({"동작": "간다", "대상": "창고문", "하는_일": "창고문 앞으로 간다"})})
    assert led.place_of("강호민") == "객잔_1층"
    play(led, {"해석": interp({"동작": "간다", "대상": "창고문", "하는_일": "창고문을 지나 들어간다"})})
    assert led.place_of("강호민") == "객잔_창고"


def test_지니지_않은_것은_꺼낼_수_없다():
    led = world()
    ents = set(led.entities)
    res, be = play(led, {"해석": interp({"동작": "꺼낸다", "대상": "목록에_없는_것", "가리킨_말": "관아의 패"})})
    assert set(led.entities) == ents and not res.judged and "지니고 있지 않다" in be.seen[-1].prompt
