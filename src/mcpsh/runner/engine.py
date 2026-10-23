"""Ordered, capped replay execution. No provider receives scorer-only labels."""

import json
import time
from typing import Any

from mcpsh import BANNER
from mcpsh.evaluation import aggregate_outcomes, paired_family_bootstrap, score_trial
from mcpsh.records import ExperimentManifest, ModelAttempt, OracleCase, PublicTaskCase, public_task_projection, typed_hash


def _admit_live(selector: Any, manifest: ExperimentManifest | None) -> None:
    if manifest is None or manifest.mode != "live":
        raise ValueError("live execution requires an explicit immutable live manifest")
    settings = manifest.settings
    if settings.get("dirty_mode_closed") is not True or settings.get("live_authorized") is not True:
        raise ValueError("live runtime/spend authorization and Dirty Mode closure are required")
    if not manifest.budget_receipt or not manifest.prices or not manifest.lock_hash or not manifest.protocol_hash:
        raise ValueError("live budget, dated prices and dependency lock are required")
    families = settings.get("family_by_model", {})
    if not isinstance(families, dict) or len(manifest.model_ids) != 2:
        raise ValueError("the selected live experiment requires two exact model arms")
    if len({families.get(model) for model in manifest.model_ids}) != 2 or any(
        not families.get(model) for model in manifest.model_ids
    ):
        raise ValueError("two genuinely distinct approved model families are required")
    if settings.get("custody_seal_verified") is not True or not settings.get("custodian_id"):
        raise ValueError("independent custody/seal verification is required")
    arm = getattr(selector, "arm", None)
    if arm is None or arm.model not in manifest.model_ids or families[arm.model] != arm.family:
        raise ValueError("selector identity does not match the approved manifest")
    if getattr(selector, "provenance", None) != "live-provider-transport":
        raise ValueError("a replay/control selector cannot be counted as a live arm")


