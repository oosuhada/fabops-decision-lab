# M1 Gate Test Report

- Test profile: `m1-test-v1`, seed `42`
- Generated event count: `373`
- F1–F6: all present in evaluation-only ground truth
- Canonical event hash: `92f1c0df38d3812b2454398d030f1ad51fe6023efe85195fa322e6b4fcfe954a`
- Manifest-only regeneration: identical event and ground-truth hashes
- Referential integrity: Lot → ProcessRun/Step → Equipment/Chamber → Inspection verified
- F5: sensor-only shift with nominal yield
- F6: explicit data-quality incidents with no physical fault/yield impact
- M0 + M1 regression at gate: `18 passed`

