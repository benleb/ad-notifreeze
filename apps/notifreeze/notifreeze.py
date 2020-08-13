"""Notifreeze
   Notifies about windows which should be closed.

    @benleb / https://github.com/benleb/ad-notifreeze
"""

__version__ = "0.4.4"

import re

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pprint import pformat
from statistics import fmean
from sys import version_info
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Union

import hassapi as hass


APP_NAME = "NotiFreeze"
APP_ICON = "❄️ "

# state set by home assistant if entity exists but has no state
STATE_UNKNOWN = "unknown"

SECONDS_PER_MIN: int = 60
LGY_INTERVAL: int = 60

# default values
DEFAULT_MAX_DIFFERENCE = 5.0
DEFAULT_INITIAL = 5
DEFAULT_REMINDER = 3

KEYWORD_DOOR_WINDOW = "binary_sensor.door_window_"
KEYWORD_TEMPERATURE = "sensor.temperature_"

# version checks
py3_or_higher = version_info.major >= 3
py37_or_higher = py3_or_higher and version_info.minor >= 7
py38_or_higher = py3_or_higher and version_info.minor >= 8


def hl(text: Union[int, float, str]) -> str:
    return f"\033[1m{text}\033[0m"


def hl_entity(entity: str) -> str:
    domain, entity = entity.split(".")
    return f"{domain}.{hl(entity)}"


async def get_timestring(last_changed: datetime) -> str:
    # exact state-change time but not relative/readable time
    last_changed = datetime.fromisoformat(str(last_changed))

    # calculate timedelta
    opened_ago = datetime.now().astimezone() - last_changed.astimezone()

    opened_ago_min, opened_ago_sec = divmod(
        (datetime.now().astimezone() - last_changed.astimezone()).total_seconds(), 60.0
    )

    # append suitable unit
    if opened_ago.total_seconds() >= SECONDS_PER_MIN:
        if opened_ago_sec < 10:
            open_since = f"{hl(int(opened_ago_min))}min"
        else:
            open_since = f"{hl(int(opened_ago_min))}min {hl(int(opened_ago_sec))}sec"
    else:
        open_since = f"{hl(int(opened_ago_sec))}sec"

    return open_since


@dataclass
class Room:
    """Class for keeping track every room."""

    name: str
    sensors_indoor: Set[str]
    sensors_door_window: Set[str]
    handles: Set[str] = field(default_factory=set, init=False)


