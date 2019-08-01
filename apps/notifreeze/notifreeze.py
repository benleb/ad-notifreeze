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

import appdaemon.plugins.hass.hassapi as hass

import adutils

APP_NAME = "NotiFreeze"
APP_ICON = "❄️ "


class NotiFreeze(hass.Hass):
    """Notifies about windows which should be closed."""

    SECONDS_PER_MIN: int = 60
    # used for debugging
    # SECONDS_PER_MIN: int = 10

    def initialize(self):
        """Set up state listener."""
        self.app_config = dict()
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

            self.sensors = dict()
            self.handles = dict()

            for entity in self.get_state("binary_sensor"):
                prefix = "binary_sensor.door_window_sensor_"
                match = re.match(fr"{prefix}([a-zA-Z0-9]+)_?(\w+)?", entity)
                room = match.group(1) if match else None

                if room and self.entity_exists(f"sensor.temperature_{room}"):
                    self.sensors[entity] = f"sensor.temperature_{room}"
                    self.listen_state(self.handler, entity=entity)

            adutils.show_info(
                self.log, APP_NAME, self.app_config, self.sensors, icon=APP_ICON
            )

    def handler(self, entity, attribute, old, new, kwargs):
        """Handle state changes."""
        indoor, outdoor, difference = self.get_temperatures(entity)

        if (
            old == "off"
            and new == "on"
            and difference > self.app_config["max_difference"]
        ):

            # door/window opened, schedule reminder/notification
            self.handles[entity] = self.run_in(
                self.notification,
                self.app_config["initial_delay"] * self.SECONDS_PER_MIN,
                entity_id=entity,
            )

            stripped_entity = self.split_entity(entity)[1].replace(
                "door_window_sensor_", ""
            )
            self.log(
                f"{APP_ICON} reminder: ({self.app_config['initial_delay']}min): "
                f"{stripped_entity} | diff: {difference:.1f}",
                ascii_encode=False,
            )

        elif old == "on" and new == "off" and entity in self.handles:
            # door/window closed, stopping scheduled timer
            self.kill_timer(entity)

    def notification(self, kwargs):
        """Send notification."""
        entity = kwargs.get("entity_id")
        counter = kwargs.get("counter", 1)

        indoor, outdoor, difference = self.get_temperatures(entity)

        if (
            difference > self.app_config["max_difference"]
            and self.get_state(entity) == "on"
            and entity != "binary_sensor.door_window_sensor_basement_window"
        ):
            # all required conditions still met, processing with notification

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
                self.app_config["notify_service"].replace(".", "/"), message=message
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
            # temperature difference below allowed threshold
            self.kill_timer(entity)

    def kill_timer(self, entity):
        """Cancel scheduled task/timers."""
        self.cancel_timer(self.handles[entity])
        self.log(
            f"{APP_ICON} reminder deleted: {self.split_entity(entity)[1]}",
            ascii_encode=False,
        )

    def get_temperatures(self, entity):
        """Get temperature indoor, outdoor and the abs. difference of both."""
        indoor_temperature = float(self.get_state(self.sensors[entity]))
        outdoor_temperature = float(self.get_state(self.sensor_outdoor))
        absolute_difference = abs(indoor_temperature - outdoor_temperature)
        return indoor_temperature, outdoor_temperature, absolute_difference
