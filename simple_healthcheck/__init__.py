from __future__ import annotations

import logging
import voluptuous as vol
from typing import TypedDict, cast

import homeassistant.core as ha
import homeassistant.helpers.config_validation as cv
from homeassistant.components.automation.const import DOMAIN as AUTOMATION_DOMAIN
from homeassistant.components.http import HomeAssistantView
from homeassistant.util import dt as dt_util
from homeassistant.components import recorder


DOMAIN = "simple_healthcheck"

HEALTHCHECK_EVENT = f"{DOMAIN}_event"
HEALTHCHECK_INTERVAL = 10
HEALTHCHECK_THRESHOLD = 3
HEALTHCHECK_ENDPOINT = "/healthz"

ENTITY_NAME = f"{DOMAIN}.last_seen"
AUTOMATION_NAME = f"{DOMAIN}_keepalive"

_LOGGER: Final = logging.getLogger(__name__)

CONF_AUTH_REQUIRED = "auth_required"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_AUTH_REQUIRED): cv.boolean,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

class ConfData(TypedDict, total=False):

    auth_required: bool

async def async_setup(hass, config):
    conf: ConfData | None = config.get(DOMAIN)
    if conf is None:
        conf = cast(ConfData, CONFIG_SCHEMA({}))

    auth_required = conf.get(CONF_AUTH_REQUIRED, True)

    healthcheck_view = HealthCheckView(auth_required)
    hass.http.register_view(healthcheck_view)

    append_automation(config)

    async def handle_healthcheck_event(event):
        now = dt_util.utcnow().timestamp()
        hass.states.async_set(ENTITY_NAME, int(now))

    hass.bus.async_listen(HEALTHCHECK_EVENT, handle_healthcheck_event)
    return True

def append_automation(config):
    config[AUTOMATION_DOMAIN].append({
        "alias": AUTOMATION_NAME,
        "trigger": [
            {
                "platform": "time_pattern",
                "seconds": f"/{HEALTHCHECK_INTERVAL}",
            },
        ],
        "action": [
            {
                "event": HEALTHCHECK_EVENT,
            }
        ],
    })


class HealthCheckView(HomeAssistantView):
    url = HEALTHCHECK_ENDPOINT
    name = DOMAIN
    requires_auth = True

    def __init__(self, requires_auth):
        self.requires_auth = requires_auth

    @ha.callback
    def get(self, request):
        last_seen = None

        use_entity_state_from_db = recorder.is_entity_recorded(request.app["hass"], ENTITY_NAME)
        if use_entity_state_from_db is True:
            _LOGGER.debug(f"Trying to fetch {ENTITY_NAME} from database")
            entity_history = recorder.history.get_last_state_changes(request.app["hass"], 1, ENTITY_NAME)

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
            if last_keepalive_seconds_ago < HEALTHCHECK_INTERVAL * HEALTHCHECK_THRESHOLD:
                _LOGGER.debug(f"HomeAssistant is healthy, last keepalive observed {last_keepalive_seconds_ago} seconds ago")
                return self.json({"healthy": True})
            else:
                _LOGGER.error(f"HomeAssistant is unhealthy, last keepalive observed {last_keepalive_seconds_ago} seconds ago")
        else:
            _LOGGER.error(f"HomeAssistant is unhealthy, unknown keepalive last seen")

        return self.json({"healthy": False}, status_code=500)
