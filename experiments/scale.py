"""규모 실험: 세계가 커질 때 호출 문맥이 얼마나 커지는가 (LLM 없이 문맥 크기만 잰다)."""
import asyncio, random, sys, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
import yaml
from raindec.llm import FakeBackend
from raindec.scenario import COMMON, open_session
from raindec.turn import run_turn

FAKE = {"심판": {"세계밖": False, "행동": [{"유형": "관찰"}], "내면": "", "소요_분": 1,
               "판정": {"필요": False, "명백": "성공"},
               "귀결": {"성공": {"PC지각": "", "변화": []}, "실패": {"PC지각": "", "변화": []}}, "지각": []},
        "인물": {"속마음": "", "겉행동": "", "대사": "", "의도": ""}, "서술자": ""}

def world(people, factions, places, here):
    """people명·factions개 세력·places개 장소. PC가 있는 방에는 here명이 있다."""
    ents = {"강호_류": {"표지": ["분류헤드"], "사실": ['분위기(이것) = "칼바람 부는 강호."']}}
    for f in range(factions):
        ents[f"세력{f}"] = {"표지": ["세력"], "사실": [f'서술(이것) = "세력 {f}의 내력과 성향을 적은 두세 문장짜리 설명이다."']}
    for p in range(places):
        ents[f"장소{p}"] = {"표지": ["장소"], "사실": ['소속(이것) = 강호_류', f'외양(이것) = "장소 {p}의 생김새를 적은 한두 문장."']}
    ents["주인공"] = {"표지": ["인물", "PC"], "사실": ['위치(이것 → 장소0) = 안에', '외양(이것) = "젊은 검객."', '민첩(이것) = 12']}
    for i in range(people):
        where = "장소0" if i < here else f"장소{1 + i % max(1, places - 1)}"
        ents[f"인물{i}"] = {"표지": ["인물"], "사실": [
            f'위치(이것 → {where}) = 안에', f'이름(이것) = 인물{i}', f'역할(이것) = 세력{i % factions}의 문도',
            f'외양(이것) = "인물 {i}의 겉모습을 적은 한 문장."',
            f'성격(이것) = "인물 {i}의 성격을 적은 두 문장. 무엇을 좋아하고 무엇을 싫어하는가."',
            f'말투(이것) = "인물 {i}의 말버릇 한 문장."', f'목표(이것) = "인물 {i}가 지금 바라는 것 한 문장."',
            f'비밀(이것) = "인물 {i}가 숨기는 것 한 문장."', '기분(이것) = 평온', f'호감(이것 → 주인공) = 무관심']}
    return {"이름": "규모 실험", "어조": "무협", "전제": "강호.", "시작": {"PC": "주인공", "시각": 0},
            "정의": yaml.safe_load(COMMON.read_text(encoding="utf-8"))["정의"], "개체": ents}

def measure(people, factions, places, here):
    scn = world(people, factions, places, here)
    t0 = time.time(); led, _ = open_session(scn, seed=1); t_open = time.time() - t0
    be = FakeBackend(FAKE)
    t0 = time.time(); asyncio.run(run_turn(led, be, "주인공", "주위를 둘러본다.", scn, random.Random(1))); t_turn = time.time() - t0
    size = {}
    for c in be.seen:
        size.setdefault(c.role, []).append(len(c.prompt))
    per = size.get("인물", [0])
    return (people, here, len(led.entities), len(led.facts), len(size["심판"]) and size["심판"][0], len(per) if size.get("인물") else 0,
            max(per), sum(per), size["서술자"][0], round(t_open, 2), round(t_turn, 2))

print("세계인물 장면인물 개체 사실 | 심판(자) 인물호출 인물최대(자) 인물합(자) 서술자(자) | 개설(초) 턴(초)")
for args in [(10, 2, 8, 3), (50, 5, 30, 3), (200, 10, 120, 3), (200, 10, 120, 10), (200, 10, 120, 30)]:
    print(*measure(*args))
