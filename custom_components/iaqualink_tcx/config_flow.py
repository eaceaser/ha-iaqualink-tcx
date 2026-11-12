"""Credentials, TCX selection and same-controller reauthentication."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from iaqualink.exception import AqualinkServiceUnauthorizedException

from .client import TcxClient, discover
from .const import CONF_SERIAL, DOMAIN

SCHEMA = vol.Schema({vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str})


class TcxConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._credentials = {}
        self._controllers = {}

    async def _authenticate(self, user_input):
        client = TcxClient(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
        try:
            systems = await discover(client)
            self._controllers = {serial: system.name for serial, system in systems.items()}
            self._credentials = dict(user_input)
        finally:
            await client.close()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                await self._authenticate(user_input)
            except AqualinkServiceUnauthorizedException:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                if not self._controllers:
                    return self.async_abort(reason="no_tcx")
                if len(self._controllers) == 1:
                    return await self.async_step_controller(
                        {CONF_SERIAL: next(iter(self._controllers))}
                    )
                return await self.async_step_controller()
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_controller(self, user_input=None):
        if user_input is not None:
            serial = user_input[CONF_SERIAL]
            if serial not in self._controllers:
                return self.async_abort(reason="no_tcx")
            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._controllers[serial],
                data={
                    **self._credentials,
                    CONF_SERIAL: serial,
                },
            )
        return self.async_show_form(
            step_id="controller",
            data_schema=vol.Schema({vol.Required(CONF_SERIAL): vol.In(self._controllers)}),
        )

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                await self._authenticate(user_input)
            except AqualinkServiceUnauthorizedException:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                entry = self._get_reauth_entry()
                if entry.data[CONF_SERIAL] not in self._controllers:
                    errors["base"] = "controller_missing"
                else:
                    return self.async_update_reload_and_abort(entry, data_updates=self._credentials)
        return self.async_show_form(step_id="reauth_confirm", data_schema=SCHEMA, errors=errors)
