# Public offline evaluation

`python evals/run_public.py --artifacts <fresh-path-outside-checkout>` runs the
scorer, evidence, conformance, accounting and fixture regressions, then publishes
the public development replay and verifies edition immutability. It retains logs,
command exit codes and a JSON summary. Exit zero covers these development checks
only; live-model, held-out, threshold and product acceptance remain pending.

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
