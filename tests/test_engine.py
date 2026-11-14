"""턴. LLM은 가짜 답으로 대신한다. 엔진은 동작을 모른다: 판단이 낸 (개체, 항목, 값)의 변화를 검사하고 반영할 뿐이다."""
import copy
import random

from raindec.engine import DEGREES, label, run_turn
from raindec.llm import FakeBackend, LLMError
from raindec.scenario import load, open_session

SCN = load("scenarios/객잔.yaml")
SECRETS = ["흑풍채", "척후", "두목", "동생"]


def world(scn=SCN):
    for s in range(1, 60):                            # 열쇠를 주모가 지닌 세계를 고른다
        led, chosen = open_session(scn, s)
        if chosen["열쇠가_있는_곳"] == "주모":
            return led
    raise AssertionError


def interp(*acts, **over):
    return {"행동": [{"유형": "물체/설비 조작", "하려는_일": "…", "대상": [], "가리킨_말": "", "말": "", **a} for a in acts],
            "내면": "", "세계에_대한_단정": "", "모호함": False, "되물음": "", "되읽기": "…하려 한다.", **over}


def ch(subj, attr, value, obj="없음"):
    return {"개체": subj, "항목": attr, "새항목": "", "대상": obj, "값": value}


def new(subj, name, value):
    return {"개체": subj, "항목": "사전에 없는 항목", "새항목": name, "대상": "없음", "값": value}


def J(**over):
    if over.get("성립") == "판정이 필요하다":
        over.setdefault("모자랄_것", "솜씨나 빠르기")
    return {"담기는가": "담긴다", "모자랄_것": "없다", "성립": "뻔히 된다", "능력": "민첩", "난이도": "보통", "방법": "무난함", "변화": [], "사전에_없는_변화": "", "시간": "잠깐", **over}


def play(led, script, seed=1, scn=SCN, press=None):
    script = copy.deepcopy(script)
    it = script.get("해석")
    if isinstance(it, dict):                          # 시험에서는 내부 이름으로 적고, 해석이 실제로 내는 부름말로 바꾼다
        for a in it["행동"]:
            a["대상"] = [label(led, t) if t in led.entities else t for t in a["대상"]]
    j = script.get("판단")
    if isinstance(j, dict):
        def fix(c):
            return {**c, "개체": label(led, c["개체"]) if c["개체"] in led.entities else c["개체"],
                    "대상": label(led, c["대상"]) if c["대상"] in led.entities else c["대상"]}
        for k, v in j.items():
            if k == "변화":
                j[k] = [fix(c) for c in v]
            elif isinstance(v, dict) and "변화" in v:
                v["변화"] = [fix(c) for c in v["변화"]]
    be = FakeBackend({"서술": "(서술)", **script})
    return run_turn(led, be, "강호민", "…", scn, random.Random(seed), press=press), be


# ── 조건은 항목에 걸려 있다 ──

def test_잠긴_문은_어떤_행동으로_열려_해도_같은_조건에_걸린다():
    for what in ("뒷문을 열어 본다", "어깨로 뒷문을 밀어 연다", "뒷문 손잡이를 발로 차 연다"):
        led = world()
        res, be = play(led, {"해석": interp({"하려는_일": what, "대상": ["뒷문"]}), "판단": J(변화=[ch("뒷문", "열림", "참")])})
        assert led.get("열림", "뒷문") == "거짓" and led.knows("강호민", "잠김", "뒷문").value == "참"
        assert "잠겨 있다" in be.seen[-1].prompt and not res.checks


def test_잠긴_문_너머로는_갈_수_없다():
    led = world()
    res, be = play(led, {"해석": interp({"하려는_일": "뒷문으로 나간다", "대상": ["뒷문"]}), "판단": J(변화=[ch("강호민", "위치", "안에", "뒷골목")])})
    assert led.place_of("강호민") == "객잔_1층" and "잠겨 있다" in be.seen[-1].prompt
    res, be = play(led, {"해석": interp({"하려는_일": "창고로 들어간다", "대상": ["창고문"]}), "판단": J(변화=[ch("강호민", "위치", "안에", "객잔_창고")])})
    assert led.place_of("강호민") == "객잔_창고"


