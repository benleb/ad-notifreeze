# notifreeze

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)

**NEEDS THE APPDAEMON BETA OR DEV BRANCH! Current stable (v3.0.5) will not work!**

*[AppDaemon](https://github.com/home-assistant/appdaemon) app which reminds to close windows if temperature difference between inside/outside exceeds a specified threshold.*  
This works for every 'room' separately e.g. an open window in the bathroom checks outside temperate against the bathroom temperature sensor. Useful in winter to remind you to close the bathroom windows after airing, but also in the summer when you do not want that hot outside air inside.

## Installation

Use [HACS](https://github.com/custom-components/hacs) or [download](https://github.com/benleb/ad-notifreeze/releases) the `notifreeze` directory from inside the `apps` directory here to your local `apps` directory, then add the configuration to enable the `notifreeze` module.

## Requirements

* expects *binary_sensor.door_window_sensor_**`room`*** or *binary_sensor.door_window_sensor_**`room`**_something* door/window sensors and matching temperature sensors with entity ids in the form *sensor.temperature_**`room`***. **`room`** is the *match-key* to decide which sensors belong together.

## App configuration

```yaml
notifreeze:
  module: notifreeze
  class: Notifreeze
  notify_service: notify.me
  outdoor_temperature: sensor.temperature_garden
```

key | optional | type | default | description
-- | -- | -- | -- | --
`module` | False | string | notifreeze | The module name of the app.
`class` | False | string | Notifreeze | The name of the Class.
`notify_service` | False | string | | Home Assistant notification service
`outdoor_temperature` | False | string | | Sensor for outside temperature
`max_difference` | True | float | 5 | Maximum tolerated tmperature difference
`initial_delay` | True | integer | 5 | Time in minutes before sending first notification
`reminder_delay` | True | integer | 3 | Time in minutes until next notification is send