def run_trial(*, task: PublicTaskCase, oracle: OracleCase, selector: Any,
              catalog: list[dict[str, Any]], trial_id: str, condition: str, cell: str,
              mode: str, selector_name: str = "scripted-replay", max_turns: int = 3,
              max_calls: int = 6, execution_mode: str = "replay",
              manifest: ExperimentManifest | None = None,
              platform_scope: str = "synthetic-memory", filesystem_config=None,
              fixture_payload=None) -> dict[str, Any]:
    from mcpsh.server import ReferenceServer

    if task.task_id != oracle.task_id:
        raise ValueError("task/oracle identity mismatch")
    if execution_mode not in ("replay", "live"):
        raise ValueError("unsupported execution mode")
    if execution_mode == "live":
        _admit_live(selector, manifest)
        if platform_scope != manifest.platform_scope:
            raise ValueError("runtime platform differs from approved manifest")
    elif getattr(selector, "provenance", None) == "live-provider-transport":
        raise ValueError("live selector cannot execute in the replay path")
    if execution_mode == "replay" and oracle.split != "development":
        raise ValueError("this development runner does not admit hidden/retired oracle packages")
    if not 1 <= max_turns <= 3 or not 1 <= max_calls <= 6:
        raise ValueError("runner caps exceed frozen plan")
    started = time.monotonic()
    trace: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    failures: list[str] = []
    observation: dict[str, Any] = {"complete": False, "predicates": {}}
    server = None
    transport = getattr(selector, "transport", None)
    attempt_start = len(getattr(transport, "attempts", []))
    try:
        server = ReferenceServer(mode=mode, allowed_sources=task.allowed_source_ids,
                                 trial_id=trial_id, platform_scope=platform_scope,
                                 filesystem_config=filesystem_config, fixture_payload=fixture_payload)
        for turn in range(1, max_turns + 1):
            deadline = manifest.settings.get("task_deadline_seconds") if manifest else None
            if execution_mode == "live" and (type(deadline) not in (int, float) or deadline <= 0):
                raise ValueError("approved task deadline required")
            if deadline is not None and time.monotonic() - started >= deadline:
                failures.append("task_deadline_exceeded")
                break
            public = public_task_projection(task)
            calls = selector.select(public, catalog, list(history))
            if deadline is not None and time.monotonic() - started >= deadline:
                failures.append("task_deadline_exceeded")
                break
            if not isinstance(calls, list):
                failures.append("selector_invalid_call_batch")
                break
            if not calls:
                break
            # Refuse an oversized batch before dispatch; do not quietly omit its late calls.
            if len(trace) + len(calls) > max_calls:
                failures.append("call_limit_exceeded")
                break
            for selected in calls:
                if not isinstance(selected, dict) or set(selected) != {"name", "arguments"}:
                    failures.append("selector_invalid_call")
                    continue
                if not isinstance(selected["name"], str) or not isinstance(selected["arguments"], str):
                    failures.append("selector_invalid_call_types")
                    continue
                packet = server.call(selected["name"], selected["arguments"])
                result = packet["result"]
                # This is the runner's response capture, outside the handler's assertions.
                wire = json.dumps(result, ensure_ascii=True, separators=(",", ":"),
                                  allow_nan=False).encode("utf-8")
                server.capture_wire(wire)
                attempts_now = getattr(transport, "attempts", [])
                attempt_id = attempts_now[-1].get("attempt_id") if attempts_now else None
                event = {**packet["event"], "trial_id": trial_id, "turn_id": turn,
                         "sequence": len(trace) + 1, "enforcement_mode": mode,
                         "model_attempt_id": attempt_id}
                trace.append(event)
                results.append(result)
                history.append({"role": "tool", "content": json.dumps(result, ensure_ascii=True),
                                "tool_call_id": event["call_id"],
                                "call": dict(selected), "result": result})
            if turn == max_turns:
                failures.append("turn_limit_reached")
        observation = server.observe()
    except Exception as exc:
        # Do not serialize exception messages: they can contain private labels/payloads.
        failures.append(f"infrastructure:{type(exc).__name__}")
        if server is not None:
            try:
                observation = server.observe()
            except Exception:
                observation = {"complete": False, "predicates": {}}
    finally:
        if server is not None:
            try:
                server.close()
            except Exception as exc:
                failures.append(f"teardown:{type(exc).__name__}")
                observation = {**observation, "complete": False}
    attempts = list(getattr(transport, "attempts", []))[attempt_start:]
    cost = 0 if execution_mode == "replay" else None
    cost_status = "non-model" if execution_mode == "replay" else "unknown"
    if execution_mode == "live" and attempts and all(
        isinstance(item.get("cost_microunits"), int) for item in attempts
    ):
        cost = sum(item["cost_microunits"] for item in attempts)
        cost_status = "settled"
    arm = getattr(selector, "arm", None)
    outcome = score_trial(trial_id=trial_id, oracle=oracle, trace=trace, results=results,
                          observation=observation, condition=condition, cell=cell,
                          selector=selector_name, failures=failures,
                          latency_seconds=float(time.monotonic() - started),
                          execution_mode=execution_mode,
                          provider_id=getattr(arm, "provider", None),
                          model_id=getattr(arm, "model", None),
                          model_attempt_ids=tuple(item["attempt_id"] for item in attempts),
                          cost_microunits=cost, cost_status=cost_status,
                          cost_basis="non-model" if execution_mode == "replay" else
                          "dated-price-estimate" if cost_status == "settled" else "unknown")
    normalized_attempts = [ModelAttempt(
        attempt_id=item["attempt_id"], request_id=item.get("request_id"),
        response_id=item.get("response_id"), raw_response_hash=item.get("raw_response_hash"),
        provider_id=item["provider"], requested_model_id=item["requested_model"],
        returned_model_id=item.get("returned_model"), started_at=item["started_at"],
        finished_at=item.get("finished_at"), status=item["status"], usage=item.get("usage", {}),
        settlement_reference=item.get("settlement_reference"),
    ).model_dump(mode="json") for item in attempts]
    return {"outcome": outcome.model_dump(mode="json"), "trace": trace,
            "results": results, "observation": observation,
            "public_task": public_task_projection(task), "catalog_hash": typed_hash(catalog),
            "fixture_ref": task.fixture_ref,
            "fixture_payload_hash": typed_hash(fixture_payload) if fixture_payload is not None else None,
            "model_attempts": normalized_attempts, "accounting_attempts": attempts}


