"""Constants for the Chores integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Final

DOMAIN: Final = "chores"
LOGGER: Final = logging.getLogger(__package__)

PLATFORMS: Final = ["todo"]

CONF_BASE_URL: Final = "base_url"
CONF_FAMILY_ID: Final = "family_id"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_BASE_URL: Final = "https://chores.apphub.casa"
DEFAULT_SCAN_INTERVAL: Final = timedelta(minutes=5)

# proto3 JSON renders enums as their names.
ROLE_CHILD: Final = "USER_ROLE_CHILD"
CLASSIFICATION_MANDATORY: Final = "TASK_CLASSIFICATION_MANDATORY"
CLASSIFICATION_OPTIONAL: Final = "TASK_CLASSIFICATION_OPTIONAL"

# Events
EVENT_TASK_COMPLETED: Final = "chores_task_completed"
