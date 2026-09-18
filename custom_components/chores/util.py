"""Small helpers shared by more than one entity platform."""

from __future__ import annotations

from typing import Any

# Separator for the composite uid `TaskOccurrence` is keyed by when it has no
# id of its own (nothing has been recorded about it yet). Shared by todo.py
# and calendar.py, which both need to turn an occurrence back into the
# (task_id, child_id, due_date) tuple CompleteTask/UncompleteTask take.
UID_SEPARATOR = "|"


def occurrence_uid(occurrence: dict[str, Any]) -> str:
    """Build the stable item id for a task occurrence."""
    return UID_SEPARATOR.join(
        (
            occurrence.get("taskId", ""),
            occurrence.get("childId", ""),
            occurrence.get("dueDate", ""),
        )
    )


def money_cents(money: dict[str, Any] | None) -> int:
    """Read a Money message's cents, defaulting a zero/missing value to 0.

    proto3 JSON omits zero-valued fields entirely, so a zero amount can
    arrive as `{}` or with the field absent altogether, and `int64` arrives
    as a JSON string rather than a number.
    """
    if not money:
        return 0
    return int(money.get("cents") or 0)