def test_사전에_항목을_더하면_코드_없이_모든_행동에서_작동한다():
    """통과 기준(docs/40 §5): 코드를 한 줄도 더 쓰지 않고 항목 하나를 더한다."""
    scn = copy.deepcopy(SCN)
    scn["정의"]["젖음"] = {"값": ["마름", "축축함", "흠뻑"], "겉보기": "누구나", "기본": "마름", "고침": "누구나",
                        "드러남": {"축축함": "축축하게 젖어 있다.", "흠뻑": "물이 뚝뚝 떨어진다."},
                        "조건": {"마름": ["젖음(이것) = 축축함"]}, "걸리면": {"마름": "이렇게 젖은 것은 닦아서 마르지 않는다."}}
    scn["규칙"] = scn["규칙"] + [{"이름": "젖은 것은 무르다", "표지": ["물건"], "조건": ["젖음(이것) = 흠뻑"], "귀결": ["견고함(이것) = 무름"]}]
    led = world(scn)
    for what in ("찻물을 의자에 붓는다", "의자를 빗물받이에 담근다"):
        res, be = play(world(scn), {"해석": interp({"하려는_일": what, "대상": ["나무_의자"]}), "판단": J(변화=[ch("나무_의자", "젖음", "흠뻑")])}, scn=scn)
        assert "물이 뚝뚝 떨어진다" in be.seen[-1].prompt
    res, be = play(led, {"해석": interp({"하려는_일": "찻물을 의자에 붓는다", "대상": ["나무_의자"]}), "판단": J(변화=[ch("나무_의자", "젖음", "흠뻑")])}, scn=scn)
    assert led.get("젖음", "나무_의자") == "흠뻑" and led.get("견고함", "나무_의자") == "무름"       # 규칙의 귀결
    res, be = play(led, {"해석": interp({"하려는_일": "소매로 의자를 닦는다", "대상": ["나무_의자"]}), "판단": J(변화=[ch("나무_의자", "젖음", "마름")])}, scn=scn)
    assert led.get("젖음", "나무_의자") == "흠뻑" and "닦아서 마르지 않는다" in be.seen[-1].prompt   # 항목의 조건


def test_바뀌지_않는_항목과_사전에_없는_값은_반영되지_않는다():
    led = world()
    res, be = play(led, {"해석": interp({"하려는_일": "…", "대상": ["주모"]}), "판단": J(변화=[
        ch("주모", "정체", "관아의 밀정"), ch("뒷문", "손상", "가루"), ch("강호민", "기분", "두려움"), ch("주모", "기분", "호의")])})
    assert led.get("정체", "주모") is None and led.get("손상", "뒷문") == "없음" and led.get("기분", "주모") == "경계"
    assert len(res.rejected) == 3                    # 정체는 고를 수 있는 항목이 아니라 걸러진다


# ── 격리 ──

def test_해석과_서술은_진실을_받지_않는다():
    led = world()
    res, be = play(led, {"해석": interp({"유형": "의사소통/설득/기만", "하려는_일": "주모에게 말한다", "대상": ["주모"], "말": "관아에서 나왔소."}),
                         "판단": J(닿는것="없음", 기색="그냥 말함")})
    by = {c.role: c.prompt for c in be.seen}
    assert any(s in by["판단"] for s in SECRETS)
    for role in ("해석", "서술"):
        assert not any(s in by[role] for s in SECRETS), role


# ── 사람을 상대로 ──

TALK = {"유형": "의사소통/설득/기만", "하려는_일": "주모에게 관아 사람이라며 뒷문을 열라고 한다", "대상": ["주모"], "말": "관아에서 나왔소. 뒷문 좀 엽시다."}
DOOR = "뒷문을 아무에게나 열어 주지 않는 것"


def test_속임은_지키려는_것의_무게로_굴리고_걸린_것은_코드가_쓴다():
    seen = []
    res, be = play(world(), {"해석": interp(TALK), "판단": J(방법="나쁨", 닿는것=DOOR, 기색="속임", **{
        "성공시:주모": {"말": "열어 줄게.", "변화": [ch("뒷문", "잠김", "거짓"), ch("뒷문", "열림", "참")]},
        "지킬때:주모": {"말": "패도 없이?", "변화": []}})}, press=seen.append)
    assert res.checks[0]["기준"] == 52 + 2 * (11 - 10) - 6 - 2 * (13 - 10) - 20 == 22
    assert not any(s in str(seen[0]) for s in SECRETS)


