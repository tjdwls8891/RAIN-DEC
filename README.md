# RAIN-DEC

LLM(Gemini)이 마스터를 맡는 디스코드 TRPG 엔진의 전면 재설계.

- 설계 기록: [docs/](docs/README.md) — 현재의 전체 요약은 [docs/05-큰그림.md](docs/05-큰그림.md)
- 코드: `raindec/` — 설계를 검증하기 위한 **최소 구현**이다. 디스코드 연결은 아직 없다.

## 최소 구현

| 파일 | 내용 |
| --- | --- |
| `raindec/ledger.py` | 장부: 개체, 사실, 정의, 사건, 시야. 위치 관계, 계승, 되감기 |
| `raindec/conditions.py` | 조건 언어의 계산(참/거짓/모름)과 되읽기 |
| `raindec/scenario.py` | 시나리오 읽기, 변수 결정, 세션 개설, 명백한 지각 |
| `raindec/turn.py` | 한 턴: 심판 → 판정 → 인물(병렬) → 서술자 → 마감 |
| `raindec/llm.py` | Gemini 호출과 토큰·시간·비용 측정 |
| `raindec/common.yaml` | 공용 사전 (최소판) |
| `scenarios/객잔.yaml` | 시험용 시나리오 한 장면 |

```
pip install pyyaml google-genai pytest
python -m pytest tests            # LLM 없이 도는 시험
python play.py --fake --bench     # LLM 없이 흐름 확인
python play.py --models           # 쓸 수 있는 Gemini 모델 이름
python play.py --bench            # 정해 둔 선언으로 비용·시간 측정 (Gemini API 필요)
python play.py                    # 직접 플레이
```

아직 없는 것: 디스코드 연결, 기제(게이지·시계·전이·예약·위치 제약·변환)의 실행, 규칙의 실행, 틀 찍어내기, 연출가,
인물의 행동이 세계를 바꾸는 처리, 서술이 지어낸 세부의 처리. 판정 수치는 임시 값이다.
