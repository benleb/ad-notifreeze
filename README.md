# notifreeze

[![python_badge](https://img.shields.io/static/v1?label=python&message=3.8%20|%203.9&color=blue&style=flat)](https://www.python.org) [![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)

## Hello ✌️ **v0.5.0** will (and the **master does**) contain breaking changes!
## · changed configuration options
## · use `rooms` similar to the famous [AutoMoLi](https://github.com/benleb/ad-automoli)

- - -

*[AppDaemon](https://github.com/appdaemon/appdaemon) app which reminds to close windows if temperature difference between inside/outside exceeds a specified threshold.*  
This works for every 'room' separately e.g. an open window in the bathroom checks outside temperate against the bathroom temperature sensor. Useful in winter to remind you to close the bathroom windows after airing, but also in the summer when you do not want that hot outside air inside.

**Note:** In **NotiFreeze** you configure just **one App for all your rooms** in contrast to separate apps/configurations per room like in [AutoMoLi](https://github.com/benleb/ad-automoli).

## Installation

Use [HACS](https://github.com/hacs/integration) or [download](https://github.com/benleb/ad-notifreeze/releases) the `notifreeze` directory from inside the `apps` directory here to your local `apps` directory, then add the configuration to enable the `notifreeze` module.

## Auto-Discovery of Entities/Sensors

If sensors entities have an ***entity id*** matching:

* ***binary_sensor.door_window_`*`***
* ***sensor.temperature_`*`***

**and**

* an ***entity id*** or ***friendly name*** containing the **`room`**/**`room`** name:

**NotiFreeze** will detect them automatically. (Manually configured entities will take precedence.)

## Configuration Example

```yaml
notifreeze:
  module: notifreeze
  class: NotiFreeze
  notify_service: notify.mobile_app_ben
  outdoor: sensor.temperature_outdoor
  max_difference: 4.2
  delays:
    initial: 3
    reminder: 7
  rooms:
    - Schlafzimmer
    - Bad
    - name: Wohnzimmer
      alias: livingroom  # entity ids contain *livingroom* but not *wohnzimmer*
    - name: Keller
      door_window: binary_sensor.door_window_sensor_basement_window
      indoor:
        - sensor.temperature_basement
        - binary_sensor.door_window_sensor_basement_window
```

### Available Options

key | optional | type | default | description
-- | -- | -- | -- | --
`module` | False | string | notifreeze | The module name of the app.
`class` | False | string | Notifreeze | The name of the Class.
`notify_service` | False | string | | Home Assistant notification service
`outdoor` | False | string | | Sensor for outside temperature
`max_difference` | True | float | 5 | Maximum tolerated tmperature difference
`rooms` | False | list<string, [**room**](#room)> | | List of [**rooms**](#room) or simple *room* names NotiFreeze will monitor. Users of the famous [AutoMoLi](https://github.com/benleb/ad-automoli) may already by familiar with the *rooms* concept.
`delays` | True | [**delay**](#delays) | [**see below**](#delays) | Delays NotiFreeze will use.

## room

key | optional | type | default | description
-- | -- | -- | -- | --
`name` | True | string | | Name of the room (used for auto-discovery if no *alias* is set)
`alias` | True | integer | | Alias used for auto-discovery of sensors (if your entity IDs not contain your *room*, this *alias* can be used)
`indoor` | True | string, list<string> | | Temperature sensor Entity ID(s)
`door_window` | True | string, list<string> | | Door/Windows sensor Entity ID(s)

## delays

key | optional | type | default | description
-- | -- | -- | -- | --
`initial` | True | integer | 5 | Time in minutes before sending first notification
`reminder` | True | integer | 3 | Time in minutes until next notification is send
