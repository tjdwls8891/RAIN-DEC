import pytest

from raindec.conditions import evaluate, paraphrase
from raindec.ledger import Event, Ledger, LedgerError
from raindec.scenario import load, open_session

SCN = "scenarios/객잔.yaml"


@pytest.fixture
def world():
    return open_session(load(SCN), seed=1)


def test_위치는_하나의_관계(world):
    led, _ = world
    assert led.place_of("강호민") == "객잔_1층"          # 인물 → 지점 → 장소
    assert led.place_of("철검") == "객잔_1층"            # 물건 → 인물 → 지점 → 장소
    assert led.holder_of("철검") == "강호민"
    assert led.inside("창가", "만리객잔")
    assert led.same_place("강호민", "주모")
    assert not led.same_place("강호민", "술독")


def test_계승_분류헤드와_기본값(world):
    led, _ = world
    assert led.get("분위기", "뒷골목").startswith("늦은 밤")      # 장소 ← 분류 헤드
    assert led.get("분위기", "객잔_1층").startswith("늦은 밤")    # 장소 ← 상위 장소 ← 분류 헤드
    assert led.get("조도", "객잔_1층") == "어스름"                # 자기 값이 우선
    assert led.get("잠김", "창고문") == "거짓"                    # 정의의 기본값
    assert led.get("근력", "주모") is None                        # 모름


def test_변수는_씨앗마다_다르게_정해진다():
    scn = load(SCN)
    seen = {open_session(scn, seed=s)[1]["열쇠가_있는_곳"] for s in range(20)}
    assert seen == {"계산대_서랍", "주모", "술독"}
    assert open_session(scn, seed=3)[1] == open_session(scn, seed=3)[1]


def test_정의에_없는_것은_기록되지_않는다(world):
    led, _ = world
    n = len(led.events)
    with pytest.raises(LedgerError):
        led.append(Event(led.now, "턴", changes=[{"op": "set", "attr": "내공", "subj": "강호민", "value": "상"}]))
    with pytest.raises(LedgerError):
        led.append(Event(led.now, "턴", changes=[
            {"op": "set", "attr": "잠김", "subj": "뒷문", "value": "거짓"},
            {"op": "set", "attr": "피로", "subj": "강호민", "value": "아주많이"}]))
    assert len(led.events) == n and led.get("잠김", "뒷문") == "참"    # 하나라도 틀리면 전부 무효


def test_되감기(world):
    led, _ = world
    n = led.append(Event(led.now + 5, "턴", changes=[{"op": "set", "attr": "잠김", "subj": "뒷문", "value": "거짓"}]))
    assert led.get("잠김", "뒷문") == "거짓"
    back = Ledger.replay(led.definitions, led.events, upto=n - 1)
    assert back.get("잠김", "뒷문") == "참"
    again = Ledger.replay(led.definitions, led.events)
    assert again.facts == led.facts


def test_시야는_진실과_다르다(world):
    led, chosen = world
    assert led.knows("주모", "정체", "척후").value == "흑풍채 척후"
    assert led.knows("강호민", "정체", "척후") is None            # PC는 모른다
    assert led.knows("강호민", "외양", "척후") is not None         # 겉모습은 보인다
    assert led.knows("강호민", "외양", "단도") is None             # 품속의 단도는 안 보인다
    assert led.knows("강호민", "외양", "술독") is None             # 다른 방의 것은 안 보인다
    assert led.knows("강호민", "성격", "주모") is None             # 성격은 겉으로 안 보인다
    assert led.knows("강호민", "외양", "철검") is not None         # 허리에 찬 검은 보인다


def test_닫힌_것_속은_보이지_않는다():
    scn = load(SCN)
    for seed in range(12):                                         # 열쇠가 어디에 있든
        led, chosen = open_session(scn, seed=seed)
        for who in ("강호민", "척후"):
            assert not any(b.subj == "뒷문_열쇠" for b in led.view(who)), (seed, who, chosen)


def test_조건_낱개와_묶기(world):
    led, _ = world
    b = {"이것": "철검", "행위자": "강호민", "상대": "척후"}
    assert evaluate("피로(행위자) 이상 보통", led, b) is True
    assert evaluate("피로(행위자) 이상 높음", led, b) is False
    assert evaluate("잠김(뒷문) = 참", led) is True
    assert evaluate("잠김(뒷문)", led) is True
    assert evaluate("위치(이것 → 지닌 자) = 허리에", led, b) is True
    assert evaluate("조도(이곳) 이하 어스름", led, b) is True
    assert evaluate("같은 곳(행위자, 상대)", led, b) is True
    assert evaluate("지닌다(상대, 단도)", led, b) is True
    assert evaluate("민첩(행위자) 미만 민첩(상대)", led, b) is True
    assert evaluate("민첩(행위자) 미만 민첩(상대) - 2", led, b) is False
    assert evaluate({"아님": "같은 곳(강호민, 술독)"}, led) is True
    assert evaluate({"하나라도": ["잠김(창고문) = 참", "잠김(뒷문) = 참"]}, led) is True
    assert evaluate(["잠김(뒷문) = 참", "피로(강호민) = 극심"], led) is False


def test_조건_모름은_참도_거짓도_아니다(world):
    led, _ = world
    assert evaluate("근력(주모) 이상 10", led) is None
    assert evaluate(["근력(주모) 이상 10", "잠김(뒷문) = 참"], led) is None
    assert evaluate(["근력(주모) 이상 10", "잠김(뒷문) = 거짓"], led) is False   # 하나가 거짓이면 거짓
    assert evaluate("근력(주모) 없음", led) is True


def test_조건_어떤과_시야(world):
    led, _ = world
    hostile = {"어떤": "ㄱ", "표지": "인물", "조건": ["같은 곳(ㄱ, 행위자)", "호감(ㄱ → 행위자) 이하 경계"]}
    assert evaluate(hostile, led, {"행위자": "강호민"}) is True
    assert evaluate({"시야": "주모", "조건": ["정체(척후) = 흑풍채 척후"]}, led) is True
    assert evaluate({"시야": "강호민", "조건": ["정체(척후) = 흑풍채 척후"]}, led) is None   # 모른다
    assert evaluate("안다(주모, «정체(척후)»)", led) is True
    assert evaluate("안다(강호민, «정체(척후)»)", led) is False


def test_되읽기():
    assert paraphrase("피로(이것) 이상 높음") == "이것의 피로이(가) 높음 이상이다"
    text = paraphrase({"어떤": "ㄱ", "표지": "인물", "조건": ["같은 곳(ㄱ, 행위자)", "호감(ㄱ → 행위자) 이하 경계"]})
    assert "어떤 인물" in text and "같은 곳에 있다" in text and "그리고" in text
