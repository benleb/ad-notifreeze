"""Notifreeze notifies about windows which should be closed.

    @benleb / https://github.com/benleb/ad-notifreeze

notifreeze:
  module: notifreeze
  class: Notifreeze
  notify_service: notify.me
  outdoor_temperature: sensor.temperature_garden
"""
import re
from datetime import datetime as dt
from typing import Any, Dict, Sequence

import hassapi as hass
from adutils import ADutils, hl

APP_NAME = "NotiFreeze"
APP_ICON = "❄️ "
APP_VERSION = "0.4.4"

# state set by home assistant if entity exists but no state
STATE_UNKNOWN = "unknown"

SECONDS_PER_MIN: int = 60


class NotiFreeze(hass.Hass):  # type: ignore
    """Notifies about windows which should be closed."""

    async def initialize(self) -> None:
        """Set up state listener."""
        self.cfg: Dict[str, Any] = dict()
        self.cfg["notify_service"] = str(self.args.get("notify_service"))
        self.sensor_outdoor = str(self.args.get("outdoor_temperature"))
        # time until notifications are triggered
        self.cfg["max_difference"] = float(self.args.get("max_difference", 5))
        # times/durations are given in minutes
        self.cfg["initial_delay"] = int(self.args.get("initial_delay", 5))
        self.cfg["reminder_delay"] = int(self.args.get("reminder_delay", 3))

        if self.cfg["notify_service"] and await self.entity_exists(self.sensor_outdoor):

            self.sensors: Dict[str, str] = dict()
            self.handles: Dict[str, str] = dict()

            for entity in await self.get_state("binary_sensor"):
                prefix = "binary_sensor.door_window_sensor_"
                match = re.match(fr"{prefix}([a-zA-Z0-9]+)_?(\w+)?", entity)
                room = match.group(1) if match else None

                if room and await self.entity_exists(f"sensor.temperature_{room}"):
                    self.sensors[entity] = f"sensor.temperature_{room}"
                    await self.listen_state(self.handler, entity=entity)

            # set units
            self.cfg.setdefault(
                "_units",
                dict(max_difference="°C", initial_delay="min", reminder_delay="min"),
            )
            self.cfg.setdefault("_prefixes", dict(max_difference="±"))

            # init adutils
            self.adu = ADutils(
                APP_NAME, self.cfg, icon=APP_ICON, ad=self, show_config=True
            )

    async def handler(
        self, entity: str, attr: Any, old: str, new: str, kwargs: Dict[str, Any]
    ) -> None:
        """Handle state changes."""
        try:
            indoor, outdoor, difference = await self.get_temperatures(entity)
        except (ValueError, TypeError) as error:
            self.adu.log(
                f"No valid temperature values from sensor {entity}: {error}",
                icon=APP_ICON,
                level="ERROR",
            )
            return

        if all(
            [
                old == "off",
                new == "on",
                abs(difference) > float(self.cfg["max_difference"]),
            ]
        ):
            # door/window opened, schedule reminder/notification
            self.handles[entity] = await self.run_in(
                self.notification,
                self.cfg["initial_delay"] * SECONDS_PER_MIN,
                entity_id=entity,
            )

            self.adu.log(
                f"{hl(await self.friendly_name(entity))} opened, "
                f"{hl(f'{difference:+.1f}°C')} → "
                f"reminder in {self.cfg['initial_delay']}min\033[0m",
                icon=APP_ICON,
            )

        elif old == "on" and new == "off" and entity in self.handles:
            # door/window closed, stopping scheduled timer
            await self.kill_timer(entity)

    async def notification(self, kwargs: Dict[str, Any]) -> None:
        """Send notification."""
        entity: str = kwargs["entity_id"]
        counter: int = int(kwargs.get("counter", 1))

        try:
            indoor, outdoor, difference = await self.get_temperatures(entity)
        except (ValueError, TypeError) as error:
            self.adu.log(
                f"No valid temperature values to calculate difference: {error}",
                icon=APP_ICON,
                level="ERROR",
            )
            return

        if all(
            [
                abs(difference) > float(self.cfg["max_difference"]),
                await self.get_state(entity) == "on",
                entity != "binary_sensor.door_window_sensor_basement_window",
            ]
        ):

            # exact state-change time but not relative/readable time
            last_changed = dt.fromisoformat(
                await self.get_state(entity, attribute="last_changed")
            )

            # calculate timedelta
            opened_ago = dt.now().astimezone() - last_changed.astimezone()

            # append suitable unit
            if opened_ago.seconds >= SECONDS_PER_MIN:
                open_since = f"{int(opened_ago.seconds / SECONDS_PER_MIN)}min"
            else:
                open_since = f"{int(opened_ago.seconds)}sec"

            # build notification/log message
            message = (
                f"{await self.friendly_name(entity)} seit {open_since} offen!\n"
                f"{hl(f'{difference:+.1f}°C')} → "
                f"{await self.friendly_name(self.sensors[entity])}: {indoor:.1f}°C"
            )

            # send notification
            await self.call_service(
                str(self.cfg["notify_service"]).replace(".", "/"),
                message=re.sub(r"\033\[\dm", "", message),
            )

            # schedule next reminder
            self.handles[entity] = await self.run_in(
                self.notification,
                self.cfg["reminder_delay"] * SECONDS_PER_MIN,
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
            await self.kill_timer(entity)

    async def kill_timer(self, entity: str) -> None:
        """Cancel scheduled task/timers."""
        if self.handles[entity]:
            await self.cancel_timer(self.handles[entity])
            self.adu.log(
                f"{hl(await self.friendly_name(entity))} closed → timer stopped",
                icon=APP_ICON,
            )

    async def get_temperatures(self, entity: str) -> Sequence[float]:
        """Get temperature indoor, outdoor and the abs. difference of both."""
        indoor = float(
            await self.get_state(self.sensors[entity], default=STATE_UNKNOWN)
        )
        outdoor = float(
            await self.get_state(self.sensor_outdoor, default=STATE_UNKNOWN)
        )
        return (indoor, outdoor, outdoor - indoor)