def run_live_matrix(*, manifest: ExperimentManifest, cases, selector_factory,
                    filesystem_config=None, fixture_map, treatment_map) -> dict[str, Any]:
    """Approved closed-loop source path; every scheduled failure remains in the edition.

    The caller verifies an explicit approval receipt and raw oracle-package seal before
    calling. Selectors/controllers are freshly allocated per trial, with a shared durable
    ledger and unique operation IDs. This function never publishes files.
    """
    import random

    from mcpsh.lint import normalize_catalog
    from .sealed import CONDITIONS, treatment_catalog

    if manifest.mode != "live" or manifest.matrix != ("C0", "C1", "C2"):
        raise ValueError("live core requires the approved three-cell manifest")
    if manifest.settings.get("dirty_mode_closed") is not True or manifest.settings.get("live_authorized") is not True:
        raise ValueError("live runtime remains unauthorized")
    cases = list(cases)
    if not cases or manifest.task_hash != typed_hash([public_task_projection(task) for task, _ in cases]):
        raise ValueError("public task corpus differs from manifest")
    phase = manifest.settings.get("corpus_phase")
    if phase == "heldout":
        if len(cases) != 24 or any(oracle.split != "heldout" for _, oracle in cases):
            raise ValueError("primary matrix requires 24 independently sealed held-out cases")
        if len({oracle.family_id for _, oracle in cases}) != 24:
            raise ValueError("primary matrix requires 24 independently attributed task families")
    elif phase != "development-pilot" or any(oracle.split != "development" for _, oracle in cases):
        raise ValueError("unapproved corpus phase")
    repeats = manifest.settings.get("repeats", 3)
    if type(repeats) is not int or repeats not in (3, 5):
        raise ValueError("repeats must be approved before held-out access")
    if manifest.platform_scope == "filesystem-posix" and not callable(filesystem_config):
        raise ValueError("POSIX matrix requires a fresh disposable fixture factory per trial")
    if manifest.platform_scope == "synthetic-memory" and filesystem_config is not None:
        raise ValueError("memory mode cannot receive host filesystem configuration")
    if set(treatment_map) != {task.task_id for task, _ in cases}:
        raise ValueError("every sealed task requires its exact metadata treatments")
    catalogs = {task.task_id: {condition: treatment_catalog(treatment_map[task.task_id], condition)
                               for condition in CONDITIONS} for task, _ in cases}
    if manifest.catalog_hash != typed_hash(catalogs):
        raise ValueError("catalog/schema set differs from immutable manifest")
    schedule = [(task, oracle, model, condition, cell, repeat)
                for task, oracle in cases for model in manifest.model_ids
                for condition in CONDITIONS for cell in manifest.matrix for repeat in range(repeats)]
    random.Random(manifest.seed).shuffle(schedule)
    rows = []
    stop_reason = None
    for index, (task, oracle, model, condition, cell, repeat) in enumerate(schedule):
        trial_id = f"{manifest.edition_id}-{index:05d}-{repeat}"
        catalog = catalogs[task.task_id][condition]
        diffs = []
        if cell == "C2":
            catalog, diffs = normalize_catalog(catalog)
        try:
            if stop_reason:
                raise RuntimeError("dispatch stopped: " + stop_reason)
            selector = selector_factory(model, trial_id)
            _admit_live(selector, manifest)
            fixture_payload = fixture_map[task.fixture_ref]
            trial_config = filesystem_config(trial_id, fixture_payload) if callable(filesystem_config) else None
            row = run_trial(task=task, oracle=oracle, selector=selector, catalog=catalog,
                            trial_id=trial_id, condition=condition, cell=cell,
                            mode="permissive" if cell == "C0" else "hardened",
                            selector_name=model, max_turns=manifest.max_turns,
                            max_calls=manifest.max_calls, execution_mode="live", manifest=manifest,
                            platform_scope=manifest.platform_scope,
                            filesystem_config=trial_config, fixture_payload=fixture_payload)
            row["normalization_diff_hash"] = typed_hash(diffs)
            row["metadata_diffs"] = diffs
            # Unknown money/identity/observation is not a reason to keep dispatching.
            if row["outcome"]["cost_status"] in ("unknown", "reserved"):
                stop_reason = "unsettled_cost_or_admission"
            elif not row["outcome"]["observation_complete"]:
                stop_reason = "observation_or_isolation_incomplete"
            elif any(any(kind in failure for kind in ("LiveDispatchDenied", "LiveTransportError"))
                     for failure in row["outcome"]["failures"]):
                stop_reason = "live_identity_or_admission_failure"
        except Exception as exc:
            failure = "not_dispatched:" + (stop_reason or type(exc).__name__)
            outcome = score_trial(trial_id=trial_id, oracle=oracle, trace=[], results=[],
                                  observation={"complete": False, "predicates": {}},
                                  condition=condition, cell=cell, selector=model,
                                  failures=[failure], latency_seconds=0.0,
                                  execution_mode="live", model_id=model,
                                  cost_microunits=None, cost_status="unknown", cost_basis="unknown")
            row = {"outcome": outcome.model_dump(mode="json"), "trace": [], "results": [],
                   "observation": {"complete": False, "predicates": {}},
                   "public_task": public_task_projection(task), "catalog_hash": typed_hash(catalog),
                   "model_attempts": [], "fixture_ref": task.fixture_ref}
            stop_reason = stop_reason or type(exc).__name__
        rows.append(row)
    outcomes = [row["outcome"] for row in rows]
    paired = []
    for model in manifest.model_ids:
        for condition in CONDITIONS:
            selected = [item for item in outcomes if item["model_id"] == model
                        and item["condition"] == condition]
            for before, after in (("C0", "C1"), ("C1", "C2"), ("C0", "C2")):
                paired.append({"model_id": model, "condition": condition,
                               **paired_family_bootstrap(selected, before=before, after=after,
                                                         seed=manifest.seed)})
    return {"schema_version": 1, "banner": "live experiment; independent acceptance pending",
            "execution_state": "partial" if stop_reason else "live-complete",
            "acceptance_verdict": "pending", "platform_scope": manifest.platform_scope,
            "development_only": phase != "heldout", "seed": manifest.seed,
            "manifest": manifest.model_dump(mode="json"), "rows": rows,
            "summary": aggregate_outcomes(outcomes), "paired_comparisons": paired,
            "dispatch_stop_reason": stop_reason,
            "limitations": ["Execution state does not establish independent product acceptance.",
                            "All scheduled failures and unknowns remain in denominators.",
                            "Live and replay editions are never pooled."]}


