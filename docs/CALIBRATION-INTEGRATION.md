# Calibration publisher and admitted-runner integration

Source constructed under Dirty Mode; no planner, summarizer, tokenizer, test, clock callback, model, fixture or runner has been executed.

The six-case producer `scripts/pilot.py plan --development-manifest-sha256 <raw-manifest-pin>` emits exactly a `manifest`, `planned_caps` and `threshold_proposal` envelope. The sole evaluator accepts this real envelope or a standalone typed `DraftPilotManifest`. Cached counts/proposals are re-derived and compared as typed JSON, so metadata cannot turn strings/booleans into numeric planning authority. All raw input files still require explicit byte pins.

The full public development publication route is:

```text
python scripts/eval.py --mode development-summary \
  --development-plan full36-plan.json --development-plan-sha256 RAW_SHA256 \
  --calibration-outcomes outcomes.json --calibration-outcomes-sha256 RAW_SHA256 \
  [--calibration-failures failures.json --calibration-failures-sha256 RAW_SHA256]
```

The plan is a strict `DevelopmentProtocolPlan` from the calibration library. Outcome arrays contain `CalibrationOutcome` records; failure arrays contain `ProtocolFailure` records. The publisher preserves supplied raw files privately, calls the frozen summary/proposal API, and writes one bounded/redacted result edition. JSON/CSV/Markdown/HTML use the same precomputed groups and disclose every scheduled/missing/unknown/proxy slot. It never manufactures an absolute floor, independent family judgment or dispatch permission. A six-case pilot is not silently promoted into full-36 evidence.

The callback bridge is `mcpsh.runner.execute_admitted_development_protocol`. It accepts an explicit `ProtocolAdmission`, injected clock, separately admitted `ExperimentManifest`, exact public task/oracle map, existing selector factory and optional trusted data-only fixture map. POSIX use needs a fresh approved per-slot filesystem factory. There is no executable fixture loader or default provider/clock/backend. The source ties task/inventory/settings hashes to the plan, refuses held-out/retired labels and requires explicit semantic-v2 predicates.

For model slots, existing per-turn/per-send admission, price, token, identity and unknown-usage gates remain active through `run_trial`. Live use also requires an injected typed attempt/output counter mapper and the same model-dispatch receipt. The mapper must bind its record to the complete captured row hash; it may not infer malformed output from an incorrect answer. Missing mapper evidence refuses live dispatch rather than inventing zero/valid counters. Keyword, abstain and deny-all controls remain non-model replay with no provider identity or charge.

The frozen calibration orchestrator validates exact pilot/plan/settings pins, Dirty Mode closure, expiry and schedule before each callback. Failed, unknown, wrong-slot or unsettled evidence stops further callbacks while retaining scheduled failures. The bridge returns `DevelopmentExecution(protocol_run, private_rows)` in memory and writes no edition. A trusted publisher may inject a private row sink; no sink or callback was invoked during construction.

Current public development labels may still be explicitly legacy call proxies. Those cannot satisfy this semantic bridge; an authorized public semantic-label conversion/adjudication package is required before actual full36 calibration. No retired hidden example is a substitute. See [CALIBRATION.md](CALIBRATION.md) for the producer's protocol and retention boundaries.
