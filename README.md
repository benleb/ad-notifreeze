# notifreeze

[![python_badge](https://img.shields.io/static/v1?label=python&message=3.8%20|%203.9&color=blue&style=flat)](https://www.python.org) [![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)

## Hello ✌️ **v0.5.0** will contain breaking changes!
## · changed configuration options
## · use `rooms` like the famous [AutoMoLi](https://github.com/benleb/ad-automoli)

- - -

*[AppDaemon](https://github.com/appdaemon/appdaemon) app which reminds to close windows if temperature difference between inside/outside exceeds a specified threshold.*  
This works for every 'room' separately e.g. an open window in the bathroom checks outside temperate against the bathroom temperature sensor. Useful in winter to remind you to close the bathroom windows after airing, but also in the summer when you do not want that hot outside air inside.

In NotiFreeze you configure just **one App for all your rooms** in contrast to separate apps/configurations per room like in [AutoMoLi](https://github.com/benleb/ad-automoli).

## Installation

Use [HACS](https://github.com/hacs/integration) or [download](https://github.com/benleb/ad-notifreeze/releases) the `notifreeze` directory from inside the `apps` directory here to your local `apps` directory, then add the configuration to enable the `notifreeze` module.

## Auto-Discovery of Entities/Sensors

If sensors entities have an ***entity id*** matching:

* ***binary_sensor.door_window_`*`***
* ***sensor.temperature_`*`***

**and** a ***friendly name*** containing the **`room`**:

NotiFreeze will detect them automatically. (Manually configured entities will take precedence.)

## Configuration Example

```yaml
notifreeze:
  module: notifreeze
  class: Notifreeze
  rooms:
    - livingroom
    - esszimmer
    - office
    - keller
  notify_service: notify.me
  outdoor: sensor.temperature_garden
  max_difference: 4.2
  delays:
    initial: 2
    reminder: 8
```

### Available Options

key | optional | type | default | description
-- | -- | -- | -- | --
`module` | False | string | notifreeze | The module name of the app.
`class` | False | string | Notifreeze | The name of the Class.
`rooms` | False | list | | Name of the *rooms* NotiFreeze will monitor. Users of the famous [AutoMoLi](https://github.com/benleb/ad-automoli) may already by familiar with the *rooms* concept.
`notify_service` | False | string | | Home Assistant notification service
`outdoor` | False | string | | Sensor for outside temperature
`max_difference` | True | float | 5 | Maximum tolerated tmperature difference
`delays` | True | list | [**see below**](#delays) | Delays NotiFreeze will use.

## delays

key | optional | type | default | description
-- | -- | -- | -- | --
.`initial` | True | integer | 5 | Time in minutes before sending first notification
`reminder` | True | integer | 3 | Time in minutes until next notification is send
