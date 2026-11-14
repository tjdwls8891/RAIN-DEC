# RAIN-DEC

LLM(Gemini)이 마스터를 맡는 디스코드 TRPG 엔진의 전면 재설계.

- 설계 기록: [docs/](docs/README.md) — 기준 문서의 지도는 [docs/35-구현-순서와-미결.md](docs/35-구현-순서와-미결.md) §1
- 코드: `raindec/` — 구현의 첫 판이다. 디스코드 연결은 아직 없다.

## 코드

| 파일 | 내용 |
| --- | --- |
| `raindec/ledger.py` | 장부: 개체, 사실, 정의, 사건, 시야. 위치 관계, 계승, 되감기 |
| `raindec/conditions.py` | 조건 언어의 계산(참/거짓/모름)과 되읽기 |
| `raindec/scenario.py` | 시나리오 읽기, 변수 결정, 세션 개설, 명백한 지각 |
| `raindec/engine.py` | 한 턴: 해석 → 준비 → 판단 → 판정 → 귀결 → 서술 → 확정 |
| `raindec/llm.py` | Gemini 호출(흘려 받기, 다시 시도, 지출 상한)과 토큰·시간·값의 측정 |
| `raindec/common.yaml` | 공용 사전 (최소판) |
| `scenarios/객잔.yaml` | 시험용 시나리오 한 장면 |
| `experiments/` | 측정 코드와 원자료 |

```
pip install pyyaml requests pytest
python -m pytest tests            # LLM 없이 도는 시험
python play.py --fake --bench     # LLM 없이 흐름 확인
python play.py --bench            # 정해 둔 선언을 한 세션으로 돌리고 시간·값을 잰다 (Gemini API 필요)
python play.py                    # 직접 플레이
```

API 키는 코드와 저장소에 두지 않는다. 실행 환경이 요청에 붙이거나, `GEMINI_API_KEY`에서 읽는다.
호출의 누적 지출(추정)은 `.spend.json`에 적히고, 상한(`--cap`, 기본 1,500원)에 닿으면 호출을 멈춘다.

아직 없는 것은 [docs/37](docs/37-뼈대와-이어-돌린-실측.md) §1과 §5에 있다. 판정의 값과 동작의 목록은 첫 판이다.