def test_성공하면_인물이_제_열쇠로_문을_연다_실패하면_지킨다():
    script = {"해석": interp(TALK), "판단": J(방법="매우 좋음", 닿는것="객잔의 장사와 평판", 기색="밀어붙임", **{
        "성공시:주모": {"말": "열어 줄게.", "변화": [ch("뒷문", "잠김", "거짓"), ch("뒷문", "열림", "참")]},
        "지킬때:주모": {"말": "안 돼.", "변화": [ch("주모", "위치", "곁에", "뒷문")]}})}
    both = set()
    for seed in range(30):
        led = world()
        res, be = play(led, script, seed=seed)
        both.add(res.checks[0]["성공"])
        if res.checks[0]["성공"]:
            assert led.get("열림", "뒷문") == "참" and "열어 줄게" in be.seen[-1].prompt
        else:
            assert led.get("잠김", "뒷문") == "참" and led.where("주모") == ("뒷문", "곁에")
    assert both == {True, False}


def test_열쇠가_없는_인물은_문을_열지_못한다():
    led = world()
    res, _ = play(led, {"해석": interp({"하려는_일": "…", "대상": []}), "판단": J(**{"반응:척후": {"말": "", "변화": [ch("뒷문", "잠김", "거짓")]}})})
    assert led.get("잠김", "뒷문") == "참"


def test_그냥_물었을_때는_굴리지_않고_인물이_지킨다():
    res, be = play(world(), {"해석": interp({**TALK, "말": "저 사내는 누구요?"}), "판단": J(닿는것="흑풍채 두목이 동생이라는 것", 기색="그냥 말함", **{
        "지킬때:주모": {"말": "손님이지.", "변화": []}, "반응:주모": {"말": "내 동생의 부하야.", "변화": []}})})
    assert not res.checks and "손님이지" in be.seen[-1].prompt and "동생" not in be.seen[-1].prompt


# ── 확정의 사다리 ──

def test_속은_후보에서만_채워지고_한_번_정해지면_그대로다():
    led = world()
    open_it = {"해석": interp({"하려는_일": "서랍을 열어 뒤진다", "대상": ["계산대_서랍"]}), "판단": J(변화=[ch("계산대_서랍", "열림", "참")], **{"속:계산대_서랍": ["주판", "용의 비늘"]})}
    play(led, open_it)
    assert [led.get("이름", x) for x in led.contents("계산대_서랍")] == ["주판"]              # 후보 밖의 답은 걸러진다
    led = world()
    open_it["판단"]["속:계산대_서랍"] = ["주판", "치부책"]
    res, be = play(led, open_it)
    assert sorted(led.get("이름", x) for x in led.contents("계산대_서랍")) == ["주판", "치부책"] and "주판" in be.seen[-1].prompt
    res, be = play(led, {"해석": interp({"하려는_일": "서랍을 엎는다", "대상": ["계산대_서랍"]}), "판단": J(**{"속:계산대_서랍": ["부싯돌"]})})
    assert len(led.contents("계산대_서랍")) == 2


def test_없는_것을_가리키면_있는_것의_다른_이름으로_잇는다():
    led = world()
    res, be = play(led, {"해석": interp({"하려는_일": "질그릇을 집어 든다", "대상": ["목록에_없는_것"], "가리킨_말": "질그릇"}),
                         "판단": J(가리킨것="찻주전자", 변화=[ch("가리킨 것", "위치", "손에 든 채", "강호민")])})
    assert led.where("찻주전자") == ("강호민", "손에 든 채")


FIND = {"하려는_일": "바닥에서 부지깽이를 찾아 집는다", "대상": ["목록에_없는_것"], "가리킨_말": "부지깽이"}
MAYBE = "저작되지 않았으나 여기 있을 법하다"