class NotiFreeze(hass.Hass):  # type: ignore
    """Notifies about windows which should be closed."""

    def lg(self, msg: str, *args: Any, icon: Optional[str] = None, repeat: int = 1, **kwargs: Any) -> None:
        kwargs.setdefault("ascii_encode", False)
        message = f"{f'{icon} ' if icon else ' '}{msg}"
        _ = [self.log(message, *args, **kwargs) for _ in range(repeat)]

    def listr(self, list_or_string: Union[List[str], Set[str], str], entities_exist: bool = True) -> Set[str]:
        entity_list: List[str] = []

        if isinstance(list_or_string, str):
            entity_list.append(list_or_string)
        elif isinstance(list_or_string, list) or isinstance(list_or_string, set):
            entity_list += list_or_string
        elif list_or_string:
            self.lg(f"{list_or_string} is of type {type(list_or_string)} and not 'Union[List[str], Set[str], str]'")

        return set(filter(self.entity_exists, entity_list) if entities_exist else entity_list)

    async def initialize(self) -> None:
        """Initialize a room with NotiFreeze."""
        self.icon = APP_ICON

        # get a real dict for the configuration
        self.args = dict(self.args)

        # python version check
        if not py38_or_higher:
            icon_alert = "⚠️"
            self.lg("", icon=icon_alert)
            self.lg("")
            self.lg(f" please update to {hl('Python >= 3.8')}! 🤪", icon=icon_alert)
            self.lg("")
            self.lg("", icon=icon_alert)
        if not py37_or_higher:
            raise ValueError

        # general notification
        self.notify_service = str(self.args.pop("notify_service")).replace(".", "/")

        # max difference outdoor - indoor
        self.max_difference = float(self.args.pop("max_difference", DEFAULT_MAX_DIFFERENCE))

        # times/durations are given in minutes
        if delays := self.args.pop("delays"):
            self.initial_delay = int(delays.pop("initial", DEFAULT_INITIAL))
            self.reminder_delay = int(delays.pop("reminder", DEFAULT_REMINDER))
        else:
            self.initial_delay = DEFAULT_INITIAL
            self.reminder_delay = DEFAULT_REMINDER

        # sensors
        self.sensors: Dict[str, Any] = {}
        # outdoor temperature sensors
        self.sensors_outdoor = self.listr(self.args.pop("outdoor"))

        # set room(s)
        self.rooms: List[Room] = []

        if rooms := self.listr(self.args.pop("rooms")):

            for configured_room in rooms:
                # enumerate sensors for motion detection
                room = Room(
                    name=configured_room.capitalize(),
                    sensors_door_window=self.listr(
                        self.args.pop("door_window", await self.find_sensors(KEYWORD_DOOR_WINDOW, configured_room))
                    ),
                    sensors_indoor=self.listr(
                        self.args.pop("indoor", await self.find_sensors(KEYWORD_TEMPERATURE, configured_room))
                    ),
                )

                if room.sensors_door_window and room.sensors_indoor:
                    for entity in room.sensors_door_window:
                        if self.entity_exists(entity):
                            await self.listen_state(self.handler, entity=entity, room=room)
                else:
                    continue

                self.rooms.append(room)

        # requirements check
        if not self.notify_service or not self.sensors_outdoor:
            self.lg("")
            # self.lg(
            #     f"{hl('No lights/sensors')} given and none found with name: "
            #     f"'{hl(KEYWORD_LIGHTS)}*{hl(self.room)}*' or '{hl(KEYWORD_MOTION)}*{hl(self.room)}*'",
            #     icon="⚠️ ",
            # )
            self.lg("")
            self.lg(f"{self.notify_service = }")
            self.lg(f"{await self.entity_exists(self.notify_service) = }")
            # self.lg(f"{await self.entity_exists(self.sensor_outdoor) = }")
            self.lg("")
            self.lg("  docs: https://github.com/benleb/ad-notifreeze")
            self.lg("")
            return

        # set units
        self.args.setdefault("_units", {"max_difference": "°C", "initial": "min", "reminder": "min"})
        self.args.setdefault("_prefixes", {"max_difference": "±"})

        self.args.update(
            {
                "max_difference": self.max_difference,
                "notify_service": self.notify_service.replace("/", "."),
                "sensors_outdoor": self.sensors_outdoor,
                "delays": {"initial": self.initial_delay, "reminder": self.reminder_delay},
                "rooms": [room.__dict__ for room in self.rooms],
            }
        )

        # show parsed config
        self.show_info(self.args)

    async def handler(self, entity: str, attr: Any, old: str, new: str, kwargs: Dict[str, Any]) -> None:
        """Handle state changes."""

        room: Room = kwargs["room"]

        try:
            indoor, outdoor, difference = await self.get_temperatures(room)
        except ValueError:
            self.lg(f"Sensor {hl(entity)} is currently unavailable, retrying later...", icon=APP_ICON, level="WARNING")
            return
        except TypeError as error:
            self.lg(f"No valid temperature values from sensor {entity}: {error}", icon=APP_ICON, level="ERROR")
            return

        if all([old == "off", new == "on", abs(difference) > float(self.max_difference)]):
            # door/window opened, schedule reminder/notification
            room.handles.update(
                [
                    await self.run_in(
                        self.notification, self.initial_delay * SECONDS_PER_MIN, entity_id=entity, room=room
                    )
                ]
            )

            self.lg(
                f"{hl(await self.friendly_name(entity))} opened, "
                f"{hl(f'{difference:+.1f}°C')} → "
                f"reminder in {self.initial_delay}min\033[0m",
                icon=APP_ICON,
            )

        elif old == "on" and new == "off" and entity in room.handles:
            # door/window closed, canceling scheduled callbacks
            await self.clear_handles(room)

    async def notification(self, kwargs: Dict[str, Any]) -> None:
        """Send notification."""
        room: Room = kwargs["room"]
        entity_id: str = kwargs["entity_id"]
        counter: int = int(kwargs.get("counter", 1))

        try:
            indoor, outdoor, difference = await self.get_temperatures(room)
        except (ValueError, TypeError) as error:
            self.lg(f"No valid temperature values to calculate difference: {error}", icon=APP_ICON, level="ERROR")
            return

        if abs(difference) > float(self.max_difference) and await self.get_state(entity_id) == "on":

            # build notification/log msg
            initial: float = kwargs.get("initial", indoor)
            message = await self.create_message(entity_id, indoor, initial)

            # send notification
            await self.call_service(self.notify_service, message=re.sub(r"\033\[\dm", "", message))

            # schedule next reminder
            room.handles.add(
                await self.run_in(
                    self.notification,
                    self.reminder_delay * SECONDS_PER_MIN,
                    entity_id=entity_id,
                    room=room,
                    initial=initial,
                    counter=counter + 1,
                )
            )

            # debug
            self.lg(f"notification to {self.notify_service}: {message}", icon=APP_ICON, level="DEBUG")

        elif entity_id in room.handles:
            # temperature difference in allowed thresholds, cancelling scheduled callbacks
            await self.clear_handles(room)

    async def find_sensors(self, keyword: str, room: str) -> List[str]:
        """Find sensors by looking for a keyword in the friendly_name."""
        return [
            sensor
            for sensor in await self.get_state()
            if keyword in sensor and room in (await self.friendly_name(sensor)).lower()
        ]

    async def create_message(self, entity_id: str, indoor: float, initial: float) -> str:
        open_since = await get_timestring(await self.get_state(entity_id, attribute="last_changed"))
        indoor_difference: float = indoor - initial
        message: str = (f"{await self.friendly_name(entity_id)} open since {open_since}: {initial:.1f}°C")
        if indoor != initial:
            message = message + f" → {indoor} ({hl(f'{indoor_difference:+.1f}°C')})"

        return message

    async def clear_handles(self, room: Room) -> None:
        """clear scheduled timers/callbacks."""
        handles = deepcopy(room.handles)
        room.handles.clear()
        [await self.cancel_timer(handle) for handle in handles]

    async def get_temperatures(self, room: Room) -> Sequence[float]:
        """Get temperature indoor, outdoor and the abs. difference of both."""
        indoor = fmean([float(await self.get_state(sensor)) for sensor in room.sensors_indoor])
        outdoor = fmean([float(await self.get_state(sensor)) for sensor in self.sensors_outdoor])
        difference = round(outdoor - indoor, 2)

        self.lg(f"{outdoor = } - {indoor = } | {difference = }")
        return (indoor, outdoor, difference)

    def show_info(self, config: Optional[Dict[str, Any]] = None) -> None:
        # check if a room is given

        if config:
            self.config = config

        if not self.config:
            self.lg("no configuration available", icon="‼️", level="ERROR")
            return

        room = ""
        if "room" in self.config:
            room = f" · {hl(self.config['room'].capitalize())}"

        self.lg("")
        self.lg(f"{hl(APP_NAME)}{room}", icon=self.icon)
        self.lg("")

        listeners = self.config.pop("listeners", None)

        for key, value in self.config.items():

            # hide "internal keys" when displaying config
            if key in ["module", "class", "handles"] or key.startswith("_"):
                continue

            if isinstance(value, list) or isinstance(value, set):
                self.print_collection(key, value, 2)
            elif isinstance(value, dict):
                self.print_collection(key, value, 2)
            else:
                self._print_cfg_setting(key, value, 2)

        if listeners:
            self.lg("  event listeners:")
            for listener in sorted(listeners):
                self.lg(f"    · {hl(listener)}")

        self.lg("")

    def print_collection(self, key: str, collection: Iterable[Any], indentation: int = 0) -> None:

        self.lg(f"{indentation * ' '}{key}:")
        indentation = indentation + 2

        for item in collection:
            indent = indentation * " "

            if item == "handles":
                continue
            if collection == "handles":
                return

            if isinstance(item, dict):

                if "name" in item:
                    self.print_collection(item.pop("name", ""), item, indentation)
                else:
                    self.lg(f"{indent}{hl(pformat(item, compact=True))}")

            elif isinstance(collection, dict):

                if isinstance(collection[item], set):
                    self.print_collection(item, collection[item], indentation)
                else:
                    self._print_cfg_setting(item, collection[item], indentation)

            else:
                self.lg(f"{indent}· {hl(item)}")

    def _print_cfg_setting(self, key: str, value: Union[int, str], indentation: int) -> None:
        unit = prefix = ""
        indent = indentation * " "

        # legacy way
        if key == "delay" and isinstance(value, int):
            unit = "min"
            min_value = f"{int(value / 60)}:{int(value % 60):02d}"
            self.lg(f"{indent}{key}: {prefix}{hl(min_value)}{unit} ≈ " f"{hl(value)}sec", ascii_encode=False)

        else:
            if "_units" in self.config and key in self.config["_units"]:
                unit = self.config["_units"][key]
            if "_prefixes" in self.config and key in self.config["_prefixes"]:
                prefix = self.config["_prefixes"][key]

            self.lg(f"{indent}{key}: {prefix}{hl(value)}{unit}")
