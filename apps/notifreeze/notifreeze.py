"""Notifreeze
   Notifies about windows which should be closed.

    @benleb / https://github.com/benleb/ad-notifreeze
"""

__version__ = "0.6.0"

import re

from datetime import datetime
from pathlib import PurePath
from pprint import pformat
from statistics import fmean
from sys import version_info
from typing import Any, Dict, Iterable, List, Optional, Set, Union

import hassapi as hass


APP_NAME = "NotiFreeze"
APP_ICON = "❄️ "

# default values
DEFAULT_MAX_DIFFERENCE = 5.0
DEFAULT_INITIAL = 5
DEFAULT_REMINDER = 3

KEYWORD_DOOR_WINDOW = "binary_sensor.door_window_"
KEYWORD_TEMPERATURE = "sensor.temperature_"

# translations
MSGS: Dict[str, Dict[str, str]] = {
    "en_US": {
        "since": "{room_name} {entity_name} open since {open_since}: {initial}°C",
        "change": "{room_name} {entity_name} open since {open_since}: {initial}°C → {indoor}°C ({indoor_difference}°C)",
    },
    "de_DE": {
        "since": "{room_name} {entity_name} offen seit {open_since}: {initial}°C",
        "change": "{room_name} {entity_name} offen seit {open_since}: {initial}°C → {indoor}°C ({indoor_difference}°C)",
    },
}

# helper
SECONDS_PER_MIN: int = 60

# version checks
py3_or_higher = version_info.major >= 3
py37_or_higher = py3_or_higher and version_info.minor >= 7
py38_or_higher = py3_or_higher and version_info.minor >= 8
py39_or_higher = py3_or_higher and version_info.minor >= 9


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
        (datetime.now().astimezone() - last_changed.astimezone()).total_seconds(), float(SECONDS_PER_MIN)
    )

    # append suitable unit
    if opened_ago.total_seconds() >= SECONDS_PER_MIN:
        if opened_ago_sec < 10 or opened_ago_sec > 50:
            open_since = f"{hl(int(opened_ago_min))}min"
        else:
            open_since = f"{hl(int(opened_ago_min))}min {hl(int(opened_ago_sec))}sec"
    else:
        open_since = f"{hl(int(opened_ago_sec))}sec"

    return open_since


