"""Tests for the live-schema drift check."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_schema.py"
spec = importlib.util.spec_from_file_location("check_schema", SCRIPT)
check_schema = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_schema)


def test_reports_missing_field() -> None:
    """A field we read being renamed upstream is a failure, not a warning."""
    descriptor = {
        "file": [
            {
                "package": "chores.v1",
                "messageType": [
                    {"name": "TaskOccurrence", "field": [{"jsonName": "taskId"}]}
                ],
            }
        ]
    }

    problems = check_schema.check(descriptor)
    assert any("TaskOccurrence is missing field" in p for p in problems)


@pytest.mark.skipif(shutil.which("buf") is None, reason="buf is not installed")
def test_live_schema_still_fits() -> None:
    """The published schema still carries everything the integration reads."""
    try:
        descriptor = check_schema.fetch_descriptor()
    except subprocess.CalledProcessError:
        pytest.skip("could not reach the schema registry")

    assert check_schema.check(descriptor) == []
