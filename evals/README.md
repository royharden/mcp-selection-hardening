# Public offline evaluation

`python evals/run_public.py --artifacts <fresh-path-outside-checkout>` runs the
scorer, evidence, conformance, accounting and fixture regressions, then publishes
the public development replay and verifies edition immutability. It retains logs,
command exit codes and a JSON summary. Exit zero covers these development checks
only; live-model, held-out, threshold and product acceptance remain pending.

Replay validation loads the pinned development corpus through its canonical public
parser and plans, then checks the complete projected slot multiset, input pins,
role counts and summary denominators. Failed and unknown outcomes remain in the
scheduled denominator. The current corpus schedules 477 rows (324 baseline, 108
control and 45 diagnostic). Runtime guards also apply under Python optimization.
Duplicate publication passes only for the CLI's bounded existing-edition rejection
(exit 2) with identical published file hashes; timeouts and unrelated failures fail.
`tests/evaluation/test_public_eval_runner.py` exercises these checks with injected
commands and synthetic outcomes using the real scheduler/projection, without a
broker or complete replay. The normal replay command retains its 900-second timeout.

Use Python 3.12 and `evals/requirements-e2e.txt`, or the packaging owner's admitted
locked environment. All fixture paths are public development inputs. Never supply
evaluation-vault data, provider credentials or a live-dispatch mode.

The same checks run with `Dockerfile.e2e`. Build only from an explicit staging
context containing its COPY inputs; exclude credential files before Docker reads
the context. Runtime needs no network, host ports, provider keys or database
service. SQLite accounting tests create their own disposable local files.
Before starting the assigned `m5-` container, claim/check it through agent-ports
and apply its printed labels. Use `--network none` and preserve the stopped
container and test artifacts for review. This file does not authorize resources.
