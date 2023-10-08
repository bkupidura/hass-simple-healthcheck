from __future__ import annotations

import asyncio
import logging
import voluptuous as vol
from typing import TypedDict, cast

import homeassistant.core as ha
import homeassistant.helpers.config_validation as cv
from homeassistant.components import recorder
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import CoreState
from homeassistant.util import dt as dt_util


DOMAIN = "simple_healthcheck"

HEALTHCHECK_ENDPOINT = "/healthz"

EVENT_NAME = f"{DOMAIN}_event"
ENTITY_NAME = f"{DOMAIN}.last_seen"

_LOGGER: Final = logging.getLogger(__name__)

CONF_AUTH_REQUIRED = "auth_required"
CONF_THRESHOLD = "threshold"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_AUTH_REQUIRED, default=True): cv.boolean,
                vol.Optional(CONF_THRESHOLD, default=60): cv.positive_int
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

class ConfData(TypedDict, total=False):

    auth_required: bool
    threshold: int

async def async_setup(hass, config):
    conf: ConfData | None = config.get(DOMAIN)
    if conf is None:
        conf = cast(ConfData, CONFIG_SCHEMA({}))

    auth_required = conf.get(CONF_AUTH_REQUIRED)
    threshold = conf.get(CONF_THRESHOLD)

    hass.data[DOMAIN] = {
        'auth_required': auth_required,
        'threshold': threshold,
    }

    healthcheck_view = HealthCheckView(auth_required)
    hass.http.register_view(healthcheck_view)

    async def handle_healthcheck_event(event):
        now = dt_util.utcnow().timestamp()
        hass.states.async_set(ENTITY_NAME, int(now))

    hass.bus.async_listen(EVENT_NAME, handle_healthcheck_event)

    return True


class HealthCheckView(HomeAssistantView):
    url = HEALTHCHECK_ENDPOINT
    name = DOMAIN
    requires_auth = True

    def __init__(self, requires_auth):
        self.requires_auth = requires_auth

    @ha.callback
    async def get(self, request):
        hass = request.app["hass"]
        last_seen = None

        if hass.state != CoreState.running:
            _LOGGER.info(f"HomeAssistant state is not running ({hass.state}), reporting as healthy")
            return self.json({"healthy": True})

        use_entity_state_from_db = recorder.is_entity_recorded(hass, ENTITY_NAME)
        if use_entity_state_from_db is True:
            _LOGGER.debug(f"Trying to fetch {ENTITY_NAME} from database")

            entity_history = await recorder.get_instance(hass).async_add_executor_job(
                recorder.history.get_last_state_changes,
                hass,
                1,
                ENTITY_NAME
            )

            if entity_history.get(ENTITY_NAME) is not None and len(entity_history.get(ENTITY_NAME)) > 0:
                last_seen = entity_history[ENTITY_NAME][-1]
            else:
                _LOGGER.warning(f"Unable to fetch {ENTITY_NAME} from database")
        else:
            _LOGGER.debug(f"Trying to fetch {ENTITY_NAME} from hass.states")
            last_seen = request.app["hass"].states.get(ENTITY_NAME)

        now = dt_util.utcnow().timestamp()

        if last_seen is not None:
            last_keepalive_seconds_ago = int(now - int(last_seen.state))
            if last_keepalive_seconds_ago < hass.data[DOMAIN]['threshold']:
                _LOGGER.debug(f"HomeAssistant is healthy, last keepalive observed {last_keepalive_seconds_ago} seconds ago")
                return self.json({"healthy": True})
            else:
                _LOGGER.error(f"HomeAssistant is unhealthy, last keepalive observed {last_keepalive_seconds_ago} seconds ago")
        else:
            _LOGGER.error(f"HomeAssistant is unhealthy, unknown keepalive last seen")

        return self.json({"healthy": False}, status_code=500)
