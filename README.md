# FabOps Decision Lab — Evidence-Grounded Yield Excursion Triage

반도체 수율 이상 대응을 위한 evidence-grounded engineering decision platform.

## Problem

Yield/Process Engineer가 excursion 발생 후 15~30분 안에 다음을 판단할 수 있도록 한다.

- 실제 공정 이상인가, 데이터 품질 문제인가?
- 영향 Lot/Wafer/Step/Equipment는 무엇인가?
- 원인 후보를 지지하거나 반박하는 근거는 무엇인가?
- 어떤 대응을 승인해야 하는가?

## Decision boundary

M0에서는 deterministic foundation만 구현한다.

- Simulator가 이벤트와 hidden ground truth를 생성한다.
- Operational artifact는 ground truth를 읽지 않는다.
- AI/Agent는 advisory layer이며 source of truth가 아니다.

## Data provenance

| Type | Meaning |
|---|---|
| Real | UCI SECOM, WM-811K, AI4I 등의 공개 데이터 anchor |
| Synthetic | FabTwin-Sim이 seed 기반 생성한 이벤트 |
| Inferred | Detection/RCA/Evaluation 결과 |

## Run

```bash
uv run pytest
uv run python -m simulator.generate --seed 42 --output evidence/sample
```

## Non-goals

- 실제 Fab MES 복제
- 자동 장비 제어
- LLM 단독 원인 판정
- synthetic data를 실제 fab lineage로 주장

