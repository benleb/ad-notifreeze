"""Notifreeze notifies about windows which should be closed.

    @benleb / https://github.com/benleb/appdaemon-healthcheck

notifreeze:
  module: notifreeze
  class: Notifreeze
  notify_service: notify.me
  outdoor_temperature: sensor.temperature_garden
"""
import re
from datetime import datetime as dt
from typing import Any, Dict, Sequence, Union
import appdaemon.plugins.hass.hassapi as hass

import adutils

APP_NAME = "NotiFreeze"
APP_ICON = "❄️ "

# state set by home assistant if entity exists but no state
STATE_UNKNOWN = "unknown"


class NotiFreeze(hass.Hass):  # type: ignore
    """Notifies about windows which should be closed."""

    SECONDS_PER_MIN: int = 60

    def initialize(self) -> None:
        """Set up state listener."""
        self.app_config: Dict[str, Union[int, float, str]] = dict()
        self.app_config["notify_service"] = str(self.args.get("notify_service"))
        self.sensor_outdoor = str(self.args.get("outdoor_temperature"))
        # time until notifications are triggered
        self.app_config["max_difference"] = float(self.args.get("max_difference", 5))
        # times/durations are given in minutes
        self.app_config["initial_delay"] = int(self.args.get("initial_delay", 5))
        self.app_config["reminder_delay"] = int(self.args.get("reminder_delay", 3))

        if self.app_config["notify_service"] and self.entity_exists(
            self.sensor_outdoor
        ):

            self.sensors: Dict[str, str] = dict()
            self.handles: Dict[str, str] = dict()

            for entity in self.get_state("binary_sensor"):
                prefix = "binary_sensor.door_window_sensor_"
                match = re.match(fr"{prefix}([a-zA-Z0-9]+)_?(\w+)?", entity)
                room = match.group(1) if match else None

                if room and self.entity_exists(f"sensor.temperature_{room}"):
                    self.sensors[entity] = f"sensor.temperature_{room}"
                    self.listen_state(self.handler, entity=entity)

            adutils.show_info(
                self.log, APP_NAME, self.app_config, self.sensors, icon=APP_ICON, appdaemon_version=self.get_ad_version()
            )

    def handler(self, entity: str, attr: Any, old: str, new: str, kwargs: Dict[str, Any]) -> None:
        """Handle state changes."""
        try:
            indoor, outdoor, difference = self.get_temperatures(entity)
        except (ValueError, TypeError) as error:
            self.error(f"No valid temperature values from sensor {entity}: {error}")
            return

        if (
            old == "off"
            and new == "on"
            and difference > float(self.app_config["max_difference"])
        ):

            # door/window opened, schedule reminder/notification
            self.handles[entity] = self.run_in(
                self.notification,
                self.app_config["initial_delay"] * self.SECONDS_PER_MIN,
                entity_id=entity,
            )

            self.log(
                f"{APP_ICON} reminder: ({self.app_config['initial_delay']}min): "
                f"{self.strip_sensor(entity)} | diff: {difference:.1f}°C",
                ascii_encode=False,
            )

        elif old == "on" and new == "off" and entity in self.handles:
            # door/window closed, stopping scheduled timer
            self.kill_timer(entity)

    def notification(self, kwargs: Dict[str, Any]) -> None:
        """Send notification."""
        entity: str = kwargs["entity_id"]
        counter: int = int(kwargs.get("counter", 1))

        try:
            indoor, outdoor, difference = self.get_temperatures(entity)
        except (ValueError, TypeError) as error:
            self.log(f"No valid temperature values to calculate difference: {error}")
            return

        # check if all required conditions still met, then processing with notification
        if (
            difference > float(self.app_config["max_difference"])
            and self.get_state(entity) == "on"
            and entity != "binary_sensor.door_window_sensor_basement_window"
        ):

            # exact state-change time but not relative/readable time
            last_changed = dt.fromisoformat(
                self.get_state(entity, attribute="last_changed")
            )

            # calculate timedelta
            opened_ago = dt.now().astimezone() - last_changed.astimezone()

            # append suitable unit
            if opened_ago.seconds >= 60:
                open_since = f"{int(opened_ago.seconds / 60)}min"
            else:
                open_since = f"{int(opened_ago.seconds)}sec"

            # build notification/log message
            message = (
                f"{self.friendly_name(entity)} seit {open_since} offen!\n"
                f"{self.friendly_name(self.sensors[entity])}: {indoor:.1f}°C | "
                f"Aussen: {outdoor:.1f}°C"
                # f"\n{counter} {last_changed}"
            )

            # send notification
            self.call_service(
                str(self.app_config["notify_service"]).replace(".", "/"),
                message=message,
            )

            # schedule next reminder
            self.handles[entity] = self.run_in(
                self.notification,
                self.app_config["reminder_delay"] * self.SECONDS_PER_MIN,
                entity_id=entity,
                counter=counter + 1,
            )

            self.log(
                f"{APP_ICON} notification sent to {self.app_config['notify_service']}: "
                f"{message}",
                ascii_encode=False,
                level="DEBUG",
            )

        elif entity in self.handles:
            # temperature difference below/above allowed threshold
            self.kill_timer(entity)

    def kill_timer(self, entity: str) -> None:
        """Cancel scheduled task/timers."""
        self.cancel_timer(self.handles[entity])
        self.log(
            f"{APP_ICON} reminder deleted: {self.strip_sensor(entity)}",
            ascii_encode=False,
        )

    def get_temperatures(self, entity: str) -> Sequence[float]:
        """Get temperature indoor, outdoor and the abs. difference of both."""
        indoor = float(self.get_state(self.sensors[entity], default=STATE_UNKNOWN))
        outdoor = float(self.get_state(self.sensor_outdoor, default=STATE_UNKNOWN))
        return (indoor, outdoor, abs(indoor - outdoor))
        # indoor_state = self.get_state(self.sensors[entity], default=STATE_UNKNOWN)
        # outdoor_state = self.get_state(self.sensor_outdoor, default=STATE_UNKNOWN)
        # if STATE_UNKNOWN not in (indoor_state, outdoor_state):
        #     indoor_temperature = float(indoor_state)
        #     outdoor_temperature = float(outdoor_state)
        #     absolute_difference = abs(indoor_temperature - outdoor_temperature)
        #     return (indoor_temperature, outdoor_temperature, absolute_difference)
        # else:
        #     raise ValueError(
        #         f"Unknown state! indoor: {indoor_state}, outdoor: {outdoor_state}"
        #     )

    def strip_sensor(self, sensor: str) -> str:
        return str(self.split_entity(sensor)[1].replace("door_window_sensor_", ""))
