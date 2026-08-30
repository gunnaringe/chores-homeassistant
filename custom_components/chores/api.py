"""Client for the Chores Connect RPC API.

Connect unary calls are ordinary HTTP POSTs with JSON bodies, so this needs no
protobuf or grpc dependency:

    POST {base_url}/chores.v1.ChoresService/ListTaskOccurrences
    Authorization: Bearer chorespat_...
    Content-Type: application/json
    Connect-Protocol-Version: 1

Responses are proto3 JSON, which has three properties this module has to
respect: field names are camelCase, enums arrive as their names, and
zero-valued fields are omitted entirely. Requests are lenient — a server using
protojson accepts both `family_id` and `familyId` — so only decoding has to
match exactly.
"""

from __future__ import annotations

from typing import Any, Final

import aiohttp

SERVICE: Final = "chores.v1.ChoresService"

# Connect error codes that mean the token is bad rather than the request.
AUTH_CODES: Final = frozenset({"unauthenticated", "permission_denied"})


class ChoresError(Exception):
    """Base error for the Chores API."""


class ChoresApiError(ChoresError):
    """The API could not be reached, or returned an unexpected error."""


class ChoresAuthError(ChoresError):
    """The token was rejected."""


class ChoresClient:
    """Thin async client over the handful of RPCs this integration uses."""

    def __init__(
        self, session: aiohttp.ClientSession, base_url: str, token: str
    ) -> None:
        """Initialise the client."""
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._token = token

    async def _rpc(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Make one unary Connect call and return the decoded response."""
        url = f"{self._base_url}/{SERVICE}/{method}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Connect-Protocol-Version": "1",
        }

        try:
            response = await self._session.post(url, json=payload, headers=headers)
            # Connect errors are JSON too, but a proxy in the way may not be.
            body = await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise ChoresApiError(f"Error calling {method}: {err}") from err
        except ValueError as err:
            raise ChoresApiError(f"Malformed response from {method}") from err

        if not isinstance(body, dict):
            body = {}

        if response.status != 200:
            code = body.get("code", "unknown")
            message = body.get("message", f"HTTP {response.status}")
            if code in AUTH_CODES:
                raise ChoresAuthError(message)
            raise ChoresApiError(f"{method} failed ({code}): {message}")

        return body

    async def get_my_membership(self) -> dict[str, Any]:
        """Resolve the token's login identity to the families it is bound to."""
        return await self._rpc("GetMyMembership", {})

    async def list_users(self, family_id: str) -> list[dict[str, Any]]:
        """List every member of a family."""
        body = await self._rpc("ListUsers", {"familyId": family_id})
        return body.get("users", [])

    async def list_task_occurrences(
        self, family_id: str, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        """List task occurrences due between two dates, inclusive."""
        body = await self._rpc(
            "ListTaskOccurrences",
            {
                "familyId": family_id,
                "startDate": start_date,
                "endDate": end_date,
            },
        )
        return body.get("occurrences", [])

    async def complete_task(self, task_id: str, child_id: str, due_date: str) -> None:
        """Mark one occurrence complete."""
        await self._rpc(
            "CompleteTask",
            {"taskId": task_id, "childId": child_id, "dueDate": due_date},
        )

    async def uncomplete_task(self, task_id: str, child_id: str, due_date: str) -> None:
        """Mark one occurrence not complete."""
        await self._rpc(
            "UncompleteTask",
            {"taskId": task_id, "childId": child_id, "dueDate": due_date},
        )
