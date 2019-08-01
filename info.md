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
