"""Config flow for the Chores integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_TOKEN
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .api import ChoresApiError, ChoresAuthError, ChoresClient
from .const import (
    CONF_BASE_URL,
    CONF_FAMILY_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
        vol.Required(CONF_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)

STEP_REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


async def _async_memberships(hass, base_url: str, token: str) -> list[dict[str, Any]]:
    """Validate the token and return the families it is bound to."""
    client = ChoresClient(async_get_clientsession(hass), base_url, token)
    body = await client.get_my_membership()
    if not body.get("bound"):
        raise ChoresAuthError("This token is not bound to a family")
    return body.get("memberships", [])


class ChoresConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Chores."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._data: dict[str, Any] = {}
        self._memberships: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Take the server URL and a personal access token."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                memberships = await _async_memberships(
                    self.hass, user_input[CONF_BASE_URL], user_input[CONF_TOKEN]
                )
            except ChoresAuthError:
                errors["base"] = "invalid_auth"
            except ChoresApiError:
                errors["base"] = "cannot_connect"
            else:
                if not memberships:
                    return self.async_abort(reason="no_family")
                self._data = dict(user_input)
                self._memberships = memberships
                if len(memberships) == 1:
                    return await self._async_create(memberships[0])
                return await self.async_step_family()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_family(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick which family to set up, when the token is bound to several."""
        if user_input is not None:
            membership = next(
                m
                for m in self._memberships
                if m["family"]["id"] == user_input[CONF_FAMILY_ID]
            )
            return await self._async_create(membership)

        options = [
            SelectOptionDict(
                value=membership["family"]["id"],
                label=membership["family"].get("name") or membership["family"]["id"],
            )
            for membership in self._memberships
        ]
        return self.async_show_form(
            step_id="family",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FAMILY_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=options, mode=SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
        )

    async def _async_create(self, membership: dict[str, Any]) -> ConfigFlowResult:
        """Create the entry for one family."""
        family = membership["family"]
        await self.async_set_unique_id(family["id"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=family.get("name") or "Chores",
            data={**self._data, CONF_FAMILY_ID: family["id"]},
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle a rotated or revoked token."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Take a fresh token for an existing entry."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            try:
                await _async_memberships(
                    self.hass, entry.data[CONF_BASE_URL], user_input[CONF_TOKEN]
                )
            except ChoresAuthError:
                errors["base"] = "invalid_auth"
            except ChoresApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: user_input[CONF_TOKEN]}
                )

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_REAUTH_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ChoresOptionsFlow:
        """Get the options flow."""
        return ChoresOptionsFlow()


class ChoresOptionsFlow(OptionsFlow):
    """Handle Chores options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set the poll interval."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, int(DEFAULT_SCAN_INTERVAL.total_seconds())
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=60, max=3600)
                    )
                }
            ),
        )
