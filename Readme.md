# HomeAssistant Simple Healthcheck component

Currently HomeAssistant is not exposing healthcheck endpoint which can be used by K8s or docker.

This component tries to change that. It should be used only be people who really needs it, and understand how it works.

**This component will not ensure that yours HomeAssistant installation is really healthy.**

Initial discussion about HealthCheck endpoint was started [here](https://github.com/home-assistant/architecture/discussions/650).

Component was created for my K8s HomeAssistant deployment, but any comments or contribution is welcome!

## How it works

* Users need to create `simple_healthcheck_keepalive` automation
* Component creates new HTTP endpoint `/healthz`
* Component will subscribe to `simple_healthcheck_event`
* When event will be received entity `simple_healthcheck.last_seen` will be updated
* When `simple_healthcheck.last_seen` will not be updated for 60 seconds (by default), `/healthz` endpoint will return unhealthy state

### Fetching entity `simple_healthcheck.last_seen` state

Component can fetch last `simple_healthcheck.last_seen` state with two methods:

1. Fetch last state from `recorder` database (default behavior)
2. Fetch last state from `hass.states` directly

Fetching data from recorder database is prefered, as healthcheck will also confirm that `recorder` is working properly (in some aspect). Second method will be only used when `simple_healthcheck.last_seen` entity is excluded from recorder.

## Why `simple`?

HomeAssistant is complicated piece of software, containing multiple components/integrations.
This component checks only a few aspects of HomeAssistant health.

**WARNING: It is possible that HomeAssistant will not be able to perform some critical actions and still be reported as healthy.**

Currently component will confirm that:
* HomeAssistant HTTP server is working
* `simple_healthcheck_keepalive` automation is working
* HomeAssistant message bus is able to deliver `simple_healthcheck_event`
* HomeAssistant `recorder` is able to fetch `simple_healthcheck.last_seen` state

## Installation

Copy `simple_healthcheck` directory into `custom_integrations/` directory.

## Configuration

```
simple_healthcheck:
automation:
  - alias: 'simple_healthcheck_keepalive'
    trigger:
      - platform: time_pattern
        seconds: '/10'
    action:
      - event: simple_healthcheck_event
```

### Possible options

```
simple_healthcheck:
  auth_required: true
  threshold: 45
```

* auth_required - enable or disable authentication for `/healthz` endpoint (default: true)
* threshold - number of seconds to wait before marking as unhealthy (default: 60)

## HTTP endpoint `/healthz`

This component will create new HomeAssistant endpoint `/healthz`.

By default this endpoint requires HomeAssistant authentication with [long term token](https://developers.home-assistant.io/docs/auth_api/#long-lived-access-token).

### Healthy response
```
< HTTP/1.1 200 OK
< Content-Type: application/json
< Content-Length: 17
< Date: Tue, 02 Nov 2021 19:30:32 GMT
< Server: Python/3.9 aiohttp/3.7.4.post0
<
{"healthy": true}
```

### Unhealthy response
```
< HTTP/1.1 500 Internal Server Error
< Content-Type: application/json
< Content-Length: 18
< Date: Tue, 02 Nov 2021 19:30:31 GMT
< Server: Python/3.9 aiohttp/3.7.4.post0
<
{"healthy": false}
```
