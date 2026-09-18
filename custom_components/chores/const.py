"""Constants for the Chores integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Final

DOMAIN: Final = "chores"
LOGGER: Final = logging.getLogger(__package__)

PLATFORMS: Final = ["todo", "sensor", "button", "calendar"]

CONF_BASE_URL: Final = "base_url"
CONF_FAMILY_ID: Final = "family_id"
CONF_SCAN_INTERVAL: Final = "scan_interval"
# Purely a display choice for the money sensors — the API carries no
# currency (Money is minor units only; there's one currency per deployment
# and it isn't on the wire, mirroring how the web app's own currency symbol
# is a client-side-only preference that never reaches the server). Empty
# means "no currency configured": sensors report a plain number.
CONF_CURRENCY: Final = "currency"

DEFAULT_BASE_URL: Final = "https://chores.apphub.casa"
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=5)
# ListMonthlyEarnings is one RPC per child rather than one per family, for
# data (completed earnings by calendar month) that changes at most daily —
# see ChoresMonthlyEarningsCoordinator.
DEFAULT_MONTHLY_EARNINGS_INTERVAL: Final = timedelta(hours=1)

# proto3 JSON renders enums as their names.
ROLE_PARENT: Final = "USER_ROLE_PARENT"
ROLE_CHILD: Final = "USER_ROLE_CHILD"
CLASSIFICATION_MANDATORY: Final = "TASK_CLASSIFICATION_MANDATORY"
CLASSIFICATION_OPTIONAL: Final = "TASK_CLASSIFICATION_OPTIONAL"

# Events
EVENT_TASK_COMPLETED: Final = "chores_task_completed"