def test_발견_선언은_그럴듯하면_판정으로_인정한다():
    script = {"해석": interp(FIND), "판단": J(가리킨것=MAYBE, 가리킨것의_갈래="흔한 소품", 발견의_난이도="보통", 변화=[ch("가리킨 것", "위치", "손에 쥐고", "강호민")])}
    both = set()
    for seed in range(20):
        led = world()
        n = len(led.entities)
        res, be = play(led, script, seed=seed)
        both.add(res.checks[0]["성공"])
        if res.checks[0]["성공"]:
            found = [e for e in led.entities if led.get("이름", e) == "부지깽이"]
            assert found and led.where(found[0]) == ("강호민", "손에 쥐고") and res.filled
        else:
            assert len(led.entities) == n and "눈에 띄지 않는다" in be.seen[-1].prompt
    assert both == {True, False}


def test_중요한_것_저작된_것_지녔다고_하는_것_닫힌_곳에서는_발견되지_않는다():
    def run(led, said, sort, scn=SCN):
        n = len(led.entities)
        res, be = play(led, {"해석": interp({**FIND, "가리킨_말": said}), "판단": J(가리킨것=MAYBE, 가리킨것의_갈래=sort, 발견의_난이도="쉬움",
                                                                              변화=[ch("가리킨 것", "위치", "손에", "강호민")])}, scn=scn)
        assert len(led.entities) == n and not res.checks and "보이지 않는다" in be.seen[-1].prompt
    run(world(), "숨겨 둔 곁쇠", "열쇠·무기·문서·귀중품처럼 중요하거나 하나뿐인 것")
    run(world(), "관아의 패", "PC가 이미 지니고 있다고 하는 것")
    run(world(), "뒷문 열쇠", "흔한 소품")                       # 저작된 것의 이름이다
    scn = copy.deepcopy(SCN)
    scn["개체"]["객잔_1층"]["사실"].append("닫힌범위(이것) = 참")
    run(world(scn), "부지깽이", "흔한 소품", scn=scn)


# ── 판정 ──

def test_버티는_것을_힘으로_바꾸려_하면_그_항목에서_난이도가_나온다():
    script = {"해석": interp({"하려는_일": "의자로 뒷문을 내리쳐 부순다", "대상": ["뒷문", "나무_의자"]}), "판단": J(능력="민첩", 난이도="쉬움", 변화=[ch("뒷문", "손상", "파손")])}
    seen = set()
    for seed in range(40):
        led = world()
        res, _ = play(led, script, seed=seed)
        c = res.checks[0]
        assert c["기준"] == 52 + 2 * (12 - 10) - 15 and ("뒷문의 견고함: 단단함", -15) in c["내역"]     # 판단이 고른 '쉬움'이 아니다
        seen.add(c["정도"])
        if c["정도"] in ("큰 성공", "성공"):
            assert led.get("손상", "뒷문") == "파손" and led.get("잠김", "뒷문") == "거짓"       # 규칙: 부서진 것은 잠그지 못한다
        elif c["정도"] == "아슬한 성공":
            assert led.get("손상", "뒷문") == "흠" and led.get("잠김", "뒷문") == "참"            # 한 칸만
        else:
            assert led.get("손상", "뒷문") == "없음"
    assert {"성공", "아슬한 성공", "실패"} <= seen


def test_남이_지닌_것을_가져오려면_굴려야_한다():
    from raindec.ledger import Event
    led = world()
    led.append(Event(led.now, "준비", changes=[{"op": "set", "attr": "위치", "subj": "찻주전자", "obj": "척후", "value": "손에"}]))
    res, _ = play(led, {"해석": interp({"하려는_일": "사내의 손에서 찻주전자를 낚아챈다", "대상": ["척후", "찻주전자"]}), "판단": J(변화=[ch("찻주전자", "위치", "손에", "강호민")])})
    assert res.checks and res.checks[0]["기준"] == 52 + 8 - 2 * (15 - 10) - 10


