# M5 Evaluation Report

Release gate: **PASS**.

Held-out seeds: `[211, 223, 227]` using common random numbers for current-vs-legacy detector comparison.

## Checked metrics

- Detector fault recall: 1.000
- RCA Top-1 / Top-3 / MRR: 1.000 / 1.000 / 1.000
- Tool selection: 1.000
- Required evidence retrieval: 1.000
- Unsupported claims: 0.000
- Unsafe action proposals: 0.000
- Human override proxy: 0.000
- U1 unseen-family abstention appropriateness: 1.000

## Negative results / limitations

- Contradicting-evidence coverage is 0.429; not every correct candidate has explicit counter-evidence in the compact synthetic fixture.
- Legacy comparison detector recall is 0.867 on the same held-out random streams; it is retained as a failing/weaker baseline rather than hidden.

No synthetic-to-real performance claim is made.
