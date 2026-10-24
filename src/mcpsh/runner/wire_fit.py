"""Bind externally admitted full-wire counters to the actual trial catalog.

Only later admitted runtime calls invoke the injected counter. Proofs are private
request evidence, not provider interoperability or spend authorization.
"""

from copy import deepcopy
from datetime import datetime, timezone

from mcpsh.adapters import LiveSelector
from mcpsh.catalog.artifacts import artifact_pins, build_catalog_artifact
from mcpsh.catalog.token_fit import build_token_fit_proof, verify_token_fit_proof
from mcpsh.records import typed_hash


class TrialWireCounter:
    def __init__(self, *, provider, model, adapter_revision, adapter_sha256,
                 approvals, expected_pins, tokenizer, journal, expires_at):
        if (not isinstance(approvals, dict) or not 1 <= len(approvals) <= 324
                or not isinstance(expected_pins, dict) or set(approvals) != set(expected_pins)):
            raise ValueError("bounded externally pinned catalog-fit approvals required")
        for catalog_hash, envelope in approvals.items():
            if (not isinstance(envelope, dict) or set(envelope) != {"approval", "approval_sha256"}
                    or not isinstance(envelope["approval"], dict)
                    or envelope["approval_sha256"] != expected_pins[catalog_hash]
                    or typed_hash(envelope["approval"]) != expected_pins[catalog_hash]):
                raise ValueError("token-fit approval differs from immutable manifest pin")
        self.provider, self.model = provider, model
        self.adapter_revision, self.adapter_sha256 = adapter_revision, adapter_sha256
        self.approvals = deepcopy(approvals)
        self.tokenizer, self.journal, self.expires_at = tokenizer, journal, expires_at
        self.context = None
        self.dispatch_context = None

    def bind_dispatch_context(self, *, phase: str, attempt_id: str | None,
                              operation_id: str | None) -> None:
        if phase == "preflight":
            valid = attempt_id is None and operation_id is None
        elif phase == "pre-send":
            valid = all(type(value) is str and 0 < len(value) <= 256
                        for value in (attempt_id, operation_id))
        else:
            valid = False
        if not valid:
            raise ValueError("exact preflight or pre-send dispatch context required")
        self.dispatch_context = (phase, attempt_id, operation_id)

    def bind(self, *, catalog, condition, normalized, ordering_seed, trial_id, turn_id):
        artifact = build_catalog_artifact(condition, ordering_seed=ordering_seed,
                                          catalog=catalog, normalized=normalized)
        if typed_hash(artifact["catalog"]) != typed_hash(catalog):
            raise ValueError("actual selector catalog differs from canonical artifact order/metadata")
        key = artifact_pins(artifact)["typed_sha256"]
        if key not in self.approvals:
            raise ValueError("actual catalog has no externally admitted token-fit approval")
        self.context = (artifact, self.approvals[key], trial_id, turn_id)

    def __call__(self, encoded_body: bytes) -> int:
        now = datetime.now(timezone.utc)
        dispatch_context, self.dispatch_context = self.dispatch_context, None
        if (self.context is None or dispatch_context is None or now >= self.expires_at
                or type(encoded_body) is not bytes):
            raise ValueError("bound unexpired exact-wire counter context required")
        artifact, envelope, trial_id, turn_id = self.context
        common = dict(artifact=artifact, provider=self.provider, model_id=self.model,
                      adapter_revision=self.adapter_revision, adapter_sha256=self.adapter_sha256,
                      approval=envelope["approval"], expected_approval_sha256=envelope["approval_sha256"],
                      trial_id=trial_id, turn_id=turn_id, at_time=now.isoformat())
        proof = build_token_fit_proof(encoded_body, tokenizer=self.tokenizer, **common)
        # This pin originates in this trusted producer/journal path; never accept
        # a submitted proof's own hash as its external verification authority.
        producer_pin = proof["proof_sha256"]
        import hashlib

        phase, attempt_id, operation_id = dispatch_context
        self.journal({"event": "token_fit_proof", "trial_id": trial_id,
                      "turn_id": turn_id, "proof_sha256": producer_pin, "proof": proof,
                      "phase": phase, "attempt_id": attempt_id, "operation_id": operation_id,
                      "raw_request_sha256": hashlib.sha256(encoded_body).hexdigest(),
                      "checked_at": now.isoformat()})
        verified = verify_token_fit_proof(proof, encoded_body,
                                         expected_proof_sha256=producer_pin, **common)
        if verified.get("valid") is not True or verified.get("fits") is not True:
            raise ValueError("unknown, mismatched or exceeding full-wire fit blocks dispatch")
        return proof["input_tokens"]


class FitBoundSelector(LiveSelector):
    """Keep scorer-only data out of provider payloads while binding catalog proof."""

    def __init__(self, *args, wire_counter, seed_by_task, **kwargs):
        super().__init__(*args, **kwargs)
        self.wire_counter, self.seed_by_task = wire_counter, dict(seed_by_task)
        self._trial_context = None
        self._proof_turn = 0

    def bind_trial_context(self, *, trial_id, condition, cell):
        if self._trial_context is not None or cell not in ("C0", "C1", "C2"):
            raise ValueError("one explicit trial context per live selector required")
        self._trial_context = (trial_id, condition, cell)

    def select(self, task, catalog, history):
        if self._trial_context is None:
            raise ValueError("runner trial context unavailable")
        trial_id, condition, cell = self._trial_context
        self._proof_turn += 1
        self.wire_counter.bind(catalog=catalog, condition=condition, normalized=cell == "C2",
                               ordering_seed=self.seed_by_task[task["task_id"]],
                               trial_id=trial_id, turn_id=self._proof_turn)
        return super().select(task, catalog, history)
