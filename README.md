# FabOps Decision Lab — Evidence-Grounded Yield Excursion Triage

반도체 수율 이상 대응을 위한 evidence-grounded engineering decision platform입니다. 공개 데이터와 재현 가능한 합성 Fab 이벤트를 바탕으로 이상 탐지, 원인 분석, 엔지니어 승인, 조치 이력과 평가를 하나의 의사결정 흐름으로 연결합니다.

## Problem

Yield/Process Engineer가 excursion 발생 후 15~30분 안에 다음을 판단할 수 있도록 한다.

- 실제 공정 이상인가, 데이터 품질 문제인가?
- 영향 Lot/Wafer/Step/Equipment는 무엇인가?
- 원인 후보를 지지하거나 반박하는 근거는 무엇인가?
- 어떤 대응을 승인해야 하는가?

## Architecture highlights

- Deterministic simulation and hidden ground-truth evaluation
- SPC/EWMA-based detection and evidence-grounded RCA
- Human approval-gated action workflow and audit trail
- Contract-driven adapters for external data, models, and operational systems
- AI advisory layer separated from authoritative engineering decisions

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

## Documentation

- [Roadmap](ROADMAP.md)
- [Project charter](docs/PROJECT_CHARTER.md)
- [System context map](docs/architecture/context-map.md)