def test_PC가_모르는_것은_PC의_행동으로_바뀌지_않는다():
    """역사칭: "서랍에서 뒷문 열쇠를 찾아 챙긴다". 판단이 주모가 지닌 열쇠를 PC의 손으로 옮기려 해도 받지 않는다."""
    for seed in range(8):
        led = world()
        res, _ = play(led, {"해석": interp({"하려는_일": "서랍에서 뒷문 열쇠를 챙긴다", "대상": ["계산대_서랍"]}),
                            "판단": J(변화=[ch("뒷문_열쇠", "위치", "손에", "강호민"), ch("단도", "위치", "손에", "강호민")])}, seed=seed)
        assert led.holder_of("뒷문_열쇠") == "주모" and led.holder_of("단도") == "척후" and not res.checks
        led = world()                                 # 없는 것을 가리키는 길로도 마찬가지다
        res, be = play(led, {"해석": interp({"하려는_일": "서랍에서 뒷문 열쇠를 챙긴다", "대상": ["계산대_서랍", "목록에_없는_것"], "가리킨_말": "뒷문 열쇠"}),
                             "판단": J(가리킨것="뒷문 열쇠", 변화=[ch("가리킨 것", "위치", "손에", "강호민")])}, seed=seed)
        assert led.holder_of("뒷문_열쇠") == "주모" and not res.checks and "보이지 않는다" in be.seen[-1].prompt


def test_사람_곁에_둔다는_것은_그_사람이_있는_자리에_두는_것이다():
    led = world()
    play(led, {"해석": interp({"하려는_일": "의자를 끌어다 앉는다", "대상": ["나무_의자"]}),
               "판단": J(변화=[ch("나무_의자", "위치", "곁에 끌어다 놓고", "강호민"), ch("강호민", "위치", "위에 앉아", "나무_의자"), ch("강호민", "자세", "앉음")])})
    assert led.where("나무_의자")[0] == "창가" and led.where("강호민") == ("나무_의자", "위에 앉아") and led.get("자세", "강호민") == "앉음"


def test_바뀌는_것이_없어도_판단이_굴리라_하면_굴린다():
    """숨은 것을 찾으려 살피는 일처럼, 세계가 바뀌지 않아도 판정이 설 수 있다."""
    res, _ = play(world(), {"해석": interp({"유형": "관찰/조사/지식", "하려는_일": "사내의 품에 무기가 있는지 눈여겨본다", "대상": ["척후"]}),
                            "판단": J(성립="판정이 필요하다", 능력="통찰", 난이도="어려움")})
    assert res.checks and res.checks[0]["기준"] == 52 + 2 - 15


# ── 실패에 대한 대응 ──

def test_판단이_실패해도_기본값으로_턴이_돈다():
    led = world()
    res, be = play(led, {"해석": interp({"하려는_일": "주모에게 술을 청한다", "대상": ["주모"], "말": "술 한 병 주시오."}), "판단": LLMError("과부하")})
    assert res.kind == "턴" and len(led.events) == 4 and not res.checks


def test_서술이_실패해도_세계는_확정되고_글만_준다():
    led = world()
    res, be = play(led, {"해석": interp({"하려는_일": "계산대로 간다", "대상": ["계산대"]}), "판단": J(변화=[ch("강호민", "위치", "곁에", "계산대")]), "서술": LLMError("끊김")})
    assert led.where("강호민") == ("계산대", "곁에") and res.readback in res.narration


def test_해석이_실패하거나_모호하면_세계는_그대로다():
    led = world()
    n = len(led.events)
    res, _ = play(led, {"해석": LLMError("끊김")})
    assert res.kind == "실패" and len(led.events) == n
    res, _ = play(led, {"해석": interp(모호함=True, 되물음="무엇을요?")})
    assert res.kind == "되물음" and len(led.events) == n


def test_항목은_붙는_곳에만_붙는다():
    led = world()
    res, _ = play(led, {"해석": interp({"하려는_일": "찻주전자를 사내에게 던진다", "대상": ["찻주전자", "척후"]}),
                        "판단": J(변화=[ch("척후", "손상", "흠"), ch("구석_탁자", "자세", "누움")])})
    assert led.get("손상", "척후") is None or led.get("손상", "척후") == "없음"
    assert not res.checks and len(res.rejected) == 2


