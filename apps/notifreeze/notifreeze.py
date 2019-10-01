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
from typing import Any, Dict, Sequence

import adutils
import hassapi as hass

APP_NAME = "NotiFreeze"
APP_ICON = "❄️ "
APP_VERSION = "0.4.2"

# state set by home assistant if entity exists but no state
STATE_UNKNOWN = "unknown"


class NotiFreeze(hass.Hass):  # type: ignore
    """Notifies about windows which should be closed."""

    SECONDS_PER_MIN: int = 60

    def initialize(self) -> None:
        """Set up state listener."""
        self.cfg: Dict[str, Any] = dict()
        self.cfg["notify_service"] = str(self.args.get("notify_service"))
        self.sensor_outdoor = str(self.args.get("outdoor_temperature"))
        # time until notifications are triggered
        self.cfg["max_difference"] = float(self.args.get("max_difference", 5))
        # times/durations are given in minutes
        self.cfg["initial_delay"] = int(self.args.get("initial_delay", 5))
        self.cfg["reminder_delay"] = int(self.args.get("reminder_delay", 3))

        if self.cfg["notify_service"] and self.entity_exists(self.sensor_outdoor):

            self.sensors: Dict[str, str] = dict()
            self.handles: Dict[str, str] = dict()

            for entity in self.get_state("binary_sensor"):
                prefix = "binary_sensor.door_window_sensor_"
                match = re.match(fr"{prefix}([a-zA-Z0-9]+)_?(\w+)?", entity)
                room = match.group(1) if match else None

                if room and self.entity_exists(f"sensor.temperature_{room}"):
                    self.sensors[entity] = f"sensor.temperature_{room}"
                    self.listen_state(self.handler, entity=entity)

            # set units
            self.cfg.setdefault(
                "_units",
                dict(max_difference="°C", initial_delay="min", reminder_delay="min"),
            )
            self.cfg.setdefault("_prefixes", dict(max_difference="±"))

            # init adutils
            self.adu = adutils.ADutils(
                APP_NAME, self.cfg, icon=APP_ICON, ad=self, show_config=True
            )

    def handler(
        self, entity: str, attr: Any, old: str, new: str, kwargs: Dict[str, Any]
    ) -> None:
        """Handle state changes."""
        try:
            indoor, outdoor, difference = self.get_temperatures(entity)
        except (ValueError, TypeError) as error:
            self.adu.log(
                f"No valid temperature values from sensor {entity}: {error}",
                icon=APP_ICON,
                level="ERROR",
            )
            return

        if (
            old == "off"
            and new == "on"
            and abs(difference) > float(self.cfg["max_difference"])
        ):

            # door/window opened, schedule reminder/notification
            self.handles[entity] = self.run_in(
                self.notification,
                self.cfg["initial_delay"] * self.SECONDS_PER_MIN,
                entity_id=entity,
            )

            self.adu.log(
                f"\033[1m{self.friendly_name(entity)}\033[0m opened, "
                f"\033[1m{difference:+.1f}°C\033[0m → "
                f"reminder in \033[1m{self.cfg['initial_delay']}min\033[0m",
                icon=APP_ICON,
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
            self.adu.log(
                f"No valid temperature values to calculate difference: {error}",
                icon=APP_ICON,
                level="ERROR",
            )
            return

        # check if all required conditions still met, then processing with notification
        if (
            abs(difference) > float(self.cfg["max_difference"])
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
                f"\033[1m{difference:+.1f}°C\033[0m → "
                f"{self.friendly_name(self.sensors[entity])}: {indoor:.1f}°C"
            )

            # send notification
            self.call_service(
                str(self.cfg["notify_service"]).replace(".", "/"),
                message=re.sub(r"\033\[\dm", "", message),
            )

            # schedule next reminder
            self.handles[entity] = self.run_in(
                self.notification,
                self.cfg["reminder_delay"] * self.SECONDS_PER_MIN,
                entity_id=entity,
                counter=counter + 1,
            )

            # debug
            self.adu.log(
                f"notification sent to {self.cfg['notify_service']}: " f"{message}",
                icon=APP_ICON,
                level="DEBUG",
            )

        elif entity in self.handles:
            # temperature difference below/above allowed threshold
            self.kill_timer(entity)

    def kill_timer(self, entity: str) -> None:
        """Cancel scheduled task/timers."""
        if self.handles[entity]:
            self.cancel_timer(self.handles[entity])
            self.adu.log(
                f"\033[1m{self.friendly_name(entity)}\033[0m closed → timer stopped",
                icon=APP_ICON,
            )

    def get_temperatures(self, entity: str) -> Sequence[float]:
        """Get temperature indoor, outdoor and the abs. difference of both."""
        indoor = float(self.get_state(self.sensors[entity], default=STATE_UNKNOWN))
        outdoor = float(self.get_state(self.sensor_outdoor, default=STATE_UNKNOWN))
        return (indoor, outdoor, outdoor - indoor)
