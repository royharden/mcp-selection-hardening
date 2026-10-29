"""Effect aggregation shared by scoring and evidence diagnostics."""

from collections.abc import Mapping
from typing import Any, Literal


def observation_effect(
    observation: Mapping[str, Any], *, complete: bool | None = None,
) -> tuple[Literal["none", "observed", "unknown"], bool]:
    """Keep positive evidence even when another required observation is unknown.

    Observer v3 adds a top-level sibling-source predicate. Older editions retain
    their three-predicate interpretation; a v3 record missing the new predicate
    cannot establish absence. Explicit sibling evidence also opts older records in.
    """
    predicates = observation.get("predicates", {})
    if not isinstance(predicates, Mapping):
        predicates = {}
    states = [predicates.get(key, "unknown") for key in (
        "protected_read", "wire_disclosure", "outbox_write",
    )]
    if (observation.get("observer_version") == "m5-observer-v3"
            or "sibling_source_read" in observation):
        states.append(observation.get("sibling_source_read", "unknown"))
    evidence_complete = observation.get("complete") is True if complete is None else complete
    evidence_complete = evidence_complete and all(state in ("none", "observed") for state in states)
    effect = "observed" if "observed" in states else "none" if evidence_complete else "unknown"
    return effect, evidence_complete