def run_matrix(*, seed: int = 1729, cases=None) -> dict[str, Any]:
    """A development diagnostic matrix, never a live-model or held-out experiment."""
    import random

    from mcpsh.adapters import KeywordSelector, ReplaySelector
    from mcpsh.catalog import build_catalog
    from mcpsh.lint import normalize_catalog

    from .cases import demonstration_cases

    rows = []
    schedule = []
    for task, oracle, calls in demonstration_cases() if cases is None else cases:
        for condition in ("clean", "ambiguous", "poisoned"):
            for cell, mode in (("C0", "permissive"), ("C1", "hardened"), ("C2", "hardened")):
                schedule.append((task, oracle, calls, condition, cell, mode, "scripted-replay"))
        # Controls have their own labelled arm and are never live samples.
        for control in ("keyword", "abstain", "deny-all"):
            schedule.append((task, oracle, calls, "clean", "control", "deny-all"
                             if control == "deny-all" else "hardened", control))
    random.Random(seed).shuffle(schedule)
    for index, (task, oracle, calls, condition, cell, mode, arm) in enumerate(schedule):
        catalog = build_catalog(condition)
        if cell == "C2":
            catalog, _ = normalize_catalog(catalog)
        selected = KeywordSelector() if arm == "keyword" else ReplaySelector(
            [] if arm == "abstain" else calls
        )
        rows.append(run_trial(task=task, oracle=oracle, selector=selected, catalog=catalog,
                              trial_id=f"replay-{index:04d}-{task.task_id}", condition=condition,
                              cell=cell, mode=mode, selector_name=arm))
    outcomes = [row["outcome"] for row in rows]
    comparisons = []
    for condition in ("clean", "ambiguous", "poisoned"):
        selected = [row for row in outcomes if row["selector"] == "scripted-replay"
                    and row["condition"] == condition]
        for before, after in (("C0", "C1"), ("C1", "C2"), ("C0", "C2")):
            comparisons.append({"selector": "scripted-replay", "condition": condition,
                                **paired_family_bootstrap(selected, before=before, after=after,
                                                          seed=seed)})
    return {"schema_version": 1, "banner": BANNER, "execution_state": "replay-only",
            "acceptance_verdict": "pending", "platform_scope": "synthetic-memory",
            "seed": seed, "live_model_runs": 0, "heldout_families": 0,
            "development_only": True, "rows": rows,
            "summary": aggregate_outcomes(outcomes), "paired_comparisons": comparisons,
            "limitations": ["Source constructed under Dirty Mode; runtime unverified.",
                            "Calls are scripted, not model-generated.",
                            "Author-seen development templates do not support held-out generalization.",
                            "Development oracle labels are agent-authored and independently unreviewed.",
                            "No POSIX or Windows filesystem conformance acceptance."]}
