"""Concrete disposable boundary scenarios for a trusted D2 instrumentation hook.

The hook owns path/handle operations inside its newly created fixture. These
definitions cannot select a host path, shell command, URL or credential source.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BoundaryScenario:
    hook: str
    source_id: str
    operation: str
    stimulus: str
    required_error_codes: tuple[str, ...]
    byte_limit: int = 8 * 1024 * 1024
    physical_line_limit: int = 64 * 1024
    frame_limit: int = 32 * 1024
    deadline_seconds: float = 5.0


SCENARIOS = {
    "read-byte-cap": BoundaryScenario("read-byte-cap", "app", "read",
        "exclusive generated source exceeds 8 MiB by one byte", ("LIMIT_EXCEEDED",)),
    "physical-line-cap": BoundaryScenario("physical-line-cap", "app", "read",
        "exclusive source contains one 65537-byte physical UTF-8 line", ("LIMIT_EXCEEDED",)),
    "deadline": BoundaryScenario("deadline", "app", "read",
        "trusted monotonic-clock/barrier advances beyond the five-second call deadline before I/O", ("LIMIT_EXCEEDED",)),
    "frame-amplification": BoundaryScenario("frame-amplification", "app", "tail",
        "bounded raw quote/backslash/tab/multibyte lines amplify the full JSON-RPC text+structured frame", ("LIMIT_EXCEEDED",)),
    "posix-symlink": BoundaryScenario("posix-symlink", "app", "read",
        "replace configured basename with a symlink to a second canary file in the SAME disposable fixture", ("PATH_FORBIDDEN", "SOURCE_CHANGED")),
    "posix-rename": BoundaryScenario("posix-rename", "app", "read",
        "trusted read barrier renames configured basename and installs a different inode in the SAME fixture", ("SOURCE_CHANGED",)),
    "posix-nonlocal": BoundaryScenario("posix-nonlocal", "app", "configuration",
        "trusted platform control supplies an independently identified unsupported mount; never mounts or contacts a network", ("SOURCE_NOT_LOCAL",)),
    "posix-source-change": BoundaryScenario("posix-source-change", "app", "read",
        "mutate bytes of the configured disposable source after initial manifest binding", ("SOURCE_CHANGED",)),
}


def exercise_boundary(hook, driver):
    """Driver implements real bounded fixture mutation, operation and observation.

    A missing driver is unavailable, not a simulated boundary success. The driver
    must create mutated files before binding when testing size/line caps, and
    after binding when testing source change. Every observation retains lineage.
    """
    scenario = SCENARIOS[hook]
    evidence = driver.exercise_scenario(scenario)
    if not isinstance(evidence, dict):
        raise ValueError("boundary driver returned no evidence")
    # Preserve raw error and observed effects; runner classifies independently.
    return {**evidence, "required_error_codes": list(scenario.required_error_codes)}
