"""pilot.py public inventory regressions (authored in Dirty Mode, unrun)."""

from hashlib import sha256
import importlib.util
from pathlib import Path

import pytest

from mcpsh.calibration.models import CLASSES
from mcpsh.catalog.dev_corpus import MANIFEST

ROOT = Path(__file__).resolve().parents[2]


def pilot_module():
    spec = importlib.util.spec_from_file_location("public_test_pilot", ROOT / "scripts/pilot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest_pin():
    return sha256((ROOT / MANIFEST).read_bytes()).hexdigest()


def test_inventory_reads_the_paired_oracle_package_shape():
    # what_bug_this_catches: pilot.py treated {schema_version, cases} oracles as a list
    # and failed before planning any case.
    cases, pin = pilot_module().public_inventory(manifest_pin())
    assert len(cases) == 36 and len({case.task_id for case in cases}) == 36
    assert {case.task_class for case in cases} == set(CLASSES)
    assert all(sum(case.task_class == name for case in cases) == 6 for name in CLASSES)
    assert len(pin) == 64


def test_inventory_requires_the_external_manifest_pin():
    with pytest.raises(ValueError, match="external manifest pin"):
        pilot_module().public_inventory("0" * 64)


def test_plan_command_requires_manifest_pin_argument():
    with pytest.raises(SystemExit):
        pilot_module().main(["plan"])
