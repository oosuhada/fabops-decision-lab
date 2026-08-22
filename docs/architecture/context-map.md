# Context Map

```text
FabTwin Simulator
        |
        v
Event Contracts -> Ingestion -> Detection -> RCA -> Workflow -> Evaluation
                                      |
                                      v
                         Evidence / Decision artifacts
```

## Boundaries

- Simulator: creates reproducible synthetic fab events.
- Ingestion: validates contracts and handles event lifecycle.
- Detection: owns anomaly signals.
- RCA: owns deterministic candidate scoring.
- Workflow: owns approval state.
- Evaluation: owns hidden truth comparison.