class Room:
    """Class for keeping track of a room."""

    def __init__(
        self,
        name: str,
        door_window: Set[str],
        temperature: Set[str],
    ) -> None:

        self.name: str = name
        # door/window sensors of a room
        self.door_window: Set[str] = door_window
        # temperature sensors of a room
        self.temperature: Set[str] = temperature
        # reminder notification callback handles
        self.handles: Dict[str, str] = {}

    async def indoor(self, nf: Any) -> Optional[float]:
        indoor_temperatures = set()
        invalid_sensors = {}

        for sensor in self.temperature:
            try:
                indoor_temperatures.add(float(await nf.get_state(sensor)))
            except ValueError:
                invalid_sensors[sensor] = await nf.get_state(sensor)
                continue

        if indoor_temperatures:
            return fmean(indoor_temperatures)

        nf.lg(f"{self.name}: No valid values ¯\\_(ツ)_/¯ {invalid_sensors = }")

        return None

    async def difference(self, outdoor: float, nf: Any) -> Optional[float]:
        return round(outdoor - indoor, 2) if (indoor := await self.indoor(nf)) else None


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

    async def outdoor(self) -> float:
        return fmean([float(await self.get_state(sensor)) for sensor in self.sensors_outdoor])

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
            self.lg(f" please update to {hl('Python >= 3.9')} (or >= 3.8 at least)! 🤪", icon=icon_alert)
            self.lg("")
            self.lg("", icon=icon_alert)
        if not py37_or_higher:
            raise ValueError

        # general notification
        self.notify_service = str(self.args.pop("notify_service")).replace(".", "/")

        # notify eveb when indoor temperature is not changing
        self.always_notify = bool(self.args.pop("always_notify", False))

        # language
        self.msgs = MSGS.get(self.args.pop("locale", "en_US"))

        if own_messages := self.args.pop("messages", None):
            since = own_messages.pop("since", self.msgs.get("since"))
            change = own_messages.pop("change", self.msgs.get("change"))
            self.msgs = {"since": since, "change": change}

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

        # entity list
        states_sensor = self.get_state(entity_id="sensor")
        states_binary_sensor = self.get_state(entity_id="binary_sensor")

        # set room(s)
        self.rooms: Dict[str, Room] = {}

        if rooms := self.args.pop("rooms"):

            for room_config in rooms:

                room_name: str = str()

                # door/window sensors of a room
                door_window: Set[str] = set()
                # temperature sensors of a room
                indoor: Set[str] = set()

                #  very hacky, needs refactoring
                if isinstance(room_config, dict):
                    room_name = room_config.pop("name").capitalize()
                    room_alias = room_config.pop("alias", room_name)

                    door_window.update(
                        self.listr(room_config.pop("door_window", None))
                        or await self.find_sensors(KEYWORD_DOOR_WINDOW, room_alias, states=await states_binary_sensor)
                    )
                    indoor.update(
                        self.listr(room_config.pop("indoor", None))
                        or await self.find_sensors(KEYWORD_TEMPERATURE, room_alias, states=await states_sensor)
                    )

                elif isinstance(room_config, str):
                    room_name = room_alias = room_config.capitalize()
                    door_window.update(
                        await self.find_sensors(KEYWORD_DOOR_WINDOW, room_alias, states=await states_binary_sensor)
                    )
                    indoor.update(await self.find_sensors(KEYWORD_TEMPERATURE, room_alias, states=await states_sensor))

                # create room
                room = Room(name=room_name, door_window=self.listr(door_window), temperature=self.listr(indoor))

                # create state listener for all door/window sensors
                if room.door_window and room.temperature:
                    for entity in room.door_window:
                        if self.entity_exists(entity):
                            await self.listen_state(self.handler, entity=entity, room=room)
                else:
                    continue

                self.rooms[room_name] = room

        # requirements checks
        if not all([self.notify_service, self.sensors_outdoor]):
            self.lg("")
            if not self.notify_service or not self.sensors_outdoor:
                self.lg(f"No {hl('notify_service')} configured!", icon="⚠️ ")
            if not self.sensors_outdoor:
                self.lg(f"No {hl('outdoor')} sensors configured!", icon="⚠️ ")
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
                "always_notify": self.always_notify,
                "sensors_outdoor": self.sensors_outdoor,
                "delays": {"initial": self.initial_delay, "reminder": self.reminder_delay},
                **self.rooms,
            }
        )

        # show parsed config
        self.show_info(self.args)

        pyng()

    async def handler(self, entity: str, attr: Any, old: str, new: str, kwargs: Dict[str, Any]) -> None:
        """Handle state changes."""

        room: Room = kwargs.pop("room")

        self.lg(f"state change in {room.name} via {await self.fname(entity, room.name)}: {old} -> {new}", level="DEBUG")

        if old == "off" and new == "on" and (difference := await room.difference(await self.outdoor(), self)):

            if abs(difference) > float(self.max_difference):

                # door/window opened, schedule reminder/notification
                room.handles[entity] = await self.run_in(
                    self.notification, self.initial_delay * SECONDS_PER_MIN, entity_id=entity, room=room
                )

                self.lg(
                    f"{room.name} {hl(await self.fname(entity, room.name))} opened, "
                    f"{hl(f'{difference:+.1f}°C')} → reminder in {hl(self.initial_delay)}min\033[0m",
                    icon=APP_ICON,
                )

        elif old == "on" and new == "off":
            # door/window closed, canceling scheduled callbacks
            await self.clear_handles(room, entity)

    async def notification(self, kwargs: Dict[str, Any]) -> None:
        """Send notification."""
        room: Room = kwargs.pop("room")
        entity_id: str = kwargs["entity_id"]
        counter: int = int(kwargs.get("counter", 1))

        self.lg(
            f"notification for {room.name} triggered via {await self.fname(entity_id, room.name)} ({counter})",
            level="DEBUG",
        )

        if (outdoor := await self.outdoor()) and (indoor := await room.indoor(self)):

            difference = await room.difference(outdoor, self)

            if difference and abs(difference) > float(self.max_difference) and await self.get_state(entity_id) == "on":

                # build notification/log msg
                initial: float = float(kwargs.get("initial", indoor))
                indoor_difference: float = indoor - initial

                self.lg(
                    f"notification for {room.name} via {await self.fname(entity_id, room.name)}: "
                    f"{indoor = } - {initial = } = {indoor_difference = }",
                    level="DEBUG",
                )

                if abs(indoor_difference) > 0 or self.always_notify:

                    message = await self.create_message(room, entity_id, indoor, initial)

                    # send notification
                    await self.call_service(self.notify_service, message=re.sub(r"\033\[\dm", "", message))

                    # schedule next reminder
                    room.handles[entity_id] = await self.run_in(
                        self.notification,
                        self.reminder_delay * SECONDS_PER_MIN,
                        entity_id=entity_id,
                        room=room,
                        initial=initial,
                        counter=counter + 1,
                    )

                    # debug
                    self.lg(f"notifying {hl(PurePath(self.notify_service).stem.capitalize())}: {message}", icon=f"{APP_ICON} ❗")

            elif entity_id in room.handles:
                # temperature difference in allowed thresholds, cancelling scheduled callbacks
                await self.clear_handles(room, entity_id)

    async def find_sensors(self, keyword: str, room_name: str, states: Dict[str, Dict[str, Any]]) -> List[str]:
        """Find sensors by looking for a keyword in the friendly_name."""
        room_name = room_name.lower()
        matches: List[str] = []
        for state in states.values():
            if (
                keyword in (entity_id := state.get("entity_id", ""))
                and room_name in "|".join([entity_id, state.get("attributes", {}).get("friendly_name", "")]).lower()
            ):
                matches.append(entity_id)

        return matches

    async def create_message(self, room: Room, entity_id: str, indoor: float, initial: float) -> str:
        tpl = self.msgs["since"] if indoor == initial else self.msgs["change"]
        return tpl.format(
            room_name=room.name,
            entity_name=hl(await self.fname(entity_id, room.name)),
            open_since=await get_timestring(await self.get_state(entity_id, attribute="last_changed")),
            initial=round(initial, 1),
            indoor=round(indoor, 1),
            indoor_difference=f"{(indoor - initial):+.1f}",
        )

    async def fname(self, entity: str, room_name: str) -> str:
        """Return a new friendly name by stripping the room name of the orig. friendly name."""
        return (await self.friendly_name(entity)).replace(room_name, "").strip()

    async def clear_handles(self, room: Room, entity: str) -> None:
        """clear scheduled timers/callbacks."""
        if handle := room.handles.pop(entity, None):
            await self.cancel_timer(handle)

            self.lg(f"{room.name} {hl(await self.fname(entity, room.name))} closed → timer stopped", icon=APP_ICON)

        room.handles.clear()

    def show_info(self, config: Optional[Dict[str, Any]] = None) -> None:
        # log loaded config

        if config:
            self.config = config

        if not self.config:
            self.lg("no configuration available", icon="‼️", level="ERROR")
            return

        room = ""
        if "room" in self.config:
            room = f" · {hl(self.config['room'].capitalize())}"

        self.lg("")
        self.lg(f"{hl(APP_NAME)} v{hl(__version__)}{room}", icon=self.icon)
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
            elif isinstance(value, Room):
                self.print_collection(key, value.__dict__, 2)
            else:
                self._print_cfg_setting(key, value, 2)

        if listeners:
            self.lg("  event listeners:")
            for listener in sorted(listeners):
                self.lg(f"    · {hl(listener)}")

        self.lg("")

    def print_collection(self, key: str, collection: Iterable[Any], indentation: int = 0) -> None:

        if isinstance(collection, set) and len(collection) == 1:
            self.lg(f"{indentation * ' '}{key.replace('_', ' ')}: {hl_entity(list(collection)[0])}")
            return

        self.lg(f"{indentation * ' '}{key}:")
        indentation = indentation + 2

        for item in collection:
            indent = indentation * " "

            if item in ["name", "handles"]:
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

        # hide "internal keys" when displaying config
        if key.startswith("_"):
            return

        # legacy way
        if key == "delay" and isinstance(value, int):
            unit = "min"
            min_value = f"{int(value / 60)}:{int(value % 60):02d}"
            self.lg(f"{indent}{key.replace('_', ' ')}: {prefix}{hl(min_value)}{unit} ≈ " f"{hl(value)}sec")

        else:
            if "_units" in self.config and key in self.config["_units"]:
                unit = self.config["_units"][key]
            if "_prefixes" in self.config and key in self.config["_prefixes"]:
                prefix = self.config["_prefixes"][key]

            self.lg(f"{indent}{key.replace('_', ' ')}: {prefix}{hl(value)}{unit}")


def pyng():
    # ping
    try:
        from http.client import HTTPSConnection
        from json import dumps
        from uuid import uuid1

        HTTPSConnection("jena.benleb.de", 7353).request(  # nosec
            "POST",
            "/pyng",
            body=dumps(
                {
                    "app": APP_NAME.lower(),
                    "version": __version__,
                    "uuid": str(uuid1()),
                    "python": f"{version_info.major}.{version_info.minor}.{version_info.micro}",
                }
            ),
        )
    except:  # noqa # nosec
        pass
