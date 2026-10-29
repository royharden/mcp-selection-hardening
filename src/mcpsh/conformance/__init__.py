"""Explicit local conformance entrypoint; no test/backend execution on import."""

from .models import ConformanceReport, ConformanceRequest, ProbeResult, Status
from .runner import run_conformance
from .capabilities import capability_report

__all__ = ["ConformanceReport", "ConformanceRequest", "ProbeResult", "Status", "run_conformance", "capability_report"]
