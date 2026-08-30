"""Check the live Chores schema still carries the fields this integration reads.

There is no vendored copy of the proto. `buf build -o desc.json` emits a
FileDescriptorSet as JSON, which the standard library reads without any
protobuf dependency, and which carries the authoritative `jsonName` for every
field — exactly what the hand-written decoder in api.py has to match.

This is deliberately narrower than diffing a vendored file: an unrelated
upstream change should not fail the build, but a field we actually read being
renamed or removed must.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

MODULE = "buf.build/apphub/chores"

# What api.py, coordinator.py and todo.py actually read off the wire.
REQUIRED_FIELDS: dict[str, set[str]] = {
    "User": {"id", "name", "role"},
    "Family": {"id", "name"},
    "Membership": {"user", "family"},
    "GetMyMembershipResponse": {"bound", "memberships"},
    "ListUsersResponse": {"users"},
    "ListTaskOccurrencesResponse": {"occurrences"},
    "TaskOccurrence": {
        "taskId",
        "childId",
        "dueDate",
        "title",
        "description",
        "classification",
        "completedAt",
    },
    "ListTaskOccurrencesRequest": {"familyId", "startDate", "endDate"},
    "CompleteTaskRequest": {"taskId", "childId", "dueDate"},
    "UncompleteTaskRequest": {"taskId", "childId", "dueDate"},
}

REQUIRED_METHODS = {
    "GetMyMembership",
    "ListUsers",
    "ListTaskOccurrences",
    "CompleteTask",
    "UncompleteTask",
}

# proto3 JSON renders enums as their names, so the names are load-bearing too.
REQUIRED_ENUM_VALUES: dict[str, set[str]] = {
    "UserRole": {"USER_ROLE_CHILD"},
    "TaskClassification": {"TASK_CLASSIFICATION_OPTIONAL"},
}


def fetch_descriptor() -> dict:
    """Build the live schema into a JSON FileDescriptorSet."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "desc.json"
        subprocess.run(
            ["buf", "build", MODULE, "-o", str(out)],
            check=True,
            capture_output=True,
        )
        return json.loads(out.read_text())


def check(descriptor: dict) -> list[str]:
    """Return a list of problems, empty when the schema still fits."""
    problems: list[str] = []

    files = [f for f in descriptor["file"] if f.get("package") == "chores.v1"]
    messages = {
        message["name"]: {field["jsonName"] for field in message.get("field", [])}
        for file in files
        for message in file.get("messageType", [])
    }
    enums = {
        enum["name"]: {value["name"] for value in enum.get("value", [])}
        for file in files
        for enum in file.get("enumType", [])
    }
    methods = {
        method["name"]
        for file in files
        for service in file.get("service", [])
        for method in service.get("method", [])
    }

    for name, required in REQUIRED_FIELDS.items():
        if name not in messages:
            problems.append(f"message {name} is gone")
            continue
        if missing := required - messages[name]:
            problems.append(f"{name} is missing field(s): {', '.join(sorted(missing))}")

    for name, required in REQUIRED_ENUM_VALUES.items():
        if name not in enums:
            problems.append(f"enum {name} is gone")
            continue
        if missing := required - enums[name]:
            problems.append(f"{name} is missing value(s): {', '.join(sorted(missing))}")

    if missing := REQUIRED_METHODS - methods:
        problems.append(
            f"ChoresService is missing RPC(s): {', '.join(sorted(missing))}"
        )

    return problems


def main() -> int:
    """Run the check, skipping when buf or the network is unavailable."""
    if shutil.which("buf") is None:
        print("buf not installed — skipping schema check")  # noqa: T201
        return 0

    try:
        descriptor = fetch_descriptor()
    except subprocess.CalledProcessError as err:
        print(  # noqa: T201
            f"could not reach {MODULE} — skipping schema check\n"
            f"{err.stderr.decode(errors='replace').strip()}"
        )
        return 0

    if problems := check(descriptor):
        for problem in problems:
            print(f"error: {problem}")  # noqa: T201
        return 1

    print(f"schema ok — {MODULE} still has every field we read")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
