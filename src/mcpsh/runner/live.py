"""Fail-closed later live admission. Importing this module does not dispatch or read keys."""

import base64
import hashlib
import importlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from mcpsh.records import ExperimentManifest, OracleCase, PublicTaskCase, strict_json_loads


def prepare_live_run(*, manifest_path: Path, approval_path: Path, oracle_path: Path,
                     protocol_record: Path, product_root: Path, private_directory: Path,
                     source_hashes: dict[str, str]):
    """Read approved files first; initialize transports only after all admission checks.

    Token counting is an explicitly approved local callable over the complete wire
    body. There is no guessed chars/tokens fallback and no provider request for counts.
    The real model tokenizer and version must be supplied and verified in activation.
    """
    manifest_raw = manifest_path.read_bytes()
    manifest = ExperimentManifest.model_validate_json(manifest_raw)
    approval = strict_json_loads(approval_path.read_bytes())
    if not isinstance(approval, dict) or approval.get("project") != "mcp-selection-hardening":
        raise ValueError("explicit M5 approval receipt required")
    if any(approval.get(key) is not True for key in ("authorized", "dirty_mode_closed", "network_allowed")):
        raise ValueError("runtime/network/spend admission remains closed")
    if manifest.mode != "live" or approval.get("mode") != "live":
        raise ValueError("live admission cannot use replay provenance")
    if approval.get("manifest_sha256") != hashlib.sha256(manifest_raw).hexdigest():
        raise ValueError("approval is not bound to these exact manifest bytes")
    if not approval.get("receipt_id") or approval["receipt_id"] != manifest.budget_receipt:
        raise ValueError("budget authority receipt mismatch")
    expires = datetime.fromisoformat(approval["expires_at"].replace("Z", "+00:00"))
    if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
        raise ValueError("live approval expired or has no timezone")
    for field in ("code_hash", "policy_hash", "scorer_hash", "observer_hash"):
        if getattr(manifest, field) != source_hashes[field]:
            raise ValueError("approved source pin differs: " + field)
    lock = product_root / "uv.lock"
    if not lock.is_file() or manifest.lock_hash != hashlib.sha256(lock.read_bytes()).hexdigest():
        raise ValueError("verified dependency lock missing or changed")
    if manifest.protocol_hash != hashlib.sha256(protocol_record.read_bytes()).hexdigest():
        raise ValueError("SDK/protocol smoke record differs from approved pin")
    resolved_oracle = oracle_path.resolve()
    if manifest.settings.get("corpus_phase") == "heldout" and (
        resolved_oracle == product_root or product_root in resolved_oracle.parents
    ):
        raise ValueError("held-out oracle custody must remain outside the product repository")
    oracle_raw = resolved_oracle.read_bytes()
    if manifest.split_hash != hashlib.sha256(oracle_raw).hexdigest():
        raise ValueError("raw oracle package seal differs from approved corpus")
    package = strict_json_loads(oracle_raw)
    if package.get("schema_version") != 1 or not isinstance(package.get("cases"), list):
        raise ValueError("unsupported sealed oracle package")
    cases = []
    for item in package["cases"]:
        task = PublicTaskCase.model_validate_json(json.dumps(item["public"]))
        oracle = OracleCase.model_validate_json(json.dumps(item["oracle"]))
        if task.task_id != oracle.task_id:
            raise ValueError("sealed public/oracle task ID mismatch")
        from mcpsh.records import canonical_json
        from mcpsh.server.validation import parse_arguments

        for alternative in oracle.alternatives + oracle.utility_alternatives:
            for predicate in alternative:
                parse_arguments(predicate.tool_name, canonical_json(predicate.arguments))
        cases.append((task, oracle))
    counter_spec = approval.get("token_counter")
    if not isinstance(counter_spec, str) or counter_spec.count(":") != 1 or not approval.get("token_counter_version"):
        raise ValueError("versioned full-wire token counter is required")
    if counter_spec != manifest.settings.get("token_counter"):
        raise ValueError("token-counter callable differs from manifest")
    module_name, attribute = counter_spec.split(":")
    token_counter = getattr(importlib.import_module(module_name), attribute)
    if not callable(token_counter):
        raise ValueError("approved token counter is not callable")
    arms = approval.get("arms")
    if not isinstance(arms, list) or len(arms) != 2:
        raise ValueError("two explicit approved live arm configurations are required")
    by_model = {arm["model"]: arm for arm in arms}
    if len(by_model) != 2 or set(by_model) != set(manifest.model_ids):
        raise ValueError("approved arm identities differ from experiment")
    if len({arm["family"] for arm in arms}) != 2:
        raise ValueError("two distinct approved model families are required")
    budget = approval.get("budget_microunits")
    if type(budget) is not int or budget <= 0:
        raise ValueError("positive bounded live budget required")
    private_directory.mkdir(parents=True, exist_ok=False)

    from mcpsh.accounting import CostLedger
    from mcpsh.adapters import LiveArm, LiveSelector
    from mcpsh.adapters.live import BudgetedLiveTransport, DatedTokenPrices
    from mcpsh.adapters.transports import AnthropicMessagesTransport, OpenAIChatTransport

    ledger = CostLedger(private_directory / "cost-ledger.sqlite", budget)

    def journal_safe(value):
        if isinstance(value, bytes):
            return {"encoding": "base64", "bytes": base64.b64encode(value).decode("ascii")}
        if isinstance(value, dict):
            return {key: journal_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [journal_safe(item) for item in value]
        return value

    def journal(event):
        # Journal is private, flushed before send by the controller; credentials are never payloads.
        with (private_directory / "provider-attempts.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(journal_safe(event), ensure_ascii=True, allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def selector_factory(model, trial_id):
        if datetime.now(timezone.utc) >= expires:
            raise ValueError("live approval expired before trial dispatch")
        row = by_model[model]
        provider = row["provider"]
        prices = DatedTokenPrices(**manifest.prices[model])
        if prices.snapshot_hash != row["price_snapshot_hash"]:
            raise ValueError("approved dated price snapshot differs")
        environment_name = row["key_environment_name"]
        if not isinstance(environment_name, str) or not environment_name or not all(
            character.isalnum() or character == "_" for character in environment_name
        ):
            raise ValueError("invalid credential environment variable name")

        def credential():
            # Evaluated only by the admitted transport immediately before a later send.
            value = os.environ.get(environment_name)
            if not value:
                raise ValueError("approved credential environment variable is absent")
            return value

        grant = {**row, "authorized": True, "dirty_mode_closed": True,
                 "network_allowed": True, "mode": "live",
                 "budget_reservation_id": approval["receipt_id"] + ":" + trial_id,
                 "corpus_seal_hash": manifest.split_hash,
                 "token_counter_version": approval["token_counter_version"]}
        common = {"credential": credential, "endpoint_url": row["endpoint_url"],
                  "network_enabled": True, "timeout_seconds": row.get("timeout_seconds", 30)}
        if provider == "openai":
            wire = OpenAIChatTransport(**common)
        elif provider == "anthropic":
            wire = AnthropicMessagesTransport(**common, api_version=row["api_version"])
        else:
            raise ValueError("unsupported approved provider")
        def count_approved_wire(body):
            if datetime.now(timezone.utc) >= expires:
                raise ValueError("live approval expired before model dispatch")
            return token_counter(body)

        controller = BudgetedLiveTransport(wire, ledger, grant, prices, count_approved_wire, journal)
        arm = LiveArm(provider, row["family"], model, environment_name)
        return LiveSelector(arm, transport=controller, approval=grant)

    return manifest, cases, selector_factory