def test_사전에_없는_항목은_막지_않고_채운다():
    led = world()
    res, be = play(led, {"해석": interp({"하려는_일": "의자를 뒤집어엎는다", "대상": ["나무_의자"]}), "판단": J(변화=[new("나무_의자", "뒤집힘", "참")])})
    assert led.get("뒤집힘", "나무_의자") == "참" and res.filled and "뒤집힘" in be.seen[-1].prompt
    assert "뒤집힘" not in SCN["정의"]                                    # 원본 사전은 그대로다. 채운 것은 세션의 기록에 남는다
    from raindec.ledger import Ledger
    again = Ledger.replay(SCN["정의"], led.events)                       # 되감아 다시 쌓아도 같다
    assert again.get("뒤집힘", "나무_의자") == "참"
    res, be = play(led, {"해석": interp({"하려는_일": "의자를 바로 세운다", "대상": ["나무_의자"]}), "판단": J(변화=[ch("나무_의자", "뒤집힘", "거짓")])})
    assert led.get("뒤집힘", "나무_의자") == "거짓" and not res.filled     # 한 번 채운 항목은 그 뒤로 사전의 항목이다


def test_위치의_방식은_자연어다():
    led = world()
    play(led, {"해석": interp({"하려는_일": "검을 뽑아 사내의 목에 겨눈다", "대상": ["철검", "척후"]}),
               "판단": J(변화=[ch("철검", "위치", "오른손에 쥐고 삿갓 쓴 사내의 목에 겨눈 채", "강호민"), ch("강호민", "위치", "맞은편 의자에 걸터앉아", "척후")])})
    assert led.where("철검") == ("강호민", "오른손에 쥐고 삿갓 쓴 사내의 목에 겨눈 채")
    assert led.where("강호민") == ("구석_탁자", "삿갓 쓴 사내의 맞은편 의자에 걸터앉아")       # 사람 곁은 그 사람이 있는 자리다


def test_사람을_상대로_한_판정은_제_몸으로_하는_일을_막지_않는다():
    script = {"해석": interp({"유형": "공격/제압/피해", "하려는_일": "검을 뽑아 사내의 목에 겨누고 소속을 대라고 한다", "대상": ["척후", "철검"], "말": "대라."}),
              "판단": J(닿는것="자기 소속과 정체", 기색="밀어붙임", 변화=[ch("철검", "위치", "손에", "강호민")],
                       **{"성공시:척후": {"말": "흑풍채요.", "변화": []}, "지킬때:척후": {"말": "사람 잘못 봤소.", "변화": []}})}
    for seed in range(10):
        led = world()
        res, _ = play(led, script, seed=seed)
        assert res.checks and led.where("철검") == ("강호민", "손에")


def test_따르는_행동은_해석의_규칙에_있다_상태판은_턴마다_온다():
    from raindec.engine import SYS_INTERPRET, SYS_JUDGE
    assert "뚜껑" in SYS_INTERPRET and "가만히 있는 것이 기본" not in SYS_JUDGE
    led = world()
    res, _ = play(led, {"해석": interp({"하려는_일": "계산대로 간다", "대상": ["계산대"]}), "판단": J(변화=[ch("강호민", "위치", "앞에 서서", "계산대")])})
    assert "객잔 1층" in res.board


def test_능력과_시간의_낱말은_사전에서_온다():
    scn = copy.deepcopy(SCN)
    for old in ("근력", "민첩", "통찰"):
        del scn["정의"][old]
    scn["정의"].update({"완력": {"겉보기": "숨김", "능력": True}, "감각": {"겉보기": "숨김", "능력": True}})
    scn["시간등급"], scn["맞섬"] = {"한 호흡": 1, "한 식경": 30}, {"말": "감각", "손": "감각", "힘": "완력"}
    scn["개체"]["강호민"]["사실"] = [f for f in scn["개체"]["강호민"]["사실"] if not any(k in f for k in ("근력", "민첩", "통찰"))] + ["완력(이것) = 15"]
    for who in ("주모", "척후"):
        scn["개체"][who]["사실"] = [f for f in scn["개체"][who]["사실"] if not any(k in f for k in ("근력", "민첩", "통찰"))]
    led = world(scn)
    res, be = play(led, {"해석": interp({"하려는_일": "의자로 뒷문을 부순다", "대상": ["뒷문"]}),
                         "판단": J(능력="완력", 시간="한 식경", 변화=[ch("뒷문", "손상", "파손")])}, scn=scn)
    assert ("완력 15", 10) in res.checks[0]["내역"] and led.now == 1260 + 30
