"""Publisher copy of D7's public normative status; never recomputed here.

The publisher has no conformance documents, so it cannot rerun
`verify_producer_bindings`. It copies `project_normative_status` only for a
producer-binding result that is bound to externally pinned authority: typed report
hash, producer authority hash and the edition's source index. Anything unbound or
malformed is omitted rather than shown as zeros.
"""

from mcpsh.evidence import project_normative_status
from mcpsh.records import typed_hash

STATUS_KEY = "normative_v3_status"


def bound_normative_status(producer_report, *, expected_report_sha256: str | None,
                           expected_authority_sha256: str | None, source_index_sha256: str) -> dict | None:
    if (type(producer_report) is not dict or not expected_report_sha256 or not expected_authority_sha256):
        return None
    try:
        if (typed_hash(producer_report) != expected_report_sha256
                or producer_report.get("authority_sha256") != expected_authority_sha256
                or producer_report.get("source_index_sha256") != source_index_sha256):
            return None
        return project_normative_status(producer_report)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None


def attach_normative_status(result: dict, producer_report, **pins) -> dict:
    """Mutates and returns `result`; the canonical projection whitelists the key."""
    status = bound_normative_status(producer_report, **pins)
    if status is None:
        result.pop(STATUS_KEY, None)
    else:
        result[STATUS_KEY] = status
    return result
