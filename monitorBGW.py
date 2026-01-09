#!/usr/bin/env python
# -*- encoding: utf-8 -*-

"""
##############################################################################
## Name: monitorBGW.py
## Purpose: This tool monitors Avaya G4xx Branch gateways
## Date: 2026-01-08
## Author: sszokoly@protonmail.com
## License: MIT
## Version: 0.2
## Source: https://github.com/sszokoly/monitorBGW
##############################################################################

This is an application to monitor Avaya Branch gateways.
- It uses curses for the UI and asyncio for asynchronous operations.
- Compatible with Python 3.6 only as this tool is expected to be run
  on the Active Avaya Communicarion Manager 10.x server.
- If run outside of CM on a Linux server, Python 3.6, 'expect' package
  and SSH access to the gateways is required.
- For media gateway packet capture upload it runs a local HTTP server
  on port 8080 by default and expects communication to be allowed on
  the network from the gateways to the Active CM shared IP address.
- User -h or --help to see all command line options.

Examples:
    python3 monitorBGW -u root -p password
"""

############################## BEGIN IMPORTS ##################################

import os
os.environ["NCURSES_NO_UTF8_ACS"] = "1"
os.environ["ESCDELAY"] = "25"
os.nice(19)

import argparse
import asyncio
import base64
import _curses, curses, curses.ascii, curses.panel, curses.textpad
import json
import locale
import logging
import re
import resource
import sys
import termios
import time
import zlib

from abc import ABC, abstractmethod
from asyncio import Queue, Semaphore
from bisect import insort_left
from contextlib import contextmanager
from collections.abc import MutableMapping, ItemsView
from datetime import datetime
from functools import partial
from urllib.parse import unquote
from typing import AbstractSet, Any, Callable, Coroutine, Dict, FrozenSet
from typing import Generator, Generic, Iterable, Iterator, ItemsView
from typing import List, Mapping, MutableMapping, Optional, Set, Sequence
from typing import Tuple, TypeVar, Union
from typing import TYPE_CHECKING

LOG_FORMAT = "%(asctime)s - %(levelname)8s - %(message)s [%(funcName)s:%(lineno)s]"
logger = logging.getLogger(__name__)

############################## END IMPORTS ###################################
############################## BEGIN CONFIG ###################################

CONFIG = {
    "user": "",
    "passwd": "",
    "max_polling": 20,
    "timeout": 20,
    "polling_secs": 20,
    "loglevel": "NOTSET",
    "logfile": "monitorBGW.log",
    "storage_maxlen": 999,
    "http_server": "0.0.0.0",
    "http_port": 8080,
    "upload_dir": "/tmp",
    "nok_rtp_only": False,
    "discovery_commands": [
        "set utilization cpu",
        "rtp-stat-service",
        "show running-config",
        "show system",
        "show faults",
        "show capture",
        "show voip-dsp",
        "show temp",
        "show port",
        "show sla-monitor",
        "show announcements files",
        "show lldp config",
        "show mg list",
        "show rtp-stat thresholds",
        "show utilization"
    ],
    "query_commands": [
        "show voip-dsp",
        "show rtp-stat summary",
        "show utilization",
        "show capture"
    ],
    "capture_setup": [
            "capture buffer-mode non-cyclic",
            "capture max-frame-size 4096",
            "no ip capture-list 501",
            "ip capture-list 501",
            "name udp",
            "ip-rule 1",
            "ip-protocol udp",
            "composite-operation Capture",
            "exit",
            "ip-rule default",
            "composite-operation No-Capture",
            "exit",
            "exit",
            "capture filter-group 501"
    ],
}

############################## END CONFIG #####################################
############################## BEGIN STORAGE ##################################

K = TypeVar("K", bound=Any)
V = TypeVar("V")

class AbstractRepository(ABC, Generic[K, V]):
    """Abstract key/value repository interface."""

    @abstractmethod
    def put(self, items: Dict[K, V]) -> None:
        """Insert or update multiple items."""
        raise NotImplementedError

    @abstractmethod
    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """Return a single item by key or default."""
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        """Remove all items."""
        raise NotImplementedError

class SlicableOrderedDict(MutableMapping, Generic[K, V]):
    """
    Mutable mapping that keeps keys sorted and supports index/slice retrieval.

    Notes:
        - `__getitem__` supports:
          * int index -> V
          * slice -> List[V]
          * tuple(int,int) -> List[V]  (slice-like)
          * key -> V
    """

    def __init__(
        self,
        items: Optional[Dict[K, V]] = None,
        maxlen: Optional[int] = None,
        name: Optional[str] = None,
    ) -> None:
        self._items = dict(items) if items else {}  # type: Dict[K, V]
        self._keys = sorted(self._items.keys()) if items else []  # type: List[K]
        self.maxlen = maxlen
        self.name = name

    def __iter__(self) -> Iterator[K]:
        yield from self._keys

    def __getitem__(
        self,
        key: Union[int, slice, Tuple[int, int], K],
    ) -> Union[V, List[V]]:
        if isinstance(key, slice):
            idxs = range(len(self._items)).__getitem__(key)
            return [self._items[self._keys[i]] for i in idxs]

        if isinstance(key, tuple):
            idxs = range(len(self._items)).__getitem__(slice(*key))
            return [self._items[self._keys[i]] for i in idxs]

        if isinstance(key, int):
            if 0 <= key < len(self._items):
                return self._items[self._keys[key]]
            raise KeyError(key)

        return self._items[key]

    def __setitem__(self, key: K, item: V) -> None:
        if key in self._items:
            self._items[key] = item
            return

        if self.maxlen and len(self._items) == self.maxlen:
            first_key = self._keys.pop(0)
            del self._items[first_key]

        insort_left(self._keys, key)
        self._items[key] = item

    def __delitem__(self, key: K) -> None:
        if key not in self._items:
            raise KeyError(key)
        del self._items[key]
        self._keys.remove(key)

    def __contains__(self, key: Any) -> bool:
        return key in self._items

    def index(self, key: K) -> int:
        if key in self._keys:
            return self._keys.index(key)
        raise ValueError(key)

    def keys(self) -> AbstractSet[K]:
        return self._items.keys()

    def values(self) -> Iterable[V]:
        return self._items.values()

    def items(self) -> ItemsView:
        return self._items.items()

    def clear(self) -> None:
        self._items.clear()
        self._keys[:] = []

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return "{}({}, maxlen={})".format(
            type(self).__name__, self._items, self.maxlen
        )

class MemoryStorage(SlicableOrderedDict[K, V], AbstractRepository[K, V]):
    """
    In-memory repository with sorted keys.

    - Use `get(key)` for a single item (dict-like).
    - Use `select(...)` for range/index/slice retrieval.
    """

    def put(self, items: Dict[K, V]) -> None:
        for k, v in items.items():
            self[k] = v

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        try:
            return self._items[key]
        except KeyError:
            return default

    def select(
        self,
        key: Union[slice, Tuple[int, int], int, K, None] = None,
    ) -> Union[V, List[V]]:
        """
        Retrieve by index/slice/tuple or key.
        If key is None, returns all values.
        """
        if key is None:
            key = slice(None, None)
        return self[key]

GWs = {}
BGWs = MemoryStorage(name="BGWs")
RTPs = MemoryStorage(maxlen=36, name="RTPs")
PCAPs = MemoryStorage(name="PCAPs")

############################## END STORAGE ####################################
############################## BEGIN SCRIPT ###################################

COMPRESSED_EXPECT_SCRIPT = '''\
eJzVWXtz27gR/1+fAqHpO/lBW3KbztRt2t4l6aWX5jF2rjMZidFAJCSxoUAaAK34NPruXbxIgKRsp+
2kU43HooDdxeKHfYIHT84rzs7nGT0nX0qSiMEBejcXOKMcJcV6jWmKikqUlUALVqzRD7f4DqMfGabJ
Cv2EBdngO2C5IqJiwPLz9bu3aJOJFVrqOZTRRXHaEsWRfL768B5xgUXGRZZwEPLmbx/Q37OEUE7g1y
1hPCsoGp2N0QuSoIvRxe8GB/d90AeyLnNYF/0DswzPc8LRvQyDAScC5ZjOshJt9fdOjVWcMLSV//Xv
EnO+SdFWf+sxJsqZ1J+jbf1oqBm5neWYixknXG5ilknenlGHHiciuyXOHDcs3QnNZTAFMvukx1Myr5
Zoq752g/shO0Av1ak/FjEDWVEKUIWjSQ6Hh6ICXQuWJeJVwcVrcvd8RZLPGV0+o4Wc+wVQfE2LDZXT
/K9ZTp6dp+T2nFZ5HitxIlsTsAw0Hhk4inUpUDA9OkCBOSIfy0APswSNBpgxMDMXkJke2m53O2dWnZ
EW4VHkxXKmjns0GGQLGAs1cjt4HCD4KAWAaAGao0B7yUzRzEJtM2cwHShaJWCiKMkXwIaj0LLGjUT5
UTQpyQmYa02jZkEnu2w6X6JJURLakCAcq2nQY5ZRQRjFOYoWDsFosHvw2OXJv2dFQtKKPXjm6tjhUB
L0Tw74E57gksBeuGA+SjCAJvAPzh6tceluN5hOA/kPvpyxQI8F7hhVY9QdYmqIuUNCDYnAIIZCWFYD
w1QoUgMKCKW4KGZSd3XiVq1lXswBO+P+y82M4jVR39V6DvZgjA7Ab5vftFYEPi2r65pZDY/SINhutd
K4hHNNzeA00GpMg0s0DSYuzsbG4mlwino5jeZ9rGbqfl61233canI/f41Rv+Jm8kF+i+w9UizJfln2
IKQQC7KEfZExCFJj9XtRMIIhc223n8kdusV5RcAgJvrolp0YErsmrHz7SajEKSvy1geljOP2qObvCJ
aO+3aq1Ildb2jUH7mhwZO+252CJNfs/iMAuvb7/wHCbhd47i/HG/9PcgJeZAqZ7VY/NKGAkSWv5ijC
eS7DzZRGkbgDbW4gcKCbKoOMxxAvcUKQhA0Gk4KKjFYkihDQTz6haXz8OvAjQ2jWgyinn7prvS0g/I
sVljskeXp2HDyG60VByZNH0srdGP2mKqHuZVK42fAN/9csW66EJY8dMNdQzdiioxNPdfauja9ezIzA
kQWh4Q1sJpMViJssjlVuAiMETTAtxArCsS0hSzhKTtAGw6mcnUkUHE4ljzE4raAR8YOW8Nxd1DEkvW
JaoLuiArFUuOeLhh/P3x79ubuKKjgqxggV1q5CUxvAz+G8WiwIO/JYjMVaap+7JVzC9NHNggapmVWs
bxehqZy+laoegI5H/C/A+lqsgmPnlM++rcYP6/aNFeI5IaXJEI9V0hbt/d6n24oPmqbjck6JC+VnlQ
s08SJ0HXMkVU9kyskCiAyrjSY6Qh2g57BJhvPsV5LWQYN8IUklexbdnGolVzCT6xCTygp/Cc86wkny
meWtQ50qeSF/Wi1HMuu0op9uvmTdDs2JX0wosqZLaLcZ8qN641ByBy9e/vjLT5fQnknFCfre7vL7Bs
xFXvGVIndBdapxLCro0RIsVMJ3ovFEhvA6DIPryOYEQFnzZexoaCQ8eSa36uppmq+Lp7/xVeciBSkg
WctCm5XuhBT4AHTfLvaC0QLk5dXVu6tL9DWie0BqGbGxrSDoIGgRcM77u+/q3EmhEwy6mPgHPrQqHV
m+ziq2WjHT2oDtmWOk2utiUcs9NZ03ZHZoakVRlnLrYNW6PlJm3bVgLk14nc6UNGXD5UxWXMoJ9Mnu
t2tbMFofCB1J9d49EKyNeU4U1g/uUnHLCgwruZHFiYTb07VrHga+8Z74YqZHTekCFW7vRcvWb2R7SN
RVR9wua/xNBnxVbGQFHUnPQbaMNuKCuG1d7nb9zRnN1QWF2ZB3GhC2CETEMs9EU89JP+7U6hOoBiGU
w9On4WQU/T4+OZryE9kxKxkzBC1VF9jc5I4eIMIsvR/usMvkH0DnZqyF/ldhK4Wh8b+BbePzDZcFK1
LYdCEzQntAs3s34PiIwFIeAJRs9ppfXUX3XCG2fteAteUZW3XQ6BW3H5tJv5/EXcTa7fnXGDN0fBT1
qxYcpoHGIEtnKUmyNc4dnl5yNdgmB3RgHkypZDUODQ06QePdTm9LJxSgAfo/PjNrNKT+lqx/dJAHB1
2DeQaHo6egEshyQhxNmFRm3OczLUGNvawJWxIVcKWdyO+xSgsXvs+Am8zBZmGrULNBxpfuLUnV10UT
t2y5lfOCCRRVNLuBJie07P4VmiZ+3HWivFF8gzP68F2iuk48QNcl3lB0ff1KVuEUikXY+oCrQQ4ZO7
qB7R3vdqG9aw7lJe1fzG2YFPBKlm9ESYDiLaMDv5EM3su7+oKll6ofMZ2nvsCHSGnw76liVc0RUeix
NyoM2KLGL2n/IC94BZRAv3WPkxSL/4Yo+Gtt5vg9YetM2QfUmDQjqd+S7lupYXuhuJrFnrp6N52jXl
1VIVBFgwb2RY66HZWR2FyPqtdBptmXlmUvUANYwv7WlBD+6iQ0nHyacgio0XCanhxNpkMZR3saGVkA
dK5kldk0rwMIdV8OEKozBkrlG6Dg5PBjdLiODtPTw1eXh28uD68hR+gLfjB+ghlk0UgG27o04ShIiv
IOJbgE8yeRvEw/howK5W80brzNun7DpTJTVeYFTm3RPR4F7WIuzxsWCaOqg+wLsYFfrzUqjSBcyJ6m
yHNpDv47MxmCGQEH5oKk5uVF8yrKf4HRipiTnkQc708oPVnLybiSRcWp1OeqrdMNYu1QZzJAT9EgOb
0s1rOGStNuvWr1KbGQL0dg+FpgJiLpbJeQxofT65OjU6cFsCWVA07fQj3t+GPqlJQIDHYk695aWBB7
orwfDxUv9gOOAKVxu/RvU81ha5+9UWfjnbXVMcpmkcDZ2UoooyqehBbPsF2511pPwETpErrr0AiJ0Z
/QuF99058ymYkympIvNRMax73Uui5SplvnWH6q/gLZJ0hZzRsLF+5+ed177mFYr+E3bD3YNZWM9vJ3
+sB0wgS/pPpNuNZ0oILzxLyDigcqAIcs+RfT8sbS
'''

def unwrap_and_decompress(wrapped_text):
    """Unwraps, base64 decodes and decompresses string"""
    base64_str = wrapped_text.replace("\n", "")
    compressed_bytes = base64.b64decode(base64_str)
    original_string = zlib.decompress(compressed_bytes).decode("utf-8")
    return original_string

EXPECT_SCRIPT = unwrap_and_decompress(COMPRESSED_EXPECT_SCRIPT)

############################## END SCRIPT #####################################
############################## BEGIN LAYOUT ###################################

"""
SYSTEM
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+--------------+---------------+------------+------------+-----+--+--------+
│BGW│     Name     |     LAN IP    │  LAN MAC   | Serial No. |Model│HW│Firmware│
+---+--------------+---------------+------------+------------+-----+--+--------+
|001|              |192.168.111.111|123456789ABC|13TG01116522| g430│1A│43.11.12│
+---+--------------+---------------+------------+------------+-----+--+--------+

MISC
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+------------+--------+-------------+-----+----+------+---+----+-----+-----+
│BGW│  Location  |  Temp  |    Uptime   |Chass|Main|Memory│DSP│Anno|Flash|Fault|
+---+------------+--------+-------------+-----+----+------+---+----+-----+-----+
|001|            |42C/108F|153d05h23m06s|   1A|  3A| 256MB│160│ 999|  1GB|    4|
+---+------------+--------+-------------+-----+----+------+---+----+-----+-----+

MODULE
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+------+------+------+------+------+------+------+------+--------+----+----+
│BGW│  v1  |  v2  |  v3  |  v4  |  v5  |  v6  |  v7  |  v8  | v10 hw |PSU1|PSU2|
+---+------+------+------+------+------+------+------+------+--------+----+----+
|001|S8300E│MM714B│MM714B│MM714B│MM714B│MM714B│MM714B│MM714B│      3A|400W│400W|
+---+------+------+------+------+------+------+------+------+--------+----+----+

PORT
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+-----+---------+--------+---------+-----+---------+--------+----+----+----+
|BGW|Port1| Status1 |  Neg1  |Spd1|Dup1|Port2| Status2 |  Neg2  |Spd2|Dup2|Redu|
+---+-----+---------+--------+----+----+-----+---------+--------+----+----+----+
|001| 10/4|connected| enabled|100M|full| 10/5|  no link| enabled|100M|half| 5/4|
+---+-----+---------+--------+----+----+-----+---------+--------+----+----+----+

CONFIG
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+--------+-----------------+----+--------+--------+---------------+--------+
|BGW|RTP-Stat| Capture-Service |SNMP|SNMPTrap| SLAMon | SLAMon Server |  LLDP  |
+---+--------+-----------------+----+--------+--------+---------------+--------+
|001|disabled| enabled/inactive|v2&3|disabled|disabled|101.101.111.198|disabled|
+---+--------+-----------------+----+--------+--------+---------------+--------+

PCAP
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+--------------------------+-------------------+-------------------+-------+
|BGW|          Filename        |    First Packet   |    Last Packet    |RTP|NOK| 
+---+--------------------------+-------------------+-------------------+---+---+
|001|   2025_12_19@22_05_45_001|2025-11-26 11:27:34|2025-11-26 11:27:35|  3|  1|
+---+--------------------------+-------------------+-------------------+---+---+

STATUS
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+--------+-------+-------+-----+--------+--------------+----------+--------+
|BGW|Act.Sess|Act.DSP|CPU 60s| RAM |Avg.Poll|Packet Capture|PCAP Dwnld|LastSeen|
+---+--------+-------+-------+-----+--------+--------------+----------+--------+
|001|     0/0|    320|   100%|  45%|    120s| running (54%)| executing|11:02:11|
+---+--------+-------+-------+-----+--------+--------------+----------+--------+

RTPSTATS
          1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+---+--------+--------+---------------+-----+---------------+-----+-------+----+
|BGW|  Start |   End  | Local-Address |LPort| Remote-Address|RPort| Codec | OK?|
+---+--------+--------+---------------+-----+---------------+-----+-------+----+
|001|11:09:07|11:11:27|192.168.111.111|55555|100.100.100.100|55555| G711U |  X |
+---+--------+--------+---------------+-----+---------------+-----+-------+----+
"""

LAYOUTS = {
    "SYSTEM": [
        ("BGW", {
            "attr_name": "gw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("Name", {
            "attr_name": "gw_name",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">14",
            "attr_xpos": 5,
        }),
        ("LAN IP", {
            "attr_name": "lan_ip",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">15",
            "attr_xpos": 20,
        }),
        ("LAN MAC", {
            "attr_name": "mac",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">12",
            "attr_xpos": 36,
        }),
        ("Serial No.", {
            "attr_name": "serial",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">12",
            "attr_xpos": 49,
        }),
        ("Model", {
            "attr_name": "model",
            "attr_func": lambda x: x[:4],
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_xpos": 62,
        }),
        ("HW", {
            "attr_name": "hw",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">2",
            "attr_xpos": 68,
        }),
        ("Firmware", {
            "attr_name": "fw",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 71,
        }),
    ],
    "MISC": [
        ("BGW", {
            "attr_name": "gw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("Location", {
            "attr_name": "location",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">12",
            "attr_xpos": 5,
        }),
        ("Temp", {
            "attr_name": "temp",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal"
                if x[:2].isdigit() and int(x[:2]) >= 42
                else "attr_color"
            ),
            "attr_fmt": ">8",
            "attr_xpos": 18,
        }),
        ("Uptime", {
            "attr_name": "uptime",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">13",
            "attr_xpos": 27,
        }),
        ("Chass", {
            "attr_name": "chassis_hw",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_xpos": 41,
        }),
        ("Main", {
            "attr_name": "mainboard_hw",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 47,
        }),
        ("Memory", {
            "attr_name": "memory",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">6",
            "attr_xpos": 52,
        }),
        ("DSP", {
            "attr_name": "dsp",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_xpos": 59,
        }),
        ("Anno", {
            "attr_name": "announcements",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 63,
        }),
        ("Flash", {
            "attr_name": "comp_flash",
            "attr_func": lambda x: x[:5],
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_xpos": 68,
        }),
        ("Fault", {
            "attr_name": "faults",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.strip() != "0" else "attr_color"
            ),
            "attr_fmt": ">5",
            "attr_xpos": 74,
        }),
    ],
    "MODULE": [
        ("BGW", {
            "attr_name": "gw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("v1", {
            "attr_name": "mm_v1",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 5,
        }),
        ("v2", {
            "attr_name": "mm_v2",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 12,
        }),
        ("v3", {
            "attr_name": "mm_v3",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 19,
        }),
        ("v4", {
            "attr_name": "mm_v4",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 26,
        }),
        ("v5", {
            "attr_name": "mm_v5",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 33,
        }),
        ("v6", {
            "attr_name": "mm_v6",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 40,
        }),
        ("v7", {
            "attr_name": "mm_v7",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 47,
        }),
        ("v8", {
            "attr_name": "mm_v8",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.startswith("Init") else "attr_color"
            ),
            "attr_fmt": "<6",
            "attr_xpos": 54,
        }),
        ("v10 hw", {
            "attr_name": "mm_v10",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 61,
        }),
        ("PSU1", {
            "attr_name": "psu1",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 70,
        }),
        ("PSU2", {
            "attr_name": "psu2",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 75,
        }),
    ],
    "PORT": [
        ("BGW", {
            "attr_name": "gw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("Port1", {
            "attr_name": "port1",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_xpos": 5,
        }),
        ("Status1", {
            "attr_name": "port1_status",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "connected" if "connected" in x else "attr_color"
            ),
            "attr_fmt": ">9",
            "attr_xpos": 11,
        }),
        ("Neg1", {
            "attr_name": "port1_neg",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 21,
        }),
        ("Spd1", {
            "attr_name": "port1_speed",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 30,
        }),
        ("Dup1", {
            "attr_name": "port1_duplex",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "attr_color" if "full" in x else "anormal"
            ),
            "attr_fmt": ">4",
            "attr_xpos": 35,
        }),
        ("Port2", {
            "attr_name": "port2",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_xpos": 40,
        }),
        ("Status2", {
            "attr_name": "port2_status",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "connected" if "connected" in x else "attr_color"
            ),
            "attr_fmt": ">9",
            "attr_xpos": 46,
        }),
        ("Neg2", {
            "attr_name": "port2_neg",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 56,
        }),
        ("Spd2", {
            "attr_name": "port2_speed",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 65,
        }),
        ("Dup2", {
            "attr_name": "port2_duplex",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "attr_color" if "full" in x else "anormal"
            ),
            "attr_fmt": ">4",
            "attr_xpos": 70,
        }),
        ("Redu", {
            "attr_name": "port_redu",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 75,
        }),
    ],
    "CONFIG": [
        ("BGW", {
            "attr_name": "gw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "attr_color" if x else "anormal"
            ),
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("RTP-Stats", {
            "attr_name": "rtp_stat_service",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if "disabled" in x else "attr_color"
            ),
            "attr_fmt": ">8",
            "attr_xpos": 5,
        }),
        ("Capture-Service", {
            "attr_name": "capture_service",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">17",
            "attr_xpos": 14,
        }),
        ("SNMP", {
            "attr_name": "snmp",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">4",
            "attr_xpos": 32,
        }),
        ("SNMPTrap", {
            "attr_name": "snmp_trap",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 37,
        }),
        ("SLAMon", {
            "attr_name": "slamon_service",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 46,
        }),
        ("SLAMon Server", {
            "attr_name": "sla_server",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">15",
            "attr_xpos": 55,
        }),
        ("LLDP", {
            "attr_name": "lldp",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 71,
        }),
    ],
    "STATUS": [
        ("BGW", {
            "attr_name": "gw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("Act.Sess", {
            "attr_name": "active_sessions",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 5,
        }),
        ("Act.DSP", {
            "attr_name": "inuse_dsp",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_xpos": 14,
        }),
        ("CPU", {
            "attr_name": "cpu_util",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_xpos": 22,
        }),
        ("RAM", {
            "attr_name": "ram_util",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_xpos": 28,
        }),
        ("Avg.Poll", {
            "attr_name": "avg_poll_secs",
            "attr_func": lambda x: str(x) + "s",
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 34,
        }),
        ("Packet Capture", {
            "attr_name": "packet_capture",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.strip() in ("starting", "stopping") else "attr_color"
            ),
            "attr_fmt": ">14",
            "attr_xpos": 43,
        }),
        ("Capture Upld", {
            "attr_name": "pcap_upload",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x.strip() == "requested" else "attr_color"
            ),
            "attr_fmt": ">12",
            "attr_xpos": 58,
        }),
        ("LastSeen", {
            "attr_name": "last_seen_time",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">8",
            "attr_xpos": 71,
        }),
    ],
    "RTPSTATS": [
        ("BGW", {
            "attr_name": "gw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: "attr_color" if x else "anormal",
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("Start", {
            "attr_name": "start_time",
            "attr_func": lambda x: x[-8:],
            "attr_color": "normal",
            "color_func": lambda x: "attr_color" if x else "anormal",
            "attr_fmt": "^8",
            "attr_xpos": 5,
        }),
        ("End", {
            "attr_name": "end_time",
            "attr_func": lambda x: x[-8:],
            "attr_color": "normal",
            "color_func": lambda x: "attr_color" if x else "anormal",
            "attr_fmt": "^8",
            "attr_xpos": 14,
        }),
        ("Local-Address", {
            "attr_name": "local_addr",
            "attr_func": None,
            "attr_color": "is_bgw_ip",
            "color_func": lambda x: "attr_color" if x else "anormal",
            "attr_fmt": ">15",
            "attr_xpos": 23,
        }),
        ("LPort", {
            "attr_name": "local_port",
            "attr_func": None,
            "attr_color": "port",
            "color_func": lambda x: (
                "attr_color" if x and int(x) % 2 == 0 else "odd"
            ),
            "attr_fmt": ">5",
            "attr_xpos": 39,
        }),
        ("Remote-Address", {
            "attr_name": "remote_addr",
            "attr_func": None,
            "attr_color": "address",
            "color_func": lambda x: (
                "is_bgw_ip" if x and x in GWs else "attr_color"
            ),
            "attr_fmt": ">15",
            "attr_xpos": 45,
        }),
        ("RPort", {
            "attr_name": "remote_port",
            "attr_func": None,
            "attr_color": "port",
            "color_func": lambda x: (
                "attr_color" if x and int(x) % 2 == 0 else "odd"
            ),
            "attr_fmt": ">5",
            "attr_xpos": 61,
        }),
        ("Codec", {
            "attr_name": "codec",
            "attr_func": None,
            "attr_color": "codec",
            "color_func": lambda x: (
                "attr_color" if x.startswith("G711") else "notg711"
            ),
            "attr_fmt": "^7",
            "attr_xpos": 67,
        }),
        (" OK?", {
            "attr_name": "nok",
            "attr_func": lambda x: (u" ⛔ " if x == "Zero" else
                            (u" ❗ " if x == "QoS" else u" ✅ ")),
            "attr_color": "ok_qos",
            "color_func": lambda x: ("anormal" if x == u" ⛔ " else
                            ("nok_qos" if x == u" ❗ " else "attr_color")),
            "attr_fmt": "^4",
            "attr_xpos": 75,
        }),
    ],
    "PCAP": [
        ("BGW", {
            "attr_name": "gw_number",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_xpos": 1,
        }),
        ("Filename", {
            "attr_name": "filename",
            "attr_func": lambda x: x[-26:],
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">26",
            "attr_xpos": 5,
        }),
        ("First Packet", {
            "attr_name": "first_packet_time",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">19",
            "attr_xpos": 32,
        }),
        ("Last Packet", {
            "attr_name": "last_packet_time",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">19",
            "attr_xpos": 52,
        }),
        ("RTP", {
            "attr_name": "rtp_streams",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">3",
            "attr_xpos": 72,
        }),
        ("NOK", {
            "attr_name": "rtp_problems",
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x and int(x) > 0 else "attr_color"
            ),
            "attr_fmt": ">3",
            "attr_xpos": 76,
        }),
    ],
}

"""       1         2         3         4         5         6         7
01234567890123456789012345678901234567890123456789012345678901234567890123456789
+------------------------------------------------------------------------------+
|Session-ID: 42      Status: Terminated    QoS: OK        Samples: 234         |
|Start: 11:09:07              End: 11:11:27              Duration: 00:02:20    |
|                                                                              |
|              LOCAL                                     REMOTE                |
|    192.168.111.111:55555 <--------------------> 55555:100.100.100.100        |
|      SSRC 0x12ab34cd   Enc:        G711U            SSRC 0x98fe76aa (0)      |
|                                                                              |
|             RTP/RTCP                                   CODEC                 |
| RTP Packets (Rx/Tx):  12345 /    NA         Psize/Ptime:    160/20           |
|RTCP Packets (Rx/Tx):    123 /    45           Play-Time:  00:02:20           |
|        DSCP (Rx/Tx):     46 /    46            Avg-Loss:   1.1%              |
|       L2Pri (Rx/Tx):      5 /     5             Avg-RTT:    123              |
|     Duplicates (Rx):      0              Max-Jbuf-Delay:     42              |
|       Seq-Fall (Rx):      0           JBuf-und/overruns:      1/0            |
|                                                                              |
|        LOCAL RTP STATISTICS                    REMOTE RTP STATISTICS         |
|            Avg-Loss:   1.1%                    Avg-Loss:   1.1%              |
|          Avg-Jitter:      3                  Avg-Jitter:      7              |
|             Avg-RTT:    123                                                  |
|                                                                              |
+------------------------------------------------------------------------------+
"""

RTP_LAYOUT = [
    (
        "Session-ID:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 1,
        },
    ),
    (
        "session_id",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 13,
        },
    ),
    (
        "Status:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 21,
        },
    ),
    (
        "status",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "bold" if "Active" in x else "attr_color"
            ),
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 29,
        },
    ),
    (
        "QoS:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 43,
        },
    ),
    (
        "qos",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if "Faulted" in x else "attr_color"
            ),
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 48,
        },
    ),
    (
        "Samples:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 58,
        },
    ),
    (
        "samples",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 1,
            "attr_xpos": 67,
        },
    ),
    (
        "Start:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 2,
            "attr_xpos": 1,
        },
    ),
    (
        "start_time",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 2,
            "attr_xpos": 8,
        },
    ),
    (
        "End:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 2,
            "attr_xpos": 30,
        },
    ),
    (
        "end_time",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 2,
            "attr_xpos": 35,
        },
    ),
    (
        "Duration:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 2,
            "attr_xpos": 57,
        },
    ),
    (
        "duration",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 2,
            "attr_xpos": 67,
        },
    ),
    (
        "LOCAL",
        {
            "attr_func": None,
            "attr_color": "title",
            "color_func": None,
            "attr_fmt": "^36",
            "attr_ypos": 4,
            "attr_xpos": 1,
        },
    ),
    (
        "REMOTE",
        {
            "attr_func": None,
            "attr_color": "title",
            "color_func": None,
            "attr_fmt": "^36",
            "attr_ypos": 4,
            "attr_xpos": 40,
        },
    ),
    (
        "local_addr",
        {
            "attr_func": None,
            "attr_color": "is_bgw_ip",
            "color_func": None,
            "attr_fmt": ">15",
            "attr_ypos": 5,
            "attr_xpos": 5,
        },
    ),
    (
        ":",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 5,
            "attr_xpos": 20,
        },
    ),
    (
        "local_port",
        {
            "attr_func": None,
            "attr_color": "port",
            "color_func": lambda x: (
                "attr_color" if x.strip().isdigit() and int(x.strip()) % 2 == 0
                else "odd"
            ),
            "attr_fmt": "<5",
            "attr_ypos": 5,
            "attr_xpos": 21,
        },
    ),
    (
        "<",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 5,
            "attr_xpos": 27,
        },
    ),
    (
        "-",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "-^20",
            "attr_ypos": 5,
            "attr_xpos": 28,
        },
    ),
    (
        "codec",
        {
            "attr_func": None,
            "attr_color": "codec",
            "color_func": lambda x: (
                "attr_color" if x.strip().startswith("G711") else "notg711"
            ),
            "attr_fmt": "^7",
            "attr_ypos": 5,
            "attr_xpos": 35,
        },
    ),
    (
        ">",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 5,
            "attr_xpos": 48,
        },
    ),
    (
        "remote_port",
        {
            "attr_func": None,
            "attr_color": "port",
            "color_func": lambda x: (
                "attr_color" if x.strip().isdigit() and int(x.strip()) % 2 == 0
                else "odd"
            ),
            "attr_fmt": ">5",
            "attr_ypos": 5,
            "attr_xpos": 50,
        },
    ),
    (
        ":",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 5,
            "attr_xpos": 55,
        },
    ),
    (
        "remote_addr",
        {
            "attr_func": None,
            "attr_color": "address",
            "color_func": lambda x: (
                "is_bgw_ip" if x.strip() in GWs else "attr_color"
            ),
            "attr_fmt": "<15",
            "attr_ypos": 5,
            "attr_xpos": 56,
        },
    ),
    (
        "SSRC",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 6,
            "attr_xpos": 7,
        },
    ),
    (
        "local_ssrc_hex",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 6,
            "attr_xpos": 12,
        },
    ),
    (
        "Enc:",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 6,
            "attr_xpos": 25,
        },
    ),
    (
        "codec_enc",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "encrypted" if x.strip() != "Off" else "attr_color"
            ),
            "attr_fmt": "^22",
            "attr_ypos": 6,
            "attr_xpos": 29,
        },
    ),
    (
        "SSRC",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 6,
            "attr_xpos": 54,
        },
    ),
    (
        "remote_ssrc_hex",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 6,
            "attr_xpos": 59,
        },
    ),
    (
        "remote_ssrc_change",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "bold" if x and x != "(0)" else "attr_color"
            ),
            "attr_fmt": "",
            "attr_ypos": 6,
            "attr_xpos": 70,
        },
    ),
    (
        "RTP/RTCP",
        {
            "attr_func": None,
            "attr_color": "title",
            "color_func": None,
            "attr_fmt": "^36",
            "attr_ypos": 8,
            "attr_xpos": 1,
        },
    ),
    (
        "CODEC",
        {
            "attr_func": None,
            "attr_color": "title",
            "color_func": None,
            "attr_fmt": "^36",
            "attr_ypos": 8,
            "attr_xpos": 40,
        },
    ),
    (
        "RTP Packets (Rx/Tx):",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 9,
            "attr_xpos": 2,
        },
    ),
    (
        "rx_rtp_packets",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "attr_color" if x.strip().isdigit() and int(x.strip()) > 0
                else "anormal"
            ),
            "attr_fmt": ">7",
            "attr_ypos": 9,
            "attr_xpos": 22,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 9,
            "attr_xpos": 30,
        },
    ),
    (
        "NA",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_ypos": 9,
            "attr_xpos": 32,
        },
    ),
    (
        "Psize/Ptime:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 9,
            "attr_xpos": 46,
        },
    ),
    (
        "codec_psize",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "attr_color" if x.strip() == "200B" else "anormal"
            ),
            "attr_fmt": ">4",
            "attr_ypos": 9,
            "attr_xpos": 61,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 9,
            "attr_xpos": 65,
        },
    ),
    (
        "codec_ptime",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "attr_color" if x.strip() == "20mS" else "anormal"
            ),
            "attr_fmt": "",
            "attr_ypos": 9,
            "attr_xpos": 66,
        },
    ),
    (
        "RTCP Packets (Rx/Tx):",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 10,
            "attr_xpos": 1,
        },
    ),
    (
        "rx_rtp_rtcp",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "attr_color" if x and x.strip().isdigit() and
                             int(x.strip()) > 0
                else "anormal"
            ),
            "attr_fmt": ">7",
            "attr_ypos": 10,
            "attr_xpos": 22,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 10,
            "attr_xpos": 30,
        },
    ),
    (
        "tx_rtp_rtcp",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_ypos": 10,
            "attr_xpos": 32,
        },
    ),
    (
        "Play-Time:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 10,
            "attr_xpos": 48,
        },
    ),
    (
        "codec_play_time",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 10,
            "attr_xpos": 60,
        },
    ),
    (
        "DSCP (Rx/Tx):",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 11,
            "attr_xpos": 9,
        },
    ),
    (
        "rx_rtp_dscp",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x and x != "46" else "attr_color"
            ),
            "attr_fmt": ">7",
            "attr_ypos": 11,
            "attr_xpos": 22,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 11,
            "attr_xpos": 30,
        },
    ),
    (
        "tx_rtp_dscp",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x and x != "46" else "attr_color"
            ),
            "attr_fmt": ">5",
            "attr_ypos": 11,
            "attr_xpos": 32,
        },
    ),
    (
        "Avg-Loss:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 11,
            "attr_xpos": 49,
        },
    ),
    (
        "codec_avg_loss",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">6",
            "attr_ypos": 11,
            "attr_xpos": 59,
        },
    ),
    (
        "L2Pri (Rx/Tx):",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 12,
            "attr_xpos": 8,
        },
    ),
    (
        "rx_rtp_l2pri",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 12,
            "attr_xpos": 22,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 12,
            "attr_xpos": 30,
        },
    ),
    (
        "tx_rtp_l2pri",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">5",
            "attr_ypos": 12,
            "attr_xpos": 32,
        },
    ),
    (
        "Avg-RTT:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 12,
            "attr_xpos": 50,
        },
    ),
    (
        "codec_avg_rtt",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 12,
            "attr_xpos": 58,
        },
    ),
    (
        "Duplicates (Rx):",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 13,
            "attr_xpos": 6,
        },
    ),
    (
        "rx_rtp_duplicates",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x and x != "0" else "attr_color"
            ),
            "attr_fmt": ">7",
            "attr_ypos": 13,
            "attr_xpos": 22,
        },
    ),
    (
        "Max-Jbuf-Delay:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 13,
            "attr_xpos": 43,
        },
    ),
    (
        "codec_max_jbuf_delay",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 13,
            "attr_xpos": 58,
        },
    ),
    (
        "Seq-Fall (Rx):",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 14,
            "attr_xpos": 8,
        },
    ),
    (
        "rx_rtp_seqfall",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": lambda x: (
                "anormal" if x and x != "0" else "attr_color"
            ),
            "attr_fmt": ">7",
            "attr_ypos": 14,
            "attr_xpos": 22,
        },
    ),
    (
        "JBuf-und/overruns:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 14,
            "attr_xpos": 40,
        },
    ),
    (
        "codec_jbuf_underruns",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">6",
            "attr_ypos": 14,
            "attr_xpos": 59,
        },
    ),
    (
        "/",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 14,
            "attr_xpos": 65,
        },
    ),
    (
        "codec_jbuf_overruns",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 14,
            "attr_xpos": 66,
        },
    ),
    (
        "LOCAL RTP STATISTICS",
        {
            "attr_func": None,
            "attr_color": "title",
            "color_func": None,
            "attr_fmt": "^36",
            "attr_ypos": 16,
            "attr_xpos": 1,
        },
    ),
    (
        "REMOTE RTP STATISTICS",
        {
            "attr_func": None,
            "attr_color": "title",
            "color_func": None,
            "attr_fmt": "^36",
            "attr_ypos": 16,
            "attr_xpos": 40,
        },
    ),
    (
        "Avg-Loss:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 17,
            "attr_xpos": 13,
        },
    ),
    (
        "rx_rtp_avg_loss",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 17,
            "attr_xpos": 22,
        },
    ),
    (
        "Avg-Loss:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 17,
            "attr_xpos": 49,
        },
    ),
    (
        "rem_avg_loss",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">6",
            "attr_ypos": 17,
            "attr_xpos": 59,
        },
    ),
    (
        "Avg-Jitter:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 18,
            "attr_xpos": 11,
        },
    ),
    (
        "rx_rtp_avg_jitter",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 18,
            "attr_xpos": 22,
        },
    ),
    (
        "Avg-Jitter:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 18,
            "attr_xpos": 47,
        },
    ),
    (
        "rem_avg_jitter",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 18,
            "attr_xpos": 58,
        },
    ),
    (
        "Avg-RTT:",
        {
            "attr_func": None,
            "attr_color": "dimmed",
            "color_func": None,
            "attr_fmt": "",
            "attr_ypos": 19,
            "attr_xpos": 14,
        },
    ),
    (
        "rx_rtp_avg_rtt",
        {
            "attr_func": None,
            "attr_color": "normal",
            "color_func": None,
            "attr_fmt": ">7",
            "attr_ypos": 19,
            "attr_xpos": 22,
        },
    ),
]

COLORS = {
    "default": 0,
    "normal": 0,
    "dimmed": 64000,
    "anormal": 2560,
    "connected": 12288,
    "enabled": 12288,
    "odd": 41216,
    "even": 40192,
    "notg711": 53760,
    "is_bgw_ip": 31744,
    "line": 22528,
    "bold": 2097152,
    "standout": 65536,
    "status_on": 272896,
    "status_off": 262656,
    "title": 256,
    "address": 22016,
    "port": 58624,
    "codec": 0,
    "encrypted": 10752,
    "id": 13312,
    "nok_qos": 53760,
    "ok_qos": 12288,
}

ColumnDef = Tuple[str, Dict[str, Any]]
SpecItem = Tuple[str, Dict[str, Any]]
Cell = Tuple[int, int, str, int]

class Layout(object):
    """A screen layout made of ordered column definitions.

    Each column is defined as a tuple: (column_name, attrs_dict).

    The attrs_dict typically contains:
        - "attr_name": str attribute name to read from the object
        - "attr_func": Optional[Callable[[Any], Any]] transform value
        - "attr_fmt": Optional[str] format spec (e.g. ">8", "<15")
        - "attr_xpos": int x-position for drawing
        - "attr_color": str default color name key
        - "color_func": Optional[Callable[[Any], str]] color selector
            Returns either:
              * a literal color name (e.g. "odd", "bold"), OR
              * the string "attr_color" to mean "use attrs_dict['attr_color']"
    """

    def __init__(
        self,
        columns: Iterable[ColumnDef],
        colors: Optional[Dict[str, int]] = None,
    ) -> None:
        """Initialize the Screen.

        Args:
            columns: Ordered iterable of (column_name, attrs_dict).
            colors: Mapping of color-name -> curses attribute (int).
                    If not provided, defaults to an empty dict and
                    you should pass a colors map to iter_cells().
        """
        self._columns = list(columns)
        self._by_name = {}
        self.colors = colors if colors is not None else {}

        for name, attrs in self._columns:
            if name in self._by_name:
                raise ValueError("Duplicate column name: {!r}".format(name))
            self._by_name[name] = attrs

    @property
    def columns(self) -> List[str]:
        """List of column names in display order."""
        return [name for name, _ in self._columns]

    @property
    def column_widths(self) -> List[int]:
        """List of computed widths for each column in display order."""
        return [self.column_width(name) for name in self.columns]

    def __contains__(self, name: str) -> bool:
        """Return True if a column exists by name."""
        return name in self._by_name

    def __getitem__(self, name: str) -> Dict[str, Any]:
        """Return the attrs dict for a given column name."""
        return self._by_name[name]

    def get(
        self,
        name: str,
        default: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return attrs dict for column name, or default if not found."""
        return self._by_name.get(name, default)

    def attr(self, name: str, key: str, default: Any = None) -> Any:
        """Return a single attribute from a column's attrs dict."""
        return self._by_name[name].get(key, default)

    def __iter__(self) -> Iterator[ColumnDef]:
        """Iterate (column_name, attrs_dict) in display order."""
        return iter(self._columns)

    def items(self) -> Iterator[ColumnDef]:
        """Alias for iterating column definitions."""
        return iter(self._columns)

    def column_width(self, name: str) -> int:
        """Compute column width from attr_fmt, else fall back to len(name).

        Extracts the first integer found in attr_fmt (e.g. ">14" -> 14).
        """
        fmt = self._by_name[name].get("attr_fmt")
        if not fmt:
            return len(name)

        m = re.search(r"(\d+)", str(fmt))
        return int(m.group(1)) if m else len(name)

    def iter_attrs(
        self,
        obj: Optional[Any] = None,
        *,
        row_y: int = 0,
        xoffset: int = 0,
        yoffset: int = 0,
        colors: Optional[Dict[str, int]] = COLORS,
        header: bool = False,
    ) -> Generator[Tuple[int, int, str, int], None, None]:
        """Yield (y, x, text, color) cells for this Screen"""
        cmap = colors if colors is not None else self.colors
        return iter_attrs(
            obj=obj,
            spec=self._columns,
            colors=cmap,
            xoffset=xoffset,
            yoffset=yoffset,
            default_y=row_y,
            header=header,
        )

def iter_attrs(
    obj: Optional[Any],
    spec: Iterable[SpecItem],
    colors: Dict[str, int],
    *,
    xoffset: int = 0,
    yoffset: int = 0,
    default_y: int = 0,
    header: bool = False,
) -> Generator[Cell, None, None]:
    """Render cells from a generic layout spec.

    Works for:
      - SCREENS-style specs (x only): provide default_y; omit attr_ypos
      - RTP_SCREEN-style specs (x+y): include attr_ypos in each item

    Spec dict keys supported:
      attr_name:     object attribute name (defaults to item name)
      attr_func:     callable(value) -> value
      attr_fmt:      format spec (e.g. '>8', '^36')
      attr_xpos:     x position
      attr_ypos:     y position (optional; falls back to default_y)
      attr_color:    default color name key (e.g. 'normal')
      color_func:    callable(value) -> str
                    returns either a literal color name OR 'attr_color'

    Args:
        obj: Object providing attributes; if None render labels.
        spec: Iterable of (name, attrs_dict) items.
        colors: Color name -> curses int attribute.
        xoffset/yoffset: Applied to coordinates.
        default_y: Used when attr_ypos is missing.
        header: If True, render item names (labels) instead of object values.

    Yields:
        (y, x, text, color_attr)
    """
    normal = int(colors.get("normal", 0))

    for name, d in spec:
        y = int(d.get("attr_ypos", default_y)) + yoffset
        x = int(d.get("attr_xpos", 0)) + xoffset

        # Value
        if header or obj is None:
            value = name
        else:
            attr_name = d.get("attr_name", name)
            value = getattr(obj, attr_name, name)

            fn = d.get("attr_func")
            if fn:
                try:
                    value = fn(value)
                except Exception:
                    pass

        # Color name
        cname = d.get("attr_color", "normal")
        cfn = d.get("color_func")
        
        if header or obj is None:
            cname = "normal"
        
        elif cfn:
            try:
                chosen = cfn(value)
                if chosen == "attr_color":
                    cname = d.get("attr_color", "normal")
                else:
                    cname = chosen
            except Exception:
                pass

        color_attr = int(colors.get(cname, normal))

        # Format
        fmt = d.get("attr_fmt")
        if fmt:
            try:
                ln = "".join(c for c in fmt if c.isdigit())
                if header or obj is None:
                    centered = "^" + ln if ln else "^" + str(len(value))
                    value = "{:{}}".format(value, centered)
                else:
                    ln = int(ln) if ln else None
                    value = "{:{}}".format(str(value)[:ln], fmt)
            except Exception:
                pass

        yield y, x, str(value), color_attr

############################## END LAYOUT #####################################
############################## BEGIN FILTER ###################################

FILTER_GROUPs = {
    "bgw": {
        "current_filter": "",
        "no_filter": False,
        "groups": {
            "ip_filter": set()
            }
        },
}

FILTER_MENUs = {
    "bgw":
"""                                BGW FILTER
Filter Usage:
    -i <IP>    <IP> address input of gateways separated by | or ,   
    -n         no filter, clear current filter
 
Filter examples:
  You MAY  use -i when the script is run on a Communication Manager
  You MUST use -i when the script is run outside a Communication Manager
  To discover only gateway 10.10.10.1 and 10.10.10.2
    -i 10.10.10.1|10.10.10.2  OR  -i 10.10.10.1,10.10.10.2
"""}

class NoExitArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def is_valid_ipv4(ip: str) -> bool:
    """
    Validate whether a string is a valid IPv4 address.

    This function uses a regular expression to ensure the address:
      - Consists of exactly four octets separated by dots
      - Each octet is in the range 0–255

    Args:
        ip: The IPv4 address string to validate.

    Returns:
        True if the string is a valid IPv4 address, False otherwise.
    """
    octet = r"(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)"
    pattern = rf"^({octet}\.){{3}}{octet}$"

    return re.match(pattern, ip) is not None

def parse_and_validate_i(value: str) -> Set[str]:
    """
    Parse and validate a list of IPv4 addresses.

    The input string may contain IPv4 addresses separated by commas or
    pipe characters (`","` or `"|"`). Each IP is stripped of surrounding
    whitespace and validated.

    Args:
        value: A string containing one or more IPv4 addresses.

    Returns:
        A set of validated IPv4 address strings.

    Raises:
        argparse.ArgumentTypeError: If any IP address is invalid.
    """
    raw_ips = re.split(r"[,\|]", value)
    ips: Set[str] = set()

    for ip in raw_ips:
        ip = ip.strip()
        if not ip:
            continue

        if not is_valid_ipv4(ip):
            raise argparse.ArgumentTypeError(f"Invalid IP: {ip}")

        ips.add(ip)

    return ips

def create_filter_parser() -> "NoExitArgumentParser":
    """
    Create an argument parser for workspace filtering.

    This parser is intended for use in the curses UI filter panel. It supports a
    mutually exclusive choice between:

    - `-n`: disable filtering
    - `-i <ips>`: provide a set of BGW IPv4 addresses to discover (filter)

    Returns:
        A configured NoExitArgumentParser instance.
    """
    parser = NoExitArgumentParser(add_help=False)
    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "-n",
        dest="no_filter",
        action="store_true",
        default=False,
        help="No filter",
    )

    group.add_argument(
        "-i",
        dest="ip_filter",
        type=parse_and_validate_i,
        default=set(),  # type: Set[str]
        help="BGW IP filter list separated by | or ,",
    )

    return parser

filter_parser = create_filter_parser()

def filter_validator(line: str) -> Optional[str]:
    """
    Validate and parse a filter command line.

    This function is typically used as a validator for user input (e.g. from a
    curses text field). It sanitizes the input, attempts to parse it using the
    global `filter_parser`, and logs the parsed arguments for debugging.

    If parsing fails, the error is logged and the error message is returned.
    Returning a string is assumed to signal validation failure to the caller.

    Args:
        line: Raw input line containing filter arguments.

    Returns:
        None if the input is valid and successfully parsed.
        A string error message if validation or parsing fails.
    """
    # Strip quotes and surrounding whitespace
    cleaned = line.replace("'", "").replace('"', "").strip()

    try:
        args = filter_parser.parse_args(cleaned.split())
        logger.debug(args)
        return None

    except Exception as e:
        logger.error(repr(e))
        return str(e)

def update_filter(
    group: str,
    filter: str,
    filter_groups: MutableMapping[str, Dict[str, Any]] = FILTER_GROUPs
) -> None:
    """Update the active filter configuration for a given filter group."""
    
    group_cfg = filter_groups.get(group)
    if not group_cfg:
        return

    args = vars(filter_parser.parse_args(filter.split()))
    groups = group_cfg.get("groups", {})
    
    # Clear all filters
    if args.get("no_filter"):
        group_cfg["current_filter"] = ""
        group_cfg["no_filter"] = False
        for g in groups.values():
            g.clear()
        logger.info("Cleared all filters")
        return

    # Update filters
    if filter and filter != "-n":
        group_cfg["current_filter"] = filter
        group_cfg["no_filter"] = False
        
        for key, value in args.items():
            if key in groups and value:
                groups[key] = value
                logger.info(f"Updated '{key}' to '{value}'")

############################## END FILTER #####################################
############################## BEGIN BGW ######################################

class BGW(object):
    """Represents an Avaya Branch Gateway (BGW) and cached command outputs.

    This object is primarily a *data holder* for parsed values derived from
    various CLI command outputs (e.g. ``show system``, ``show capture``).
    Callers typically:

    - instantiate BGW with a LAN IP and defaults
    - periodically call :meth:`update` with new timestamps and command outputs
    - access properties which parse and cache derived values lazily

    Notes:
        - Many properties return "NA" when the corresponding command output is
          missing.
        - Parsed values are cached in private attributes (e.g. ``_hw``) to avoid
          repeated regex work. If you overwrite the underlying ``show_*`` string,
          you may also want to clear the relevant cache field.
    """

    def __init__(
        self,
        lan_ip: str,
        proto: str = "",
        polling_secs: int = 10,
        gw_name: str = "",
        gw_number: str = "",
        show_announcements_files: str = "",
        show_capture: str = "",
        show_faults: str = "",
        show_lldp_config: str = "",
        show_mg_list: str = "",
        show_port: str = "",
        show_rtp_stat_summary: str = "",
        show_rtp_stat_thresholds: str = "",
        show_running_config: str = "",
        show_sla_monitor: str = "",
        show_system: str = "",
        show_temp: str = "",
        show_utilization: str = "",
        show_voip_dsp: str = "",
        show_upload_status_10: str = "",
        **kwargs: Any
    ) -> None:
        # Identity / polling
        self.lan_ip = lan_ip
        self.proto = proto
        self.polling_secs = polling_secs
        self.gw_name = gw_name
        self.gw_number = gw_number

        self.polls = 0
        self.avg_poll_secs = 0.0
        self.poll_count = 0

        self.active_session_ids = set()  # type: Set[str]
        self.last_seen = ""
        self.last_seen_dt = None  # type: Optional[datetime]
        self.last_session_id = None  # type: Optional[str]

        # Raw command outputs
        self.show_announcements_files = show_announcements_files
        self.show_capture = show_capture
        self.show_faults = show_faults
        self.show_lldp_config = show_lldp_config
        self.show_mg_list = show_mg_list
        self.show_port = show_port
        self.show_rtp_stat_summary = show_rtp_stat_summary
        self.show_rtp_stat_thresholds = show_rtp_stat_thresholds
        self.show_running_config = show_running_config
        self.show_sla_monitor = show_sla_monitor
        self.show_system = show_system
        self.show_temp = show_temp
        self.show_utilization = show_utilization
        self.show_upload_status_10 = show_upload_status_10
        self.show_voip_dsp = show_voip_dsp

        # Work queue used by your polling/executor layer
        self.queue = Queue()  # type: Queue

        # --- Lazy caches (keep as you had them) ---
        self._announcements = None  # type: Optional[str]
        self._capture_service = None  # type: Optional[str]
        self._capture_status = None  # type: Optional[str]

        self._chassis_hw = None  # type: Optional[str]
        self._comp_flash = None  # type: Optional[str]
        self._cpu_util = None  # type: Optional[str]
        self._dsp = None  # type: Optional[str]
        self._faults = None  # type: Optional[str]
        self._fw = None  # type: Optional[str]
        self._hw = None  # type: Optional[str]
        self._inuse_dsp = None  # type: Optional[str]
        self._last_seen_time = None  # type: Optional[str]
        self._lldp = None  # type: Optional[str]
        self._location = None  # type: Optional[str]
        self._mac = None  # type: Optional[str]
        self._mainboard_hw = None  # type: Optional[str]
        self._memory = None  # type: Optional[str]
        self._mm_groupdict = None  # type: Optional[Dict[str, Dict[str, str]]]

        self._mm_v1 = None  # type: Optional[str]
        self._mm_v2 = None  # type: Optional[str]
        self._mm_v3 = None  # type: Optional[str]
        self._mm_v4 = None  # type: Optional[str]
        self._mm_v5 = None  # type: Optional[str]
        self._mm_v6 = None  # type: Optional[str]
        self._mm_v7 = None  # type: Optional[str]
        self._mm_v8 = None  # type: Optional[str]
        self._mm_v10 = None  # type: Optional[str]

        self._model = None  # type: Optional[str]

        self._packet_capture = ""
        self._pcap_upload = ""

        self._port1 = None  # type: Optional[str]
        self._port1_status = None  # type: Optional[str]
        self._port1_neg = None  # type: Optional[str]
        self._port1_duplex = None  # type: Optional[str]
        self._port1_speed = None  # type: Optional[str]

        self._port2 = None  # type: Optional[str]
        self._port2_status = None  # type: Optional[str]
        self._port2_neg = None  # type: Optional[str]
        self._port2_duplex = None  # type: Optional[str]
        self._port2_speed = None  # type: Optional[str]

        self._port_redu = None  # type: Optional[str]
        self._psu1 = None  # type: Optional[str]
        self._psu2 = None  # type: Optional[str]

        self._ram_util = None  # type: Optional[str]
        self._rtp_stat_service = None  # type: Optional[str]
        self._serial = None  # type: Optional[str]
        self._slamon_service = None  # type: Optional[str]
        self._sla_server = None  # type: Optional[str]
        self._snmp = None  # type: Optional[str]
        self._snmp_trap = None  # type: Optional[str]
        self._temp = None  # type: Optional[str]
        self._uptime = None  # type: Optional[str]
        self._upload_status = None  # type: Optional[str]
        self._has_filter_501 = None # type: Optional[bool]

        # Keep kwargs accepted for forward compatibility
        _ = kwargs

    # ------------------- RTP / capture -------------------

    @property
    def active_sessions(self) -> str:
        """Active Session value from RTP-Stat summary, or "NA"."""
        if not self.show_rtp_stat_summary:
            return "NA"
        m = re.search(r"nal\s+\S+\s+(\S+)", self.show_rtp_stat_summary)
        return m.group(1) if m else ""

    @property
    def announcements(self) -> str:
        """Count of announcement files, as a string, or 'NA'."""
        if self._announcements is not None:
            return self._announcements
        if not self.show_announcements_files:
            return "NA"
        m = re.findall(r"announcement file", self.show_announcements_files)
        self._announcements = str(len(m))
        return self._announcements

    @property
    def capture_service(self) -> str:
        """Capture service admin state and buffer size, 'enabled ( 1024)'."""
        if self._capture_service is not None:
            return self._capture_service
        if not self.show_capture:
            return "NA"

        m = re.search(r"Capture service is (\w+)", self.show_capture)
        state = m.group(1) if m else ""

        m = re.search(r"Current buffer size is (\d+) KB", self.show_capture)
        size = m.group(1) if m else ""

        self._capture_service = "{} ({:>5})".format(state, size)
        return self._capture_service

    @property
    def has_filter_501(self) -> bool:
        """Capture filter list 501 in ``show_capture``."""
        if not self.show_capture:
            return False

        has_filter_501 = "Capture list 501" in self.show_capture
        return has_filter_501

    @property
    def capture_status(self) -> str:
        """Capture runtime status derived from ``show_capture``."""
        if not self.show_capture or "try again" in self.show_capture:
            return "NA"

        if "disabled" in self.capture_service:
            return "inactive"

        m = re.search(r"Capture service is \w+ and (\w+)", self.show_capture)
        status = m.group(1) if m else ""

        m = re.search(r"buffer occupancy: (\d+)\.", self.show_capture)
        occ = "({:>2}%)".format(m.group(1)) if m else ""

        if (
            "Actual capture stopped" in self.show_capture
            or "and inactive" in self.show_capture
        ):
            return "stopped {}".format(occ).strip() if occ else "stopped"

        if "enabled and active" in self.show_capture:
            return "running {}".format(occ).strip() if occ else "running"

        return status or ""

    @property
    def packet_capture(self) -> str:
        """User-facing packet capture status with transitional states preserved."""
        val = (self._packet_capture or "").strip().lower()
        if val.startswith(("starting", "stopping")):
            return self._packet_capture
        return self.capture_status

    @packet_capture.setter
    def packet_capture(self, value: str) -> None:
        """State machine for capture status transitions."""
        current = getattr(self, "_packet_capture", "NA")

        value = (value or "").strip()
        current = (current or "").strip()

        def base_state(s: str) -> str:
            s = s.lower().strip()
            if not s:
                return ""
            if s == "na":
                return "NA"
            for st in ("starting", "stopping", "running", "stopped", "disabled"):
                if s.startswith(st):
                    return st
            return s

        cur_base = base_state(current)
        val_base = base_state(value)

        if val_base in ("", "NA"):
            self._packet_capture = "NA" if val_base == "NA" else ""
            return

        if val_base in ("starting", "stopping"):
            self._packet_capture = value
            return

        if cur_base == val_base and val_base in ("running", "stopped"):
            self._packet_capture = value
            return

        if cur_base in ("", "NA"):
            if val_base in ("running", "stopped", "disabled"):
                self._packet_capture = value
            return

        if cur_base == "starting":
            if val_base == "running":
                self._packet_capture = value
            return

        if cur_base == "stopping":
            if val_base == "stopped":
                self._packet_capture = value
            return

        if cur_base == "running" and val_base == "stopped":
            self._packet_capture = value

    @property
    def pcap_upload(self) -> str:
        """Upload status string (derived from upload_status)."""
        if self._pcap_upload:
            return self._pcap_upload
        return self.upload_status

    @pcap_upload.setter
    def pcap_upload(self, value: str) -> None:
        self._pcap_upload = value

    # ------------------- HW / system -------------------

    @property
    def chassis_hw(self) -> str:
        """Chassis HW vintage+suffix (from ``show_system``), or "NA"."""
        if self._chassis_hw is not None:
            return self._chassis_hw
        if not self.show_system:
            return "NA"

        m = re.search(r"HW Vintage\s+:\s+(\S+)", self.show_system)
        vintage = m.group(1) if m else ""

        m = re.search(r"HW Suffix\s+:\s+(\S+)", self.show_system)
        suffix = m.group(1) if m else ""

        self._chassis_hw = "{}{}".format(vintage, suffix)
        return self._chassis_hw

    @property
    def comp_flash(self) -> str:
        """Compact flash size/string if installed, empty string if not, or "NA"."""
        if self._comp_flash is not None:
            return self._comp_flash
        if not self.show_system:
            return "NA"

        m = re.search(r"Flash Memory\s+: (\d+)\S+ ([MG])B", self.show_system)
        size, unit = m.group(1) if m else "", m.group(2) if m else ""
        result = "{}{}B".format(size, unit) if size and unit else ""
        self._comp_flash = result
        return result

    @property
    def cpu_util(self) -> str:
        """Last 60s CPU utilization percent (from ``show_utilization``), or "NA"."""
        if not self.show_utilization:
            return "NA"
        m = re.search(r"10\s+\d+%\s+(\d+)%", self.show_utilization)
        self._cpu_util = "{}%".format(m.group(1)) if m else ""
        return self._cpu_util

    @property
    def dsp(self) -> str:
        """Total DSP count (from ``show_system``), or "NA"."""
        if self._dsp is not None:
            return self._dsp
        if not self.show_system:
            return "NA"
        m = re.findall(r"Media Socket .*?: M?P?(\d+) ", self.show_system)
        self._dsp = str(sum(int(x) for x in m)) if m else ""
        return self._dsp

    @property
    def faults(self) -> str:
        """Count of faults from ``show_faults``, or "NA"."""
        if self._faults is not None:
            return self._faults
        if not self.show_faults:
            return "NA"

        if "No Fault Messages" in self.show_faults:
            self._faults = "0"
        else:
            m = re.findall(r"\s+\+ (\S+)", self.show_faults)
            self._faults = str(len(m))
        return self._faults

    @property
    def fw(self) -> str:
        """Firmware vintage from ``show_system`` (FW Vintage), or "NA"."""
        if self._fw is not None:
            return self._fw
        if not self.show_system:
            return "NA"
        m = re.search(r"FW Vintage\s+:\s+(\S+)", self.show_system)
        result = m.group(1) if m else ""
        self._fw = result
        return result

    @property
    def hw(self) -> str:
        """Hardware vintage+suffix from ``show_system``, or "NA"."""
        if self._hw is not None:
            return self._hw
        if not self.show_system:
            return "NA"

        m = re.search(r"HW Vintage\s+:\s+(\S+)", self.show_system)
        hw_vintage = m.group(1) if m else "?"

        m = re.search(r"HW Suffix\s+:\s+(\S+)", self.show_system)
        hw_suffix = m.group(1) if m else "?"

        self._hw = "{}{}".format(hw_vintage, hw_suffix)
        return self._hw

    @property
    def last_seen_time(self) -> str:
        """Last seen time formatted HH:MM:SS (24h), or empty string."""
        if self.last_seen_dt:
            return self.last_seen_dt.strftime("%H:%M:%S")
        return ""

    @property
    def lldp(self) -> str:
        """LLDP state ('enabled'/'disabled') from ``show_lldp_config``, or "NA"."""
        if self._lldp is not None:
            return self._lldp
        if not self.show_lldp_config:
            return "NA"

        self._lldp = (
            "disabled"
            if "Application status: disable" in self.show_lldp_config
            else "enabled"
        )
        return self._lldp

    @property
    def location(self) -> str:
        """System Location from ``show_system``, or "NA"."""
        if self._location is not None:
            return self._location
        if not self.show_system:
            return "NA"

        # NOTE: your original regex had an extra space before \s+.
        m = re.search(r"System Location\s+:\s*(\S+)", self.show_system)
        result = m.group(1) if m else ""
        self._location = result
        return result

    @property
    def mac(self) -> str:
        """LAN MAC without colons (from ``show_system``), or "NA"."""
        if self._mac is not None:
            return self._mac
        if not self.show_system:
            return "NA"
        m = re.search(r"LAN MAC Address\s+:\s+(\S+)", self.show_system)
        result = m.group(1).replace(":", "") if m else ""
        self._mac = result
        return result

    @property
    def mainboard_hw(self) -> str:
        """Mainboard HW vintage+suffix from ``show_system``, or "NA"."""
        if self._mainboard_hw is not None:
            return self._mainboard_hw
        if not self.show_system:
            return "NA"

        m = re.search(r"Mainboard HW Vintage\s+:\s+(\S+)", self.show_system)
        vintage = m.group(1) if m else "N"

        m = re.search(r"Mainboard HW Suffix\s+:\s+(\S+)", self.show_system)
        suffix = m.group(1) if m else "A"

        self._mainboard_hw = "{}{}".format(vintage, suffix)
        return self._mainboard_hw

    @property
    def memory(self) -> str:
        """Total memory as '<n>MB' or model-specific raw string, or "NA"."""
        if self._memory is not None:
            return self._memory
        if not self.show_system:
            return "NA"

        if self.model and self.model.lower().startswith("g430"):
            m = re.search(r"RAM Memory\s+:\s+(\S+)", self.show_system)
            result = m.group(1) if m else ""
            self._memory = result
            return result

        m = re.findall(r"Memory #\d+\s+:\s+(\S+)", self.show_system)
        self._memory = "{}MB".format(
            sum(self._to_mbyte(x) for x in m)
        ) if m else ""
        return self._memory

    # ------------------- Media modules -------------------

    @property
    def mm_groupdict(self) -> Dict[str, Dict[str, str]]:
        """Parsed media-module table keyed by slot (e.g. 'v1', 'v2').

        Returns:
            Dict mapping slot -> parsed fields: slot/type/code/suffix/hw_vint/fw_vint.
            Returns {} if ``show_mg_list`` is missing.
        """
        if self._mm_groupdict is not None:
            return self._mm_groupdict
        if not self.show_mg_list:
            self._mm_groupdict = {}
            return self._mm_groupdict

        groupdict = {}  # type: Dict[str, Dict[str, str]]

        for text in (ln.strip() for ln in self.show_mg_list.splitlines()):
            if not (text.startswith("v") and "Not Installed" not in text):
                continue

            m = re.search(
                r".*?(?P<slot>\S+)"
                r".*?(?P<type>\S+)"
                r".*?(?P<code>\S+)"
                r".*?(?P<suffix>\S+)"
                r".*?(?P<hw_vint>\S+)"
                r".*?(?P<fw_vint>\S+)",
                text,
            )
            if m:
                groupdict[m.group("slot")] = m.groupdict()

        self._mm_groupdict = groupdict
        return self._mm_groupdict

    def _mm_v(self, slot: int) -> str:
        """Return module code+suffix for slot (e.g. 1..8)."""
        code = self.mm_groupdict.get("v{}".format(slot), {}).get("code", "")
        if code == "ICC":
            code = self.mm_groupdict.get("v{}".format(slot), {}).get("type", "")
        suffix = self.mm_groupdict.get("v{}".format(slot), {}).get("suffix", "")
        return "{}{}".format(code, suffix)

    @property
    def mm_v1(self) -> str:
        """Media module code+suffix for slot 1, or "NA"."""
        if self._mm_v1 is not None:
            return self._mm_v1
        if not self.show_mg_list:
            return "NA"
        self._mm_v1 = self._mm_v(1)
        return self._mm_v1

    @property
    def mm_v2(self) -> str:
        """Media module code+suffix for slot 2, or "NA"."""
        if self._mm_v2 is not None:
            return self._mm_v2
        if not self.show_mg_list:
            return "NA"
        self._mm_v2 = self._mm_v(2)
        return self._mm_v2

    @property
    def mm_v3(self) -> str:
        """Media module code+suffix for slot 3, or "NA"."""
        if self._mm_v3 is not None:
            return self._mm_v3
        if not self.show_mg_list:
            return "NA"
        self._mm_v3 = self._mm_v(3)
        return self._mm_v3

    @property
    def mm_v4(self) -> str:
        """Media module code+suffix for slot 4, or "NA"."""
        if self._mm_v4 is not None:
            return self._mm_v4
        if not self.show_mg_list:
            return "NA"
        self._mm_v4 = self._mm_v(4)
        return self._mm_v4

    @property
    def mm_v5(self) -> str:
        """Media module code+suffix for slot 5, or "NA"."""
        if self._mm_v5 is not None:
            return self._mm_v5
        if not self.show_mg_list:
            return "NA"
        self._mm_v5 = self._mm_v(5)
        return self._mm_v5

    @property
    def mm_v6(self) -> str:
        """Media module code+suffix for slot 6, or "NA"."""
        if self._mm_v6 is not None:
            return self._mm_v6
        if not self.show_mg_list:
            return "NA"
        self._mm_v6 = self._mm_v(6)
        return self._mm_v6

    @property
    def mm_v7(self) -> str:
        """Media module code+suffix for slot 7, or "NA"."""
        if self._mm_v7 is not None:
            return self._mm_v7
        if not self.show_mg_list:
            return "NA"
        self._mm_v7 = self._mm_v(7)
        return self._mm_v7

    @property
    def mm_v8(self) -> str:
        """Media module code+suffix for slot 8, or "NA"."""
        if self._mm_v8 is not None:
            return self._mm_v8
        if not self.show_mg_list:
            return "NA"
        self._mm_v8 = self._mm_v(8)
        return self._mm_v8

    @property
    def mm_v10(self) -> str:
        """Slot 10 module hw_vintage+suffix, or "NA".

        BUGFIX: your original code had:
            if self.show_mg_list: return "NA"
        which inverted the condition and made it always return "NA" when
        mg list exists. This is corrected below.
        """
        if self._mm_v10 is not None:
            return self._mm_v10
        if not self.show_mg_list:
            return "NA"

        suffix = self.mm_groupdict.get("v10", {}).get("suffix", "")
        hw_vint = self.mm_groupdict.get("v10", {}).get("hw_vint", "")
        self._mm_v10 = "{}{}".format(hw_vint, suffix)
        return self._mm_v10

    @property
    def model(self) -> str:
        """Gateway model from ``show_system``, or "NA"."""
        if self._model is not None:
            return self._model
        if not self.show_system:
            return "NA"
        m = re.search(r"Model\s+:\s+(\S+)", self.show_system)
        result = m.group(1) if m else ""
        self._model = result
        return result

    # ------------------- Ports -------------------

    @property
    def port1(self) -> str:
        """LAN port1 identifier (e.g. '0/1'), or 'NA'."""
        if self._port1 is not None:
            return self._port1
        pdict = self._port_groupdict(0)
        self._port1 = pdict.get("port", "") if pdict else "NA"
        return self._port1

    @property
    def port1_status(self) -> str:
        """LAN port1 link status, or 'NA'."""
        if self._port1_status is not None:
            return self._port1_status
        pdict = self._port_groupdict(0)
        self._port1_status = pdict.get("status", "") if pdict else "NA"
        return self._port1_status

    @property
    def port1_neg(self) -> str:
        """LAN port1 autoneg status, or 'NA'."""
        if self._port1_neg is not None:
            return self._port1_neg
        pdict = self._port_groupdict(0)
        self._port1_neg = pdict.get("neg", "") if pdict else "NA"
        return self._port1_neg

    @property
    def port1_duplex(self) -> str:
        """LAN port1 duplex setting, or 'NA'."""
        if self._port1_duplex is not None:
            return self._port1_duplex
        pdict = self._port_groupdict(0)
        self._port1_duplex = pdict.get("duplex", "") if pdict else "NA"
        return self._port1_duplex

    @property
    def port1_speed(self) -> str:
        """LAN port1 speed, or 'NA'."""
        if self._port1_speed is not None:
            return self._port1_speed
        pdict = self._port_groupdict(0)
        self._port1_speed = pdict.get("speed", "") if pdict else "NA"
        return self._port1_speed

    @property
    def port2(self) -> str:
        """LAN port2 identifier, or 'NA'."""
        if self._port2 is not None:
            return self._port2
        pdict = self._port_groupdict(1)
        self._port2 = pdict.get("port", "") if pdict else "NA"
        return self._port2

    @property
    def port2_status(self) -> str:
        """LAN port2 link status, or 'NA'."""
        if self._port2_status is not None:
            return self._port2_status
        pdict = self._port_groupdict(1)
        self._port2_status = pdict.get("status", "") if pdict else "NA"
        return self._port2_status

    @property
    def port2_neg(self) -> str:
        """LAN port2 autoneg status, or 'NA'."""
        if self._port2_neg is not None:
            return self._port2_neg
        pdict = self._port_groupdict(1)
        self._port2_neg = pdict.get("neg", "") if pdict else "NA"
        return self._port2_neg

    @property
    def port2_duplex(self) -> str:
        """LAN port2 duplex setting, or 'NA'."""
        if self._port2_duplex is not None:
            return self._port2_duplex
        pdict = self._port_groupdict(1)
        self._port2_duplex = pdict.get("duplex", "") if pdict else "NA"
        return self._port2_duplex

    @property
    def port2_speed(self) -> str:
        """LAN port2 speed, or 'NA'."""
        if self._port2_speed is not None:
            return self._port2_speed
        pdict = self._port_groupdict(1)
        self._port2_speed = pdict.get("speed", "") if pdict else "NA"
        return self._port2_speed

    @property
    def port_redu(self) -> str:
        """Port redundancy pair 'x/y' from ``show_running_config``, or "NA"."""
        if self._port_redu is not None:
            return self._port_redu
        if not self.show_running_config:
            return "NA"
        m = re.search(
            r"port redundancy \d+/(\d+) \d+/(\d+)",
            self.show_running_config,
        )
        self._port_redu = "{}/{}".format(m.group(1), m.group(2)) if m else ""
        return self._port_redu

    # ------------------- PSU / utilization / services -------------------

    @property
    def psu1(self) -> str:
        """PSU #1 wattage (or model-specific main PSU value), or "NA"."""
        if self._psu1 is not None:
            return self._psu1
        if not self.show_system:
            return "NA"

        if self.model and self.model.lower().startswith("g430"):
            m = re.search(r"Main PSU\s+:\s+(\S+)", self.show_system)
            result = m.group(1) if m else ""
            self._psu1 = result
            return result

        m = re.search(r"PSU #1\s+:\s+\S+ (\S+)", self.show_system)
        result = m.group(1) if m and "W" in m.group(1) else ""
        self._psu1 = result
        return result

    @property
    def psu2(self) -> str:
        """PSU #2 wattage, or "NA"."""
        if self._psu2 is not None:
            return self._psu2
        if not self.show_system:
            return "NA"
        m = re.search(r"PSU #2\s+:\s+\S+ (\S+)", self.show_system)
        result = m.group(1) if m and "W" in m.group(1) else ""
        self._psu2 = result
        return result

    @property
    def ram_util(self) -> str:
        """RAM utilization percent (from ``show_utilization``), or "NA"."""
        if not self.show_utilization:
            return "NA"
        m = re.search(r"10\s+\S+\s+\S+\s+(\d+)%", self.show_utilization)
        self._ram_util = "{}%".format(m.group(1)) if m else ""
        return self._ram_util

    @property
    def rtp_stat_service(self) -> str:
        """RTP-Stat service admin status ('enabled'/'disabled'), or "NA"."""
        if self._rtp_stat_service is not None:
            return self._rtp_stat_service
        if not self.show_running_config:
            return "NA"
        self._rtp_stat_service = (
            "enabled" if "rtp-stat-service" in self.show_running_config else "disabled"
        )
        return self._rtp_stat_service

    @rtp_stat_service.setter
    def rtp_stat_service(self, _: str) -> None:
        pass

    @property
    def serial(self) -> str:
        """Serial number from ``show_system``, or "NA"."""
        if self._serial is not None:
            return self._serial
        if not self.show_system:
            return "NA"
        m = re.search(r"Serial No\s+:\s+(\S+)", self.show_system)
        result = m.group(1) if m else ""
        self._serial = result
        return result

    @property
    def slamon_service(self) -> str:
        """SLA Monitor admin state from ``show_sla_monitor``, or "NA"."""
        if self._slamon_service is not None:
            return self._slamon_service
        if not self.show_sla_monitor:
            return "NA"
        m = re.search(r"SLA Monitor:\s+(\S+)", self.show_sla_monitor)
        result = m.group(1).lower() if m else ""
        self._slamon_service = result
        return result

    @property
    def sla_server(self) -> str:
        """Registered SLA monitor server IP, or "NA"."""
        if self._sla_server is not None:
            return self._sla_server
        if not self.show_sla_monitor:
            return "NA"
        m = re.search(
            r"Registered Server IP Address:\s+(\S+)",
            self.show_sla_monitor,
        )
        result = m.group(1) if m else ""
        self._sla_server = result
        return result

    @property
    def snmp(self) -> str:
        """Configured SNMP versions: 'v2', 'v3', 'v2&3', '' or 'NA'."""
        if self._snmp is not None:
            return self._snmp
        if not self.show_running_config:
            return "NA"

        versions = []  # type: list
        if "snmp-server community read-only" in self.show_running_config:
            versions.append("2")
        if "encrypted-snmp-server user" in self.show_running_config:
            versions.append("3")

        self._snmp = "v" + "&".join(versions) if versions else ""
        return self._snmp

    @property
    def snmp_trap(self) -> str:
        """SNMP trap configuration ('enabled'/'disabled') or 'NA'."""
        if self._snmp_trap is not None:
            return self._snmp_trap
        if not self.show_running_config:
            return "NA"
        m = re.search(r"snmp-server host (\S+) trap", self.show_running_config)
        self._snmp_trap = "enabled" if m else "disabled"
        return self._snmp_trap

    @property
    def temp(self) -> str:
        """Ambient temperature as '<cur>/<max>' from ``show_temp``, or "NA"."""
        if self._temp is not None:
            return self._temp
        if not self.show_temp:
            return "NA"
        m = re.search(r"Temperature\s+:\s+(\S+) \((\S+)\)", self.show_temp)
        self._temp = "{}/{}".format(m.group(1), m.group(2)) if m else ""
        return self._temp

    @property
    def total_sessions(self) -> str:
        """Total Session value from RTP-Stat summary, or "NA"."""
        if not self.show_rtp_stat_summary:
            return "NA"
        m = re.search(r"nal\s+\S+\s+\S+\s+(\S+)", self.show_rtp_stat_summary)
        return m.group(1) if m else ""

    @property
    def upload_status(self) -> str:
        """Derived upload status from ``show_upload_status_10``."""
        if not self.show_upload_status_10:
            return ""

        m = re.search(r"Running state\s+:\s+(\S+)", self.show_upload_status_10)
        status = m.group(1).lower() if m else ""

        m = re.search(
            r"Failure display\s+:\s+(\S+)",
            self.show_upload_status_10,
        )
        failure = m.group(1).lower() if m else ""

        if status == "executing":
            return status
        if failure and failure != "(null)":
            return "failed"
        return status

    @property
    def uptime(self) -> str:
        """Gateway uptime as a compact string (e.g. '3d12h4m55s'), or "NA"."""
        if self._uptime is not None:
            return self._uptime
        if not self.show_system:
            return "NA"

        m = re.search(r"Uptime \(\S+\)\s+:\s+(\S+)", self.show_system)
        if m:
            result = (
                m.group(1)
                .replace(",", "d")
                .replace(":", "h", 1)
                .replace(":", "m")
                + "s"
            )
        else:
            result = ""
        self._uptime = result
        return result 

    @property
    def inuse_dsp(self) -> str:
        """Total in-use DSP count from ``show_voip_dsp``."""
        inuse = 0
        dsps = re.findall(r"In Use\s+:\s+(\d+)", self.show_voip_dsp or "")
        for dsp in dsps:
            try:
                inuse += int(dsp)
            except Exception:
                pass
        return str(inuse)

    # ------------------- Update / helpers -------------------

    def update(
        self,
        gw_name: Optional[str] = None,
        gw_number: Optional[str] = None,
        last_session_id: Optional[str] = None,
        last_seen: Optional[str] = None,
        commands: Optional[Dict[str, str]] = None,
        **kwargs: Any
    ) -> None:
        """Update BGW identity and attach command outputs.

        Args:
            gw_name: Gateway name (optional).
            gw_number: Gateway number (optional).
            last_session_id: Last RTP session id (optional).
            last_seen: Timestamp in the format ``"%Y-%m-%d,%H:%M:%S"``.
            commands: Mapping of command string -> output text.
            **kwargs: Reserved for future extension.
        """
        if gw_name is not None:
            self.gw_name = gw_name
        if gw_number is not None:
            self.gw_number = gw_number
        if last_session_id is not None:
            self.last_session_id = last_session_id
        if last_seen is not None:
            self.last_seen = last_seen

        if last_seen:
            last_seen_dt = datetime.strptime(last_seen, "%Y-%m-%d,%H:%M:%S")

            if self.last_seen_dt is not None:
                delta_s = (last_seen_dt - self.last_seen_dt).total_seconds()
                self.poll_count += 1
                self.avg_poll_secs = round(
                    ((self.avg_poll_secs * (self.poll_count - 1)) + delta_s)
                    / float(self.poll_count),
                    1,
                )
            else:
                self.poll_count = 1
                self.avg_poll_secs = float(self.polling_secs)

            self.last_seen_dt = last_seen_dt
            self.polls += 1

        if commands:
            for cmd, value in commands.items():
                bgw_attr = cmd.replace(" ", "_").replace("-", "_")
                try:
                    setattr(self, bgw_attr, value)
                except Exception as e:
                    logger.error(f"{e} while setting {bgw_attr}")

                if cmd == "show capture":
                    # Keep your state machine behavior
                    self.packet_capture = self.capture_status

                if cmd == "show upload status 10":
                    self.pcap_upload = self.upload_status
                    if self.upload_status == "executing":
                        try:
                            self.queue.put_nowait("show upload status 10")
                        except Exception:
                            pass

        _ = kwargs

    def _port_groupdict(self, idx: int) -> Dict[str, str]:
        """Extract port details from ``show_port``.

        Args:
            idx: 0 for port1, 1 for port2.

        Returns:
            Dict with keys: port/name/status/vlan/level/neg/duplex/speed.
            Returns {} if parsing fails or ``show_port`` missing.
        """
        if not self.show_port:
            return {}

        matches = re.findall(r"(.*Avaya )", self.show_port)
        if not matches:
            return {}

        line = matches[idx] if idx < len(matches) else ""
        if not line:
            return {}

        m = re.search(
            r".*?(?P<port>\d+/\d+)"
            r".*?(?P<name>.*)"
            r".*?(?P<status>(connected|no link|disabled))"
            r".*?(?P<vlan>\d+)"
            r".*?(?P<level>\d+)"
            r".*?(?P<neg>\S+)"
            r".*?(?P<duplex>\S+)"
            r".*?(?P<speed>\S+)",
            line,
        )
        return m.groupdict() if m else {}

    def properties_asdict(self) -> Dict[str, Any]:
        """Return all @property values as a dict."""
        properties = {}  # type: Dict[str, Any]
        for name in dir(self.__class__):
            obj = getattr(self.__class__, name)
            if isinstance(obj, property):
                properties[name] = obj.__get__(self, self.__class__)
        return properties

    def asdict(self) -> Dict[str, Any]:
        """Return properties + instance attributes as a dict."""
        attrs = dict(self.__dict__)
        return dict(self.properties_asdict(), **attrs)

    @staticmethod
    def _to_mbyte(mem_str: str) -> int:
        """Convert a memory token like '256MB' or '1GB' to MB (int)."""
        m = re.search(r"(\d+)([MG]B)", mem_str or "")
        if not m:
            return 0
        num = int(m.group(1))
        unit = m.group(2)
        if unit == "MB":
            return num
        if unit == "GB":
            return 1024 * num
        return 0

    def __repr__(self) -> str:
        return "BGW({})".format(self.__dict__)

############################## END BGW ########################################
############################## BEGIN RTPPARSER ################################

RTP_DETAILS = (
    r".*?Session-ID: (?P<session_id>\d+)",
    r".*?Status: (?P<status>\S+),",
    r".*?QOS: (?P<qos>\S+),",
    r".*?EngineId: (?P<engineid>\d+)",
    r".*?Start-Time: (?P<start_time>\S+),",
    r".*?End-Time: (?P<end_time>\S+)",
    r".*?Duration: (?P<duration>\S+)",
    r".*?CName: (?P<cname>\S+)",
    r".*?Phone: (?P<phone>.*?)\s+",
    r".*?Local-Address: (?P<local_addr>\S+):",
    r".*?(?P<local_port>\d+)",
    r".*?SSRC (?P<local_ssrc>\d+)",
    r".*?Remote-Address: (?P<remote_addr>\S+):",
    r".*?(?P<remote_port>\d+)",
    r".*?SSRC (?P<remote_ssrc>\d+)",
    r".*?(?P<remote_ssrc_change>\S+)",
    r".*?Samples: (?P<samples>\d+)",
    r".*?(?P<sampling_interval>\(.*?\))",
    r".*?Codec:\s+(?P<codec>\S+)",
    r".*?(?P<codec_psize>\S+)",
    r".*?(?P<codec_ptime>\S+)",
    r".*?(?P<codec_enc>\S+),",
    r".*?Silence-suppression\(Tx/Rx\) (?P<codec_silence_suppr_tx>\S+)/",
    r".*?(?P<codec_silence_suppr_rx>\S+),",
    r".*?Play-Time (?P<codec_play_time>\S+),",
    r".*?Loss (?P<codec_loss>\S+)",
    r".*?#(?P<codec_loss_events>\d+),",
    r".*?Avg-Loss (?P<codec_avg_loss>\S+),",
    r".*?RTT (?P<codec_rtt>\S+)",
    r".*?#(?P<codec_rtt_events>\d+),",
    r".*?Avg-RTT (?P<codec_avg_rtt>\S+),",
    r".*?JBuf-under/overruns (?P<codec_jbuf_underruns>\S+)/",
    r".*?(?P<codec_jbuf_overruns>\S+),",
    r".*?Jbuf-Delay (?P<codec_jbuf_delay>\S+),",
    r".*?Max-Jbuf-Delay (?P<codec_max_jbuf_delay>\S+)",
    r".*?Packets (?P<rx_rtp_packets>\d+),",
    r".*?Loss (?P<rx_rtp_loss>\S+)",
    r".*?#(?P<rx_rtp_loss_events>\d+),",
    r".*?Avg-Loss (?P<rx_rtp_avg_loss>\S+),",
    r".*?RTT (?P<rx_rtp_rtt>\S+)",
    r".*?#(?P<rx_rtp_rtt_events>\d+),",
    r".*?Avg-RTT (?P<rx_rtp_avg_rtt>\S+),",
    r".*?Jitter (?P<rx_rtp_jitter>\S+)",
    r".*?#(?P<rx_rtp_jitter_events>\d+),",
    r".*?Avg-Jitter (?P<rx_rtp_avg_jitter>\S+),",
    r".*?TTL\(last/min/max\) (?P<rx_rtp_ttl_last>\d+)/",
    r".*?(?P<rx_rtp_ttl_min>\d+)/",
    r".*?(?P<rx_rtp_ttl_max>\d+),",
    r".*?Duplicates (?P<rx_rtp_duplicates>\d+),",
    r".*?Seq-Fall (?P<rx_rtp_seqfall>\d+),",
    r".*?DSCP (?P<rx_rtp_dscp>\d+),",
    r".*?L2Pri (?P<rx_rtp_l2pri>\d+),",
    r".*?RTCP (?P<rx_rtp_rtcp>\d+),",
    r".*?Flow-Label (?P<rx_rtp_flow_label>\d+)",
    r".*?VLAN (?P<tx_rtp_vlan>\d+),",
    r".*?DSCP (?P<tx_rtp_dscp>\d+),",
    r".*?L2Pri (?P<tx_rtp_l2pri>\d+),",
    r".*?RTCP (?P<tx_rtp_rtcp>\d+),",
    r".*?Flow-Label (?P<tx_rtp_flow_label>\d+)",
    r".*?Loss (?P<rem_loss>\S+)",
    r".*#(?P<rem_loss_events>\S+),",
    r".*?Avg-Loss (?P<rem_avg_loss>\S+),",
    r".*?Jitter (?P<rem_jitter>\S+)",
    r".*?#(?P<rem_jitter_events>\S+),",
    r".*?Avg-Jitter (?P<rem_avg_jitter>\S+)",
    r".*?Loss (?P<ec_loss>\S+)",
    r".*?#(?P<ec_loss_events>\S+),",
    r".*?Len (?P<ec_len>\S+)",
    r".*?Status (?P<rsvp_status>\S+),",
    r".*?Failures (?P<rsvp_failures>\d+)",
)

reRTPDetails = re.compile(r"".join(RTP_DETAILS), re.M | re.S | re.I)

class RTPDetails(object):
    """
    RTP session details parsed from BGW RTP-Stat output.

    This class is intentionally permissive: it defines a common baseline set of
    attributes, then applies any extra keyword parameters via setattr(). This
    makes it resilient to schema changes (new fields appearing in parsed data).

    Attributes:
        gw_number: Gateway number / identifier.
        global_id: Global RTP session identifier.
        session_id: Session identifier (often numeric, stored as string).
        qos: QoS status string (e.g. "ok", "bad").
        rx_rtp_packets: Number of received RTP packets (string form).
        status: Session status string (e.g. "Active", "Terminated").
        local_ssrc: Local SSRC (string form, typically integer).
        remote_ssrc: Remote SSRC (string form, typically integer).
        start_time: Session start timestamp as "YYYY-mm-dd,HH:MM:SS".
        end_time: Session end timestamp as "YYYY-mm-dd,HH:MM:SS" or "-".
    """

    def __init__(self, **params: Any) -> None:
        """
        Initialize RTPDetails.

        Args:
            **params:
                Arbitrary RTP fields. Known keys overwrite the defaults.
                Unknown keys are accepted and stored as attributes.
        """
        self.gw_number = ""           # type: str
        self.global_id = ""           # type: str
        self.session_id = ""          # type: str
        self.qos = "ok"               # type: str
        self.rx_rtp_packets = "0"     # type: str
        self.status = ""              # type: str
        self.local_ssrc = ""          # type: str
        self.remote_ssrc = ""         # type: str
        self.start_time = ""          # type: str
        self.end_time = ""            # type: str

        for k, v in params.items():
            setattr(self, k, v)

    @property
    def nok(self) -> str:
        """
        Return a simple issue marker for the session.

        Returns:
            "None": QoS is ok and RX packet count > 0
            "Zero": RX packet count == 0
            "QoS":  QoS is not ok (or RX packet parsing fails and QoS not ok)
        """
        rx = self._safe_int(self.rx_rtp_packets)
        if self.qos.lower() == "ok" and rx is not None and rx > 0:
            return "None"
        if rx == 0:
            return "Zero"
        return "QoS"

    @property
    def is_active(self) -> bool:
        """
        Whether the RTP session is currently active.

        Note:
            Despite the old comment in your code, the logic here treats any
            status other than "Terminated" as active.

        Returns:
            True if status != "Terminated", otherwise False.
        """
        return self.status != "Terminated"

    @property
    def local_ssrc_hex(self) -> str:
        """
        Local SSRC as a hexadecimal string.

        Returns:
            Hex string like "0x1a2b3c4d", or "" if conversion fails.
        """
        return self._safe_hex(self.local_ssrc)

    @property
    def remote_ssrc_hex(self) -> str:
        """
        Remote SSRC as a hexadecimal string.

        Returns:
            Hex string like "0x1a2b3c4d", or "" if conversion fails.
        """
        return self._safe_hex(self.remote_ssrc)

    @property
    def start_datetime(self) -> Optional[datetime]:
        """
        Parse start_time into a datetime.

        Returns:
            datetime if start_time is present and parseable, else None.
        """
        return self._parse_ts(self.start_time)

    @property
    def end_datetime(self) -> Optional[datetime]:
        """
        Parse end_time into a datetime.

        Returns:
            datetime if end_time is present, not "-", and parseable, else None.
        """
        if not self.end_time or self.end_time == "-":
            return None
        return self._parse_ts(self.end_time)

    @property
    def duration_secs(self) -> Optional[int]:
        """
        Session duration in seconds.

        If end_time is missing or "-", duration is computed up to "now".

        Returns:
            Duration in seconds, or None if start time is unavailable.
        """
        start = self.start_datetime
        if start is None:
            return None

        end = self.end_datetime
        if end is None:
            return int((datetime.now() - start).total_seconds())
        return int((end - start).total_seconds())

    def asdict(self) -> Dict[str, Any]:
        """
        Return a shallow dict of all attributes stored on this instance.

        Returns:
            Dict mapping attribute name to value.
        """
        return self.__dict__

    def __repr__(self) -> str:
        """Debug representation."""
        return "RTPDetails({})".format(self.__dict__)

    def __str__(self) -> str:
        """Human-readable representation (currently same as dict view)."""
        return str(self.__dict__)

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        """Convert value to int, returning None on failure."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_hex(value: Any) -> str:
        """Convert value to hex(int(value)), returning "" on failure."""
        try:
            return hex(int(value))
        except (TypeError, ValueError):
            return ""

    @staticmethod
    def _parse_ts(ts: Any) -> Optional[datetime]:
        """Parse BGW timestamp format 'YYYY-mm-dd,HH:MM:SS'."""
        if not ts:
            return None
        try:
            return datetime.strptime(str(ts), "%Y-%m-%d,%H:%M:%S")
        except (TypeError, ValueError):
            return None

def parse_rtpstat(global_id, rtpstat):
    """
    Returns RTPDetails instance with RTP stat attributes.
    """
    gw_number, session_id = global_id.split(",")[2:]

    try:
        m = reRTPDetails.search(rtpstat)
        if m:
            d = m.groupdict()
            d["gw_number"] = gw_number
            d["global_id"] = global_id
            rtpdetails = RTPDetails(**d)
        else:
            logger.error(f"Unable to parse {session_id} from BGW {gw_number}")
            logger.debug(repr(rtpstat))
            rtpdetails = None

    except Exception as e:
        logger.error(f"Error {e.__class__.__name__} with session {session_id}")
        return None

    return rtpdetails

############################## END RTPPARSER ##################################
############################## BEGIN AHTTP ####################################

"""
Async HTTP server that receives file uploads via PUT/POST requests.
Compatible with Python 3.6+

Examples:
    curl -T mg.pcap http://10.10.10.1:8080/mg.pcap
    curl -X PUT --data-binary @mg.pcap http://10.10.10.1:8080/mg.pcap
    wget --method=PUT --body-file=gwcapture.pcap http://10.10.10.1:8080/mg.pcap
"""

class FileUploadProtocol(asyncio.Protocol):
    def __init__(self, upload_dir, upload_queue):
        self.upload_dir = upload_dir
        self.upload_queue = upload_queue if upload_queue else Queue()
        self.transport = None
        self.buffer = b""
        self.headers = {}
        self.method = None
        self.path = None
        self.content_length = 0
        self.headers_complete = False
        self.body = b""

    def connection_made(self, transport):
        self.transport = transport
        peername = transport.get_extra_info("peername")
        logger.info(f"Connection from {peername[0]}:{peername[1]}")
        
        if peername:
            self.remote_ip = peername[0]
        else:
            self.remote_ip = None

    def data_received(self, data):
        self.buffer += data

        if not self.headers_complete:
            # Check if we have complete headers
            if b"\r\n\r\n" in self.buffer:
                header_end = self.buffer.index(b"\r\n\r\n")
                header_data = self.buffer[:header_end].decode(
                    "utf-8", errors="ignore"
                )
                self.body = self.buffer[header_end + 4 :]
                self.headers_complete = True

                # Parse request line and headers
                lines = header_data.split("\r\n")
                request_line = lines[0].split()

                if len(request_line) >= 2:
                    self.method = request_line[0]
                    self.path = unquote(request_line[1])

                # Parse headers
                for line in lines[1:]:
                    if ":" in line:
                        key, value = line.split(":", 1)
                        self.headers[key.strip().lower()] = value.strip()

                self.content_length = int(
                    self.headers.get("content-length", 0)
                )
        else:
            # Accumulate body data
            self.body += data

        # Check if we have complete body
        if self.headers_complete and len(self.body) >= self.content_length:
            self.handle_request()

    def handle_request(self):
        if self.method in ["PUT", "POST"]:
            self.handle_upload()
        else:
            self.send_response(
                405,
                "Method Not Allowed",
                "Only PUT and POST methods are supported",
            )

    def handle_upload(self):
        # Extract filename from path
        if not self.path:
            self.send_response(400, "Bad Request", "Filename missing")
            return

        filename = os.path.basename(self.path.lstrip("/"))

        if not filename:
            self.send_response(
                400, "Bad Request", "Filename must be specified in URL path"
            )
            return

        # Sanitize filename
        filename = filename.replace("..", "").replace("/", "").replace("\\", "")

        if not filename:
            self.send_response(400, "Bad Request", "Invalid filename")
            return

        # Save file
        filepath = os.path.join(self.upload_dir, filename)

        try:
            with open(filepath, "wb") as f:
                f.write(self.body[: self.content_length])

            file_size = len(self.body[: self.content_length])
            logger.info(f"Received {filename} ({file_size} bytes) via HTTP")

            item = {
                "remote_ip": self.remote_ip,
                "filename": filename,
                "file_size": file_size,
                "received_timestamp": datetime.now()
            }

            self.upload_queue.put_nowait(item)
            logger.info(f"Put {item} in upload_queue")

            self.send_response(
                201,
                "Created",
                f"File {filename} uploaded successfully "
                f"({file_size} bytes)",
            )
        except Exception as e:
            logger.error(f"Error saving {filename}: {e}")
            self.send_response(
                500, "Internal Server Error", f"Error saving file: {str(e)}"
            )

    def send_response(self, status_code, status_text, message):
        response_body = f"{message}\n".encode("utf-8")
        response = (
            f"HTTP/1.1 {status_code} {status_text}\r\n"
            f"Content-Type: text/plain\r\n"
            f"Content-Length: {len(response_body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        ).encode("utf-8") + response_body

        if self.transport:
            self.transport.write(response)
            self.transport.close()

    def connection_lost(self, exc):
        logger.info(f"Connection lost {exc}")
        pass

async def start_http_server(host, port, upload_dir, upload_queue):
    loop = asyncio.get_event_loop()

    try:
        os.makedirs(upload_dir, exist_ok=True)
    except Exception as e:
        logger.error(f"{e} while creating {upload_dir}")
    
    try:
        server = await loop.create_server(
            lambda: FileUploadProtocol(upload_dir, upload_queue), host, port
        )
    except Exception as e:
        logger.error(f"Failed to start HTTP server on {host}:{port}: {e}")
        return

    logger.info(f"HTTP server started on http://{host}:{port}")
    logger.info(f"Upload directory: {os.path.abspath(upload_dir)}")

    try:
        # wait forever
        await asyncio.Event().wait()

    except asyncio.CancelledError:
        logger.info("HTTP server task cancelled")
        raise

    finally:
        server.close()
        await server.wait_closed()
        logger.info("HTTP server closed")

############################## END AHTTP ######################################
############################## BEGIN ALOOP ####################################

TASKs = set()
BGWMap = Mapping[str, Any]
Progress = Tuple[int, int, int]
ProgressCallback = Callable[[Progress], None]

class CommandResult:
    """A consistent container for command output."""

    stdout: str
    stderr: str
    returncode: Optional[int]
    error_type: Optional[str]
    name: Optional[str]

    def __init__(
        self,
        stdout: str,
        stderr: str,
        returncode: Optional[int],
        error_type: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        """
        Initializes the CommandResult object.
        """
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.error_type = error_type
        self.name = name

    def __repr__(self) -> str:
        """
        Provides a string representation for debugging and printing
        """
        fields = [
            f"name={repr(self.name)}",
            f"stdout={repr(self.stdout)}",
            f"stderr={repr(self.stderr)}",
            f"returncode={self.returncode}",
        ]
        if self.error_type is not None:
            fields.append(f"error_type={repr(self.error_type)}")

        return f"CommandResult({', '.join(fields)})"

class Capture:
    """A consistent container for command output."""

    remote_ip: str
    filename: str
    file_size: int
    received_timestamp: datetime
    capinfos: str
    rtpinfos: str
    gw_number: str

    def __init__(
        self,
        remote_ip: str,
        filename: str,
        file_size: int,
        received_timestamp: datetime,
        capinfos: str = "",
        rtpinfos: str = "",
        gw_number: str = ""
    ) -> None:
        """
        Initializes the Capture object.
        """
        self.remote_ip = remote_ip
        self.filename = filename
        self.file_size = file_size
        self.received_timestamp = received_timestamp
        self.capinfos = capinfos
        self.rtpinfos = rtpinfos
        self.gw_number = gw_number

        self._first_packet_time = None
        self._last_packet_time = None
        self._rtp_streams = None
        self._rtp_problems = None

    @property
    def received_timestamp_str(self):
        return self.received_timestamp.strftime("%Y-%m-%d,%H:%M:%S")

    @property
    def first_packet_time(self):
        if self._first_packet_time:
            return self._first_packet_time
        
        if not self.capinfos:
            return ""
        
        m = re.search(r"First packet time:\s+(.*?)\.", self.capinfos)
        self._first_packet_time = m.group(1) if m else ""
        return self._first_packet_time 
            
    @property
    def last_packet_time(self):
        if self._last_packet_time:
            return self._last_packet_time
        
        if not self.capinfos:
            return ""
        
        m = re.search(r"Last packet time:\s+(.*?)\.", self.capinfos)
        self._last_packet_time = m.group(1) if m else ""
        return self._last_packet_time

    @property
    def rtp_problems(self):
        if self._rtp_problems:
            return self._rtp_problems
        
        if not self.rtpinfos:
            return 0
        
        lines = self.rtpinfos.splitlines()
        problems = sum(1 for x in lines if x.strip().endswith("X"))
        self._rtp_problems = problems
        
        return self._rtp_problems

    @property
    def rtp_streams(self):
        if self._rtp_streams:
            return self._rtp_streams
        
        if not self.rtpinfos:
            return ""
        
        rtps = sum(1 for x in self.rtpinfos.splitlines() if "0x" in x)
        self._rtp_streams = rtps
        
        return self._rtp_streams

    def __repr__(self) -> str:
        """
        Provides a string representation for debugging and printing
        """
        fields = [
            f"remote_ip={repr(self.remote_ip)}",
            f"filename={repr(self.filename)}",
            f"file_size={repr(self.file_size)}",
            f"received_timestamp={repr(self.received_timestamp)}",
            f"capinfos={repr(self.capinfos)}",
            f"rtpinfos={repr(self.rtpinfos)}",
            f"gw_number={repr(self.gw_number)}"
        ]

        return f"Capture({', '.join(fields)})"

def create_bgw_script(
    bgw: "BGW",
    script_template: str = EXPECT_SCRIPT,
) -> str:
    """
    Generate an Expect script for querying a BGW.

    The generated script depends on whether the BGW has been seen before:
    - If this is the first discovery, discovery commands are used and RTP
      statistics are disabled.
    - If the BGW has been seen previously, query commands are used and RTP
      statistics are enabled.
    - Any queued commands are prepended to the command list.

    Args:
        bgw: The BGW instance to generate the script for.
        script_template: The Expect script template to format.

    Returns:
        A fully formatted Expect script as a string.
    """
    debug: int = 1 if logger.getEffectiveLevel() == 10 else 0

    if not bgw.last_seen:
        # Initial discovery
        rtp_stats: int = 0
        commands: List[str] = CONFIG["discovery_commands"][:]
        prev_last_session_id: str = ""
        prev_active_session_ids: Iterable[str] = []

    else:
        # Regular polling
        rtp_stats = 1
        prev_last_session_id = bgw.last_session_id or ""
        prev_active_session_ids = sorted(bgw.active_session_ids)
        commands = CONFIG["query_commands"][:]

        if not bgw.queue.empty():
            queued_commands = bgw.queue.get_nowait()
            if isinstance(queued_commands, str):
                queued_commands = [queued_commands]

            commands = list(queued_commands) + commands
            logger.info(
                "Queued commands: '%s' - %s",
                queued_commands,
                bgw.lan_ip,
            )

    template_args = {
        "lan_ip": bgw.lan_ip,
        "user": CONFIG["user"],
        "passwd": CONFIG["passwd"],
        "prev_last_session_id": f'"{prev_last_session_id}"',
        "prev_active_session_ids": "{"
        + " ".join(f'"{sid}"' for sid in prev_active_session_ids)
        + "}",
        "rtp_stats": rtp_stats,
        "commands": "{"
        + " ".join(f'"{cmd}"' for cmd in commands)
        + "}",
        "debug": debug,
    }

    logger.debug(
        "Template variables %s - %s",
        template_args,
        bgw.lan_ip,
    )

    return script_template.format(**template_args)

def connected_gws(
    ip_filter: Optional[Iterable[str]] = None
) -> Dict[str, str]:
    """Return a dictionary of connected G4xx media-gateways

    Args:
        ip_filter: IP addresses of BGWs to discover.

    Returns:
        Dict: A dictionary of connected gateways.
    """
    result: Dict[str, str] = {}
    ip_filter = set(ip_filter) if ip_filter else set()

    ports = "1039|2944|2945|61440|61441|61442|61443|61444"
    command = "netstat -tan | grep ESTABLISHED | grep -E '{}'".format(ports)
    pattern = r"([0-9.]+):(1039|2944|2945|6144[0-4])\s+([0-9.]+):([0-9]+)"
    protocols = {
        "1039": "ptls",
        "2944": "tls",
        "2945": "unenc",
        "61440": "h323",
        "61441": "h323",
        "61442": "h323",
        "61443": "h323",
        "61444": "h323",
    }

    connections = os.popen(command).read()

    for m in re.finditer(pattern, connections):
        ip, port = m.group(3, 2)

        proto = protocols.get(port, "unknown")
        logger.debug(f"Found GW using {proto} - {ip}")

        if not ip_filter or ip in ip_filter:
            result[ip] = proto
            logger.info(f"Added GW to results - {ip}")

    result = {ip: result[ip] for ip in sorted(result)}
    return result if result else {ip: "unknown" for ip in ip_filter}

async def _run_cmd(
    program: str,
    args: List[str],
    name: Optional[str] = None,
) -> Tuple[str, str, Optional[int]]:
    """
    Execute an external command asynchronously and capture output.

    This is a small wrapper around `asyncio.create_subprocess_exec()` that
    returns decoded stdout/stderr and the process return code.

    Cancellation handling:
        - If the coroutine is cancelled while the subprocess is still running,
          the subprocess is killed and waited for.

    Python 3.6 note:
        - Some environments can leave transports open longer than desired; the
          `finally` block includes a defensive transport close workaround.

    Args:
        program: Executable name/path.
        args: Argument vector (without the program itself).
        name: Optional label used in logs to identify the caller/context.

    Returns:
        A tuple of (stdout_text, stderr_text, returncode). The return code is
        typically an int; it may be None only in unusual edge cases.

    Raises:
        OSError / FileNotFoundError: If the program cannot be executed.
        asyncio.CancelledError: If the coroutine is cancelled.
        Exception: Propagates unexpected failures from subprocess execution.
    """
    proc: Optional[asyncio.subprocess.Process] = None

    try:
        proc = await asyncio.create_subprocess_exec(
            program,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.debug("Created PID %s - %s", proc.pid, name)

        stdout_bytes, stderr_bytes = await proc.communicate()

        stdout_text = stdout_bytes.decode(errors="replace").strip()
        stderr_text = stderr_bytes.decode(errors="replace").strip()
        return stdout_text, stderr_text, proc.returncode

    except asyncio.CancelledError:
        if proc is not None and proc.returncode is None:
            logger.debug("Killing PID %s - %s", proc.pid, name)
            try:
                proc.kill()
                await proc.wait()
            except Exception as e2:
                logger.error("Cleanup %s - %s", e2.__class__.__name__, name)
        raise

    except Exception as e:
        # Keep your original behavior: log a short message and re-raise.
        logger.error("%s - %s", e.__class__.__name__, name)
        raise

    finally:
        # WORKAROUND FOR PYTHON 3.6:
        # Some 3.6/older asyncio implementations can keep transports open.
        if proc is not None and hasattr(proc, "_transport"):  # type: ignore
            transport = getattr(proc, "_transport", None)  # type: ignore
            if transport:
                try:
                    transport.close()
                    setattr(proc, "_transport", None)  # type: ignore
                except Exception:
                    pass

async def run_cmd(
    program: str,
    args: List[str],
    timeout: float = 10.0,
    name: Optional[str] = None,
) -> CommandResult:
    """
    Run an external command asynchronously with a timeout and return a
    structured result.

    This coroutine wraps `_run_cmd()` and adds:
      - Timeout handling via `asyncio.wait_for`
      - Consistent logging
      - Conversion of failures into a `CommandResult` instance

    Args:
        program: Executable name or path.
        args: Argument vector (excluding the program itself).
        timeout: Maximum execution time in seconds before the command is
            cancelled.
        name: Optional label used for logging and propagated into the
            returned `CommandResult`.

    Returns:
        CommandResult:
            - stdout: Captured standard output (string).
            - stderr: Captured standard error (string).
            - returncode: Process return code, or None on failure/timeout.
            - name: The optional command name.
            - error_type: Set when an error or timeout occurred.

    Raises:
        asyncio.CancelledError:
            Propagated if the coroutine itself is cancelled.
    """
    try:
        logger.info("Starting '%s' - %s", program, name)

        stdout, stderr, returncode = await asyncio.wait_for(
            _run_cmd(program, args, name),
            timeout=timeout,
        )

        logger.info(
            "Completed '%s' with rc %s - %s",
            program,
            returncode,
            name,
        )

        return CommandResult(
            stdout,
            stderr,
            returncode=returncode,
            name=name,
        )

    except asyncio.TimeoutError:
        logger.error(
            "TimeoutError after %.1f secs - %s",
            timeout,
            name,
        )
        return CommandResult(
            "",
            "",
            returncode=None,
            error_type="Timeout",
            name=name,
        )

    except asyncio.CancelledError:
        # Let task cancellation propagate normally
        raise

    except Exception as e:
        error_name = e.__class__.__name__
        error_msg = f"{error_name} - {name}"

        logger.error("%s", error_msg)

        return CommandResult(
            "",
            "",
            returncode=None,
            error_type=error_msg,
            name=name,
        )

async def process_queue(
    queue: "asyncio.Queue[Any]",
    storage: "AbstractRepository[str, RTPDetails]",
    callback: Optional[Callable[[], None]] = None,
    nok_rtp_only: bool = False
) -> None:
    """Continuously consume items from an asyncio queue and process them.

    This coroutine blocks on ``queue.get()`` and forwards each received item to
    ``process_item(...)`` to update BGW state and the RTP session storage.

    Args:
        queue: An asyncio queue yielding items to be processed (often a
            subprocess result / message containing JSON in ``item.stdout``).
        storage: Mutable mapping that will be updated by ``process_item``.
            Typically a ``MemoryStorage[str, RTPDetails]`` or similar.
        callback: Optional callable invoked by ``process_item`` after updates.

    Returns:
        None.
    """
    while True:
        item = await queue.get()
        try:
            logger.debug("Got item from process queue: %r", item)
            process_item(
                item,
                storage=storage,
                callback=callback,
                nok_rtp_only=nok_rtp_only
            )
        finally:
            try:
                queue.task_done()
            except Exception:
                pass

def process_item(
    item: Any,
    bgw: Optional["BGW"] = None,
    storage: "AbstractRepository[str, RTPDetails]" = RTPs,
    callback: Optional[Callable[[], None]] = None,
    nok_rtp_only: bool = False
) -> None:
    """Process a single queue item and update BGW + RTP session storage.

    Expects ``item.stdout`` to contain a JSON string with (at least) gateway
    identifiers and optionally a session map.

    Expected JSON keys (commonly used):
        - gw_number: str
        - lan_ip: str
        - rtp_sessions: mapping[str, Any] where values are per-session payloads
        - plus any keys accepted by ``BGW.update(**data)``

    Side effects:
        - Updates global gateway index ``GWs`` (lan_ip -> gw_number)
        - Updates BGW via ``bgw.update(**data)``
        - Parses RTP sessions and writes to ``storage[global_id]``
        - Updates ``bgw.active_session_ids``
        - Persists BGW back into ``BGWs[gw_number]``
        - Calls ``callback()`` if provided

    Args:
        item: An object with a ``stdout`` attribute containing JSON text.
        bgw: The BGW instance to update. If None, it's looked up in ``BGWs``.
        storage: Mapping to receive parsed RTPDetails by global session id.
            Typically your ``RTPs`` MemoryStorage.
        callback: Optional callable invoked after processing.
        nok_rtp_only: If True, only sessions considered "NOK" are stored
            (based on the logic below). Active sessions are tracked separately.

    Returns:
        None.
    """
    try:
        data = json.loads(getattr(item, "stdout", ""), strict=False)
    except json.JSONDecodeError:
        logger.error("JSONDecodeError: %r", item)
        return

    if not isinstance(data, dict):
        logger.debug("Unexpected JSON type %r in %r", type(data), item)
        return

    gw_number = data.get("gw_number")
    lan_ip = data.get("lan_ip")

    if not gw_number and not lan_ip:
        logger.debug("Unexpected data in %r", item)
        return

    if bgw is None:
        bgw = BGWs.get(gw_number)
        if not bgw:
            return

    # Keep a lan_ip -> gw_number index for quick reverse lookup.
    if lan_ip and lan_ip not in GWs:
        GWs.update({lan_ip: gw_number})
        logger.info("Updated GWs with %s -> %s", lan_ip, gw_number)

    active_session_ids: Set[str] = set()

    bgw.update(**data)
    logger.debug(
        "Updated BGW %s with data (%s) - %s", gw_number, len(data), lan_ip
    )

    rtp_sessions = data.get("rtp_sessions", {})  # type: Any
    if isinstance(rtp_sessions, dict):
        for global_id, rtpstat in rtp_sessions.items():
            rtpdetails = parse_rtpstat(global_id, rtpstat)
            if rtpdetails is None:
                continue

            session_id = "{:0>5}".format(rtpdetails.session_id)

            if rtpdetails.is_active:
                active_session_ids.add(session_id)
                # If nok_rtp_only is True wait for the session to complete
                if nok_rtp_only:
                    continue

            if nok_rtp_only and getattr(rtpdetails, "nok", None) == "None":
                # If nok_rtp_only is True don't store good sessions
                continue

            storage.put({global_id: rtpdetails})
            logger.info("Updated storage with %s - %s", session_id, lan_ip)
    else:
        logger.debug("rtp_sessions is not a dict (got %r)", type(rtp_sessions))

    bgw.active_session_ids = active_session_ids
    if active_session_ids:
        logger.info("%d active sessions - %s", len(active_session_ids), lan_ip)

    if gw_number:
        BGWs.put({gw_number: bgw})

    if callback:
        callback()

async def process_upload_queue(
    queue: "asyncio.Queue",
    storage: "AbstractRepository[str, Capture]",
    callback: Optional[Callable[[], None]] = None,
) -> None:
    """Continuously process items from the upload queue.

    Expected item keys:
      - "filename": str
      - "remote_ip": str

    Args:
        queue: An asyncio.Queue that yields dict-like items.
        storage: Storage passed through to process_upload_item.
        callback: Optional callable invoked by process_upload_item.

    Returns:
        None. Runs forever until cancelled.
    """
    while True:
        item = await queue.get()
        try:
            logger.info("Got %r from upload queue", item)
            filename = item.get("filename")
            remote_ip = item.get("remote_ip")

            if not filename or not isinstance(filename, str):
                logger.debug("Upload item missing/invalid filename: %r", item)
                process_upload_item(item, storage=storage, callback=callback)
                continue

            upload_dir = CONFIG.get("upload_dir", "./")
            pcapfile = os.path.join(upload_dir, filename)

            gw_number = "NA"
            if remote_ip:
                gw_number = GWs.get(remote_ip, "NA")

            if os.path.exists(pcapfile):
                try:
                    capinfos_output = await capinfos(pcapfile)
                except Exception as e:
                    logger.error("capinfos failed for %s: %s", pcapfile, e)
                    capinfos_output = f"{e}"

                try:
                    rtpinfos_output = await rtpinfos(pcapfile)
                except Exception as e:
                    logger.error("rtpinfos failed for %s: %s", pcapfile, e)
                    rtpinfos_output = f"{e}"

                item.update(
                    {
                        "capinfos": capinfos_output,
                        "rtpinfos": rtpinfos_output,
                        "gw_number": gw_number,
                    }
                )
            else:
                item.update({"gw_number": gw_number})

            process_upload_item(item, storage=storage, callback=callback)

        finally:
            try:
                queue.task_done()
            except Exception:
                pass

def process_upload_item(
    item: MutableMapping[str, Any],
    storage: "AbstractRepository[str, Capture]" = PCAPs,
    callback: Optional[Callable[[], None]] = None,
) -> None:
    """Convert an upload metadata dict into a `Capture` and store it.

    This function takes the dict produced by your upload pipeline (possibly
    enriched with `capinfos`, `rtpinfos`, and `gw_number`), instantiates a
    `Capture`, and inserts it into the capture storage keyed by filename.

    Args:
        item:
            Upload item mapping used to construct `Capture(**item)`.
        storage:
            Target capture storage. Defaults to global `PCAPs`. The object is
            expected to implement `put({key: value})`.
        callback:
            Optional callable invoked after the item is stored.
    """
    try:
        capture = Capture(**item)
    except Exception as e:
        logger.error("Capture instantiation failed for %s: %s", item, e)
        return

    storage.put({capture.filename: capture})

    logger.info("Put %s into capture storage", capture.filename)
    logger.debug("%r", capture)

    if callback is not None:
        callback()

def done_task_callback(task):
    name = task.name if hasattr(task, "name") else task._coro.__name__
    TASKs.discard(task)
    logger.debug(f"Discarded task from TASKs - {name}")

def schedule_task(
    coro: Coroutine[Any, Any, Any],
    name: Optional[str] = None,
    loop: Optional["asyncio.AbstractEventLoop"] = None,
) -> asyncio.Task:
    """Schedule a coroutine as an asyncio Task on the given event loop.

    This helper wraps `asyncio.ensure_future()` to:
      - Bind the task to a specific event loop (or the current one),
      - Assign a human-readable task name (for logging/debugging),
      - Register a completion callback,
      - Track the task in the global TASKs registry.

    Notes:
        - On Python 3.6, `asyncio.Task` does not officially expose a
          `name` attribute. Assigning `task.name` is therefore a
          best-effort, runtime-only convenience and is marked with
          `# type: ignore`.
        - The `done_task_callback` function is expected to handle cleanup
          (e.g. logging, removing the task from TASKs, error reporting).

    Args:
        coro: The coroutine object to schedule.
        name: Optional human-readable name for the task. If omitted,
            `coro.__name__` is used.
        loop: The event loop on which to schedule the task. If omitted,
            the current event loop is used.

    Returns:
        The created and scheduled asyncio.Task instance.
    """
    task_name = name if name else coro.__name__
    event_loop = loop if loop else asyncio.get_event_loop()

    task: asyncio.Task = asyncio.ensure_future(coro, loop=event_loop)
    task.name = task_name  # type: ignore[attr-defined]

    logger.debug("Scheduled '%s' as task '%s'", coro.__name__, task_name)

    task.add_done_callback(done_task_callback)
    TASKs.add(task)

    logger.debug("Added task to TASKs - %s", task_name)

    return task

async def query(
    bgw: BGW,
    semaphore: Optional[asyncio.Semaphore] = None,
    name: Optional[str] = None,
    queue: Optional[asyncio.Queue] = None,
    timeout: float = 25,
    polling_secs: float = 30,
) -> Optional[CommandResult]:

    name = name if name else bgw.lan_ip
    semaphore = semaphore if semaphore else asyncio.Semaphore(1)
    avg_sleep = 0.0
    sleep_n = 0

    while True:
        try:
            t0 = time.monotonic()
            async with semaphore:
                logger.debug(
                    f"Semaphore acquired ({semaphore._value} free) - {name}"
                )

                result = await run_cmd(
                    program="expect",
                    args=["-c", create_bgw_script(bgw)],
                    timeout=timeout,
                    name=name,
                )

                if isinstance(result, CommandResult):
                    if not queue:
                        return result
                    await queue.put(result)

            elapsed = time.monotonic() - t0
            sleep = round(max(polling_secs - elapsed, 0.0), 2)
            
            sleep_n += 1
            avg_sleep = (avg_sleep * (sleep_n - 1) + sleep) / sleep_n
            avg_sleep = round(avg_sleep, 2)
            
            logger.debug(
                f"Semaphore released ({semaphore._value} free), "
                f"Cycle elapsed {elapsed:.2f}s, sleeping {sleep:.2f}s "
                f"(avg_sleep {avg_sleep:.2f}s) - {name}"
            )

            if sleep:
                await asyncio.sleep(sleep)

        except asyncio.CancelledError:
            logger.error(f"CancelledError - {name}")
            raise

        except asyncio.TimeoutError:
            logger.error(f"TimeoutError in {name}")
            if not queue:
                raise

        except Exception as e:
            logger.error(f"{repr(e)} in {name}")
            if not queue:
                raise

        finally:
            logger.debug(
                f"Semaphore released ({semaphore._value} free) - {name}"
            )

async def discovery(
    loop: "asyncio.AbstractEventLoop",
    callback: Optional[ProgressCallback] = None,
    ip_filter: Optional[Any] = None,
) -> None:
    """Discover connected gateways and process scheduled query results.

    Args:
        loop: Event loop used by `schedule_queries`.
        callback: Optional progress callback invoked as (ok, err, total).
        ip_filter: Optional filter passed to `connected_gws(ip_filter)`.
    Returns:
        None
    """
    # connected_gws() should return mapping: lan_ip -> proto
    gw_map: Dict[str, str] = connected_gws(ip_filter)

    bgws = {ip: BGW(ip, proto) for ip, proto in gw_map.items()}
    if not bgws:
        return

    tasks = schedule_queries(loop, bgws)
    total = len(tasks)
    ok = 0
    err = 0

    if callback:
        callback((ok, err, total))

    for fut in asyncio.as_completed(tasks):
        try:
            result = await fut
        except Exception:
            err += 1
            if callback:
                callback((ok, err, total))
            continue

        if isinstance(result, Exception):
            err += 1
            if callback:
                callback((ok, err, total))
            continue

        # Successful command result
        if isinstance(result, CommandResult) and result.returncode == 0:
            lan_ip = getattr(result, "name", None)
            if lan_ip and lan_ip in bgws:
                process_item(result, bgw=bgws[lan_ip])
                ok += 1
            else:
                err += 1
        else:
            err += 1
            logger.error("Query failed: %r", result)

        if callback:
            callback((ok, err, total))

def schedule_queries(
    loop: "asyncio.AbstractEventLoop",
    bgws: Optional[BGWMap] = None,
    callback: Optional[Callable[[], None]] = None,
) -> List["asyncio.Future[Any]"]:
    """Schedule polling/query tasks for BGWs.

      - Creates a shared semaphore limiting concurrent polling.
      - Optionally creates a work queue (when polling).
      - Schedules one `query(...)` task per BGW and returns the task list.

    Args:
        loop: Event loop to schedule tasks on.
        bgws: Optional mapping BGWs. If omitted, uses global `BGWs`.
        callback: Optional progress callback passed to `process_queue`.

    Returns:
        A list of scheduled task objects (Tasks/Futures), one per BGW query.
        (The queue consumer task is scheduled but not included in this list.)
    """
    queue = asyncio.Queue(loop=loop) if GWs else None  # type: ignore

    bgw_map = bgws if bgws is not None else BGWs  # expects .items()

    semaphore = Semaphore(int(CONFIG.get("max_polling", 20)))
    timeout = int(CONFIG.get("timeout", 25))
    polling_secs = int(CONFIG.get("polling_secs", 15))

    # Storage is passed into process_queue
    storage: AbstractRepository[str, RTPDetails] = CONFIG.get("storage", RTPs)

    if queue is not None:
        nok_rtp_only = bool(CONFIG.get("nok_rtp_only", False))
        schedule_task(
            process_queue(
                queue,
                storage=storage,
                callback=callback,
                nok_rtp_only=nok_rtp_only
            ),
            loop=loop,
        )

    tasks: List["asyncio.Future[Any]"] = []

    for lan_ip, bgw in bgw_map.items():
        task = schedule_task(
            query(
                bgw,
                semaphore=semaphore,
                name=lan_ip,
                queue=queue,
                timeout=timeout,
                polling_secs=polling_secs,
            ),
            name=lan_ip,
            loop=loop,
        )
        tasks.append(task)

    return tasks

def schedule_http_server(
    loop: "asyncio.AbstractEventLoop",
) -> None:
    """Schedule the HTTP upload server and its processing task.

    This function conditionally starts an HTTP server used for receiving
    uploaded capture files and a background task that processes uploaded
    items from a queue.

    Behaviour:
        - If no HTTP server host is CONFIGured, nothing is scheduled.
        - An asyncio.Queue is created for uploaded items.
        - The HTTP server coroutine is scheduled on the given event loop.
        - A consumer coroutine (`process_upload_queue`) is scheduled to
          process items placed onto the upload queue.

    Args:
        loop: The asyncio event loop on which to schedule tasks.

    Returns:
        None
    """
    http_server: Optional[str] = CONFIG.get("http_server")

    if not http_server:
        logger.warning(f"HTTP server will not be started")
        return

    upload_queue: "asyncio.Queue" = asyncio.Queue(loop=loop)  # type: ignore

    schedule_task(
        start_http_server(
            host=http_server,
            port=int(CONFIG.get("http_port", 8080)),
            upload_dir=CONFIG.get("upload_dir", "./"),
            upload_queue=upload_queue,
        ),
        name="http_server",
        loop=loop,
    )

    schedule_task(
        process_upload_queue(upload_queue, storage=PCAPs),
        name="process_upload_queue",
        loop=loop,
    )

async def rtpinfos(pcapfile):
    """
    Extract RTP stream statistics from a pcap file using tshark.

    This coroutine invokes `tshark` with RTP analysis options enabled and
    returns the textual output of the RTP stream summary.

    Args:
        pcapfile: Path to the pcap file to analyse.

    Returns:
        A string containing the RTP stream information produced by tshark.
        If the command fails (non-zero return code), an empty string is
        returned.
    """
    program = "tshark"
    args = ["-n", "-q", "-o", "rtp.heuristic_rtp:TRUE",
            "-z", "rtp,streams", "-r", pcapfile]

    result = await run_cmd(program, args)
    logger.debug(f"rtpinfos {result}")

    return "" if result.returncode else result.stdout.strip()

async def capinfos(pcapfile):
    """
    Extract capture metadata from a pcap file using capinfos.

    This coroutine runs the `capinfos` utility against the given pcap file
    and returns its textual output, which typically includes capture
    duration, packet counts, file size, and timestamps.

    Args:
        pcapfile: Path to the pcap file to analyse.

    Returns:
        A string containing the capinfos output.
        If the command fails (non-zero return code), an empty string is
        returned.
    """
    program = "capinfos"
    args = [pcapfile]

    result = await run_cmd(program, args)
    logger.debug(f"capinfos {result}")

    return "" if result.returncode else result.stdout.strip()

def startup_async_loop():
    """Sets up the non-blocking event loop and child watcher."""
    loop = asyncio.new_event_loop()
    
    # Create and attach NEW watcher BEFORE setting the loop
    watcher = asyncio.SafeChildWatcher()
    watcher.attach_loop(loop)
    asyncio.set_child_watcher(watcher)

    # Now set the event loop
    asyncio.set_event_loop(loop)
    logger.debug("Loop started")

    return loop

def tick_async_loop(loop):
    """Run one iteration of the asyncio loop."""
    if loop is None or loop.is_closed():
        return

    # Run ready callbacks/I/O once, then stop.
    loop.call_soon(loop.stop)
    loop.run_forever()

def request_shutdown(loop):
    """Schedule shutdown on the loop; do not block."""
    if loop is None or loop.is_closed():
        return

    logger.debug("Async loop shutdown requested")
    # Create a task inside the loop
    loop.create_task(_shutdown_async(loop))

    # Ensure the loop runs at least one more tick
    loop.call_soon(loop.stop)

async def _shutdown_async(loop):
    """Helper coroutine to prepare shutting down the loop"""
    await _cancel_all_tasks(loop)
    try:
        await loop.shutdown_asyncgens()
    except Exception:
        pass

async def _cancel_all_tasks(loop):
    logger.debug("Cancelling all tasks except current task")
    current = asyncio.Task.current_task(loop=loop)
    tasks = [
        t for t in asyncio.Task.all_tasks(loop=loop)
        if t is not current and not t.done()
    ]

    for t in tasks:
        t.cancel()

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

def finalize_loop_if_idle(loop):
    """Close loop once all tasks are done/cancelled."""
    if loop is None or loop.is_closed():
        return True

    logger.debug("Closing async loop")
    
    pending = [t for t in asyncio.Task.all_tasks(loop) if not t.done()]
    if pending:
        return False

    loop.close()
    return True

############################## END ALOOP ######################################
############################## BEGIN WORKSPACE ################################

WorkspaceT = Any
ActionFunc = Callable[..., Any]
AttrCell = Tuple[int, int, str, int]
AttrIterator = Callable[[Any], Iterable[AttrCell]]
DoneCallback = Callable[[], None]
ProgressTuple = Tuple[int, int, int]
ToggleFunc = Callable[[Optional[WorkspaceT]], Any]

class Display(ABC):
    """Base class for a curses-driven UI.

    This class owns the main curses loop. It supports:
      - non-blocking keyboard input (`nodelay(True)`)
      - screen resize handling
      - optional integration with an asyncio loop via `tick_async_loop()`

    Subclasses implement:
      - `make_display()` to draw/rebuild the UI (also a good place to recompute
        layout, create windows/panels, etc.)
      - `handle_char()` to react to keystrokes

    Attributes:
        stdscr: The root curses screen from `curses.wrapper`.
        miny/minx: Minimum terminal size required for the UI.
        workspaces: List of workspace objects (may be empty).
        tab: Optional tab UI object (implementation-specific).
        loop: Optional asyncio event loop used by the application.
        loop_shutdown_requested: Flag set by caller when a shutdown is requested.
        done: When True the main loop exits.
        active_ws_idx: Index of current workspace in `workspaces`.
        special_pair: A curses color-pair number reserved for "special" UI text.
    """

    def __init__(
        self,
        stdscr: "_curses._CursesWindow",
        miny: int = 24,
        minx: int = 80,
        workspaces: Optional[List[Any]] = None,
        tab: Optional[Any] = None,
    ) -> None:
        self.stdscr = stdscr
        self.miny = miny
        self.minx = minx
        self._workspaces = [] if workspaces is None else workspaces
        self._tab = tab

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Initialize runtime state. Safe to call once at startup."""
        self.done = False  # type: bool
        self.active_ws_idx = 0  # type: int
        self.loop = None  # type: Optional["asyncio.AbstractEventLoop"]
        self.loop_shutdown_requested = False

        # Cache current size (subclasses may use it).
        self.maxy, self.maxx = self.stdscr.getmaxyx()
        
        self.init_colors()

    def init_colors(self) -> None:
        """Initialize curses color pairs.

        Notes:
            - Creates a grayscale-like mapping of (pair=i+1 -> fg=i, bg=-1)
              for as many colors as the terminal supports.
            - Also reserves `self.special_pair` for UI messages/highlights.
        """
        curses.start_color()
        curses.use_default_colors()

        max_pairs = min(curses.COLORS, curses.COLOR_PAIRS - 1)
        for i in range(max_pairs):
            curses.init_pair(i + 1, i, -1)

        # Reserve a dedicated pair number that is not 0.
        self.special_pair = min(1, curses.COLOR_PAIRS - 1)

        fg = 21 if curses.COLORS > 21 else curses.COLOR_CYAN
        bg = 246 if curses.COLORS > 246 else -1
        curses.init_pair(self.special_pair, fg, bg)

    def set_exit(self) -> None:
        """Request clean exit from the curses main loop."""
        self.done = True

    def run(self) -> None:
        """Main curses loop.

        The loop is non-blocking:
          - When no key is pressed, we optionally tick the asyncio loop and
            sleep briefly to reduce CPU usage.
          - On resize, we re-check minimum size and call `make_display()`.
          - All other keys are forwarded to `handle_char()`.
        """
        self.stdscr.nodelay(True)
        self.stdscr.keypad(True)

        try:
            curses.curs_set(0)
        except curses.error:
            pass

        self.make_display()

        while not self.done:
            curses.panel.update_panels()
            ch = self.stdscr.getch()

            if ch == curses.ERR:
                # No input. Tick asyncio if present.
                if self.loop is not None:
                    tick_async_loop(self.loop)

                    if self.loop_shutdown_requested:
                        if finalize_loop_if_idle(self.loop):
                            self.loop = None
                            self.loop_shutdown_requested = False

                time.sleep(0.05)
                continue

            if ch == curses.KEY_RESIZE:
                self.maxy, self.maxx = self.stdscr.getmaxyx()

                if self.maxy >= self.miny and self.maxx >= self.minx:
                    self.make_display()
                    curses.panel.update_panels()
                    curses.doupdate()
                    if self.active_workspace is not None:
                        self.active_workspace.menubar.draw()
                else:
                    self.stdscr.erase()
                    self.stdscr.refresh()
                    break
                continue

            # Forward all other keys to subclass handler.
            try:
                ch_repr = repr(chr(ch)) if 0 <= ch <= 0x10FFFF else repr(ch)
            except Exception:
                ch_repr = repr(ch)
            
            logger.debug("Detected char %r (%s)", ch, ch_repr)
            self.handle_char(ch)

    @property
    def active_workspace(self) -> Optional[Any]:
        """Return the currently active workspace, or None."""
        if not self.workspaces:
            return None
        if self.active_ws_idx >= len(self.workspaces):
            self.active_ws_idx = 0
        return self.workspaces[self.active_ws_idx]

    @property
    def workspaces(self):
        return self._workspaces

    @workspaces.setter
    def workspaces(self, value):
        self._workspaces = value
        # Auto-create tab when workspaces are set
        if value and not self._tab:
            self._tab = Tab(self, tab_names=[ws.name for ws in value])

    @property
    def tab(self):
        return self._tab

    @tab.setter
    def tab(self, value):
        self._tab = value

    @abstractmethod
    def make_display(self) -> None:
        """(Re)build and draw the UI."""
        raise NotImplementedError

    @abstractmethod
    def handle_char(self, char: int) -> None:
        """Handle a keystroke from the main loop."""
        raise NotImplementedError

    def update_title(self, title: str = None) -> None:
        """Updates terminal window title using curses."""
        if title is None:
            return
        try:
            curses.putp(curses.tigetstr("tsl"))  # Enter title mode
            sys.stderr.write(title)
            curses.putp(curses.tigetstr("fsl"))  # Exit title mode
            sys.stderr.flush()
        except:
            # Fallback to escape sequence
            sys.stderr.write(f"\x1b]2;{title}\x07")
            sys.stderr.flush()

class MyDisplay(Display):
    """Concrete Display implementation.

    Responsibilities:
      - Delegates most keystrokes to the active workspace's `handle_char`.
      - Draws the tab bar (if present) and the active workspace.
      - Handles global keys (e.g., quit).

    Notes:
      - `active_handle_char` is a callable that routes input to the currently
        focused component (typically the active workspace, but may be swapped
        temporarily to a panel/textbox handler).
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super(MyDisplay, self).__init__(*args, **kwargs)
        # Default handler: safe no-op until make_display sets a real one.
        self.active_handle_char = self._noop_handle_char

    def _noop_handle_char(self, char: int) -> None:
        """Fallback handler used before UI components are ready."""
        return

    def make_display(self) -> None:
        """(Re)build and draw the UI.

        Sets the active input handler to the active workspace handler,
        clears the screen, draws the tab bar (if any), then draws the active
        workspace.
        """
        ws = self.active_workspace
        if ws is None:
            return

        self.active_handle_char = ws.handle_char
        self.maxy, self.maxx = self.stdscr.getmaxyx()
        self.stdscr.erase()

        if self.tab is not None:
            self.tab.draw()

        ws.draw()

    def handle_char(self, char: int) -> None:
        """Handle a keystroke from the main loop.

        Global shortcuts:
          - 'q' or 'Q': exit the application

        All other keys are forwarded to `active_handle_char`.
        """
        # Quit on 'q' or 'Q'
        if char in (ord("q"), ord("Q")):
            self.set_exit()
            return

        # Forward to currently active handler (workspace/panel/etc).
        try:
            self.active_handle_char(char)
        except Exception as e:
            logger.exception(f"{e} in active_handle_char")
            pass

    @property
    def title(self) -> str:
        """Return current memory usage in MB."""
        mem = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024)
        bgws = len(BGWs)
        rtps = len(RTPs)
        return f"MemUsage: {mem}MB  |  BGWs: {bgws}  |  RTPs: {rtps}"

class Tab(object):
    """Simple top tab bar widget for curses.

    Draws a row (or two lines) of tabs using box-drawing characters.
    The active tab is drawn normally; inactive tabs are dimmed.

    The widget owns a curses subwindow and draws within it.
    """

    def __init__(
        self,
        display: Any,
        tab_names: Sequence[str],
        nlines: int = 2,
        yoffset: int = 0,
        xoffset: int = 0,
        color_text: int = 0,
        color_border: int = 65024,
    ) -> None:
        """
        Args:
            display: Object that provides `stdscr`.
            tab_names: Names/labels for each tab.
            nlines: Height of the tab bar in rows.
            yoffset: Y position relative to stdscr.
            xoffset: X position relative to stdscr.
            color_text: curses attribute for tab text.
            color_border: curses attribute for tab border.
        """
        self.display = display
        self.tab_names = list(tab_names)
        self.nlines = int(nlines)
        self.yoffset = int(yoffset)
        self.xoffset = int(xoffset)
        self.color_text = int(color_text)
        self.color_border = int(color_border)

        self.stdscr = None          # type: Any
        self.win = None             # type: Optional[Any]
        self.maxy = 0
        self.maxx = 0
        self.active_tab_idx = 0
        self.tab_width = 0

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Compute geometry and create the subwindow."""
        self.stdscr = self.display.stdscr
        self.active_tab_idx = 0

        maxy, maxx = self.stdscr.getmaxyx()
        self.maxy = min(self.nlines, maxy)
        self.maxx = maxx

        width = self.maxx - self.xoffset
        if self.maxy <= 0 or width <= 0:
            self.win = None
            self.tab_width = 0
            return

        try:
            self.win = self.stdscr.subwin(
                self.maxy,
                width,
                self.yoffset,
                self.xoffset,
            )
        except curses.error:
            self.win = None
            self.tab_width = 0
            return

        if not self.tab_names:
            self.tab_width = 0
            return

        computed = (
            width - (len(self.tab_names) * 2)
        ) // len(self.tab_names)
        self.tab_width = max(3, computed)

    def draw(self) -> None:
        """Draw the tab bar."""
        if (
            self.win is None
            or not self.tab_names
            or self.tab_width <= 0
        ):
            return

        xpos = 0
        for idx, name in enumerate(self.tab_names):
            active = idx == self.active_tab_idx
            self._draw_tab(name, xpos, active)
            xpos += self.tab_width + 2

        try:
            self.win.noutrefresh()
        except curses.error:
            pass

    def _draw_tab(
        self,
        name: str,
        xpos: int,
        active: bool,
    ) -> None:
        """Draw a single tab."""
        if self.win is None:
            return

        top = u"┌" + (u"─" * self.tab_width) + u"┐"
        mid = u"│" + (u" " * self.tab_width) + u"│"

        if active:
            border_attr = self.color_border
            text_attr = self.color_text
        else:
            border_attr = self.color_border | curses.A_DIM
            text_attr = self.color_text | curses.A_DIM

        try:
            self.win.addstr(0, xpos, top, border_attr)
            for line in range(1, self.maxy):
                self.win.addstr(line, xpos, mid, border_attr)
        except curses.error:
            pass

        if self.maxy > 1:
            try:
                label = "{:^{w}}".format(
                    name[: self.tab_width],
                    w=self.tab_width,
                )
                self.win.addstr(
                    1,
                    xpos + 1,
                    label,
                    text_attr,
                )
            except curses.error:
                pass

    def next_tab(self) -> None:
        """Activate the next tab."""
        if not self.tab_names:
            return

        self.active_tab_idx = (
            self.active_tab_idx + 1
        ) % len(self.tab_names)
        self.draw()

    def prev_tab(self) -> None:
        """Activate the previous tab."""
        if not self.tab_names:
            return

        self.active_tab_idx = (
            self.active_tab_idx - 1
        ) % len(self.tab_names)
        self.draw()

class Button(object):
    """
    UI button bound to a keyboard key (char_int) with optional on/off actions.

    The button has two states:
      - state == 0: "off"
      - state == 1: "on"

    When toggled:
      - If state is off, func_on(workspace) is called (if provided). If it
        returns a truthy value and func_off exists, state becomes 1; otherwise 0.
      - If state is on, func_off(workspace) is called (if provided). If it
        returns a truthy value, state becomes 0; otherwise stays 1.

    Notes:
      - If func_off is not provided, this button cannot deactivate (state stays 1)
        once activated.
      - done_callback_on/off (if provided) are called after a successful
        activate/deactivate transition.
    """

    def __init__(
        self,
        char_int: int,
        label_on: Optional[str] = None,
        func_on: Optional[ToggleFunc] = None,
        char_uni: Optional[str] = None,
        label_off: Optional[str] = None,
        func_off: Optional[ToggleFunc] = None,
        done_callback_on: Optional[DoneCallback] = None,
        done_callback_off: Optional[DoneCallback] = None,
        status_label: str = "",
        status_color_on: int = 0,
        status_color_off: int = 0,
        name: str = "",
    ) -> None:
        self.char_int = char_int
        self.char_str = chr(char_int)
        self.char_uni = char_uni

        # Use explicit None checks so empty-string labels are allowed.
        self.label_on = label_on if label_on is not None else str(self)
        self.label_off = label_off if label_off is not None else self.label_on

        self.func_on = func_on
        self.func_off = func_off

        self.done_callback_on = done_callback_on
        self.done_callback_off = done_callback_off

        self.status_label = status_label
        self.status_color_on = status_color_on
        self.status_color_off = status_color_off

        self.name = name if name else str(self)

        self.state = 0  # 0=off, 1=on

    @property
    def char(self) -> str:
        """Human-friendly key label for display."""
        if self.char_uni:
            return self.char_uni
        if self.char_str == "\n":
            return "Enter"
        return self.char_str

    @property
    def label(self) -> str:
        """Current button label based on state."""
        return self.label_on if self.state else self.label_off

    @property
    def status_color(self) -> int:
        """Status color based on state."""
        return self.status_color_on if self.state else self.status_color_off

    def toggle(self, *args: Any, **kwargs: Any) -> None:
        """
        Toggle the button state by calling the on/off function(s).

        workspace is passed through to func_on/func_off when provided.
        """
        # Activating
        if not self.state:
            result = self.func_on(*args, **kwargs) if self.func_on else 1

            new_state = 1 if result and self.func_off else 0
            self.state = new_state
            logger.info("%s activation in state %s", self.name, self.state)

            if self.state and self.done_callback_on:
                self.done_callback_on()

            return

        # Deactivating
        if self.func_off:
            result = self.func_off(*args, **kwargs)
            self.state = 0 if result else 1
        else:
            self.state = 1  # this is for fire-and-forget buttons

        logger.info("%s deactivation in state %s", self.name, self.state)

        if not self.state and self.done_callback_off:
            self.done_callback_off()

    def status_attrs(self) -> Tuple[str, int]:
        """Return (status_label, status_color) for UI rendering."""
        return self.status_label, self.status_color

    def __str__(self) -> str:
        return "Button({})".format(repr(chr(self.char_int)))

    def __repr__(self) -> str:
        return "Button(char_int={}, label_on={!r})".format(
            self.char_int, self.label_on
        )

class Menubar(object):
    """
    Single-line menubar rendered at the bottom of the screen.

    Layout:
      [status labels ... │]     <spacing>     [buttons: key=label ...]

    - Status labels come from Button.status_label/status_color.
    - Button labels come from Button.char and Button.label.
    """

    def __init__(
        self,
        display: Any,
        xoffset: int = 2,
        bar_color: int = 0,
        buttons: Optional[Sequence[Any]] = None,
        button_width: int = 10,
        button_gap: int = 3,
        max_status_width: int = 15,
        status_button_spacing: int = 5,
    ) -> None:
        self.display = display
        self.xoffset = xoffset
        self.bar_color = bar_color
        self.buttons = list(buttons) if buttons else []  # type: List[Any]
        self.button_width = button_width
        self.button_gap = button_gap
        self.max_status_width = max_status_width
        self.status_button_spacing = status_button_spacing

        self._init_attrs()

    def _init_attrs(self) -> None:
        """
        Initialize or refresh window geometry.
        """
        self.stdscr = self.display.stdscr
        maxy, maxx = self.stdscr.getmaxyx()

        height = 1
        width = max(1, maxx)
        begin_y = max(0, maxy - 1)
        begin_x = 0

        self.win = curses.newwin(height, width, begin_y, begin_x)
        self.maxy, self.maxx = self.win.getmaxyx()
        self.color = self.bar_color | curses.A_REVERSE

    def draw(self) -> None:
        """
        Redraw the entire menubar line.
        """
        try:
            sy, sx = self.stdscr.getmaxyx()
            win_y, _ = self.win.getbegyx()
            if sx != self.maxx or (sy - 1) != win_y:
                self._init_attrs()
        except Exception:
            pass

        try:
            self.win.addstr(0, 0, " " * self.maxx, self.color)
        except _curses.error:
            pass

        status_end = self._draw_status_labels()
        self._draw_button_labels(status_end)

        try:
            self.win.refresh()
        except _curses.error:
            pass

    def _truncate_status_labels(
        self,
        status_buttons: Sequence[Any],
    ) -> List[str]:
        """
        Truncate status labels so they fit within max_status_width.
        """
        if not status_buttons:
            return []

        num_separators = len(status_buttons)
        available = self.max_status_width - num_separators
        if available <= 0:
            return [""] * len(status_buttons)

        labels = [b.status_attrs()[0] for b in status_buttons]
        total = sum(len(label) for label in labels)

        if total <= available:
            return labels

        width_per = available // len(labels)
        remainder = available % len(labels)

        truncated = []
        for idx, label in enumerate(labels):
            extra = 1 if idx < remainder else 0
            target = width_per + extra
            truncated.append(label[:max(0, target)])

        return truncated

    def _draw_status_labels(self) -> int:
        """
        Draw status labels on the left side.

        Returns:
            int: x position immediately after the status area.
        """
        status_buttons = [
            b for b in self.buttons
            if getattr(b, "status_label", "")
        ]

        if not status_buttons:
            return 0

        labels = self._truncate_status_labels(status_buttons)
        x = 0

        for button, label in zip(status_buttons, labels):
            if not label or x >= self.maxx:
                break

            try:
                _, status_color = button.status_attrs()
            except Exception:
                status_color = 0

            remaining = self.maxx - x
            chunk = label[:remaining]

            try:
                self.win.addstr(0, x, chunk, status_color)
            except _curses.error:
                pass

            x += len(chunk)

            if x < self.maxx:
                try:
                    self.win.addstr(0, x, u"│", self.color)
                except _curses.error:
                    pass
                x += 1

        return x

    def _draw_button_labels(self, status_end_x: int) -> None:
        """
        Draw button labels to the right of the status area.
        """
        x = max(
            self.xoffset,
            status_end_x + self.status_button_spacing,
        )

        for idx, button in enumerate(self.buttons):
            if x >= self.maxx:
                break

            try:
                key = button.char
                label = button.label
            except Exception:
                continue

            text = "{}={:<{w}}".format(
                key,
                label,
                w=self.button_width,
            )

            remaining = self.maxx - x
            if remaining <= 0:
                break

            chunk = text[:remaining]

            try:
                self.win.addstr(0, x, chunk, self.color)
            except _curses.error:
                pass

            x += len(chunk)

            if idx < len(self.buttons) - 1:
                x += self.button_gap

class TextPanel(object):
    """
    Scrollable text viewer shown as a curses panel.

    This panel renders `storage` (a sequence of text lines) inside a boxed window
    and supports vertical/horizontal scrolling.

    Notes:
        - This class does *not* own the event loop. It assumes the caller routes
          keystrokes to `handle_char()`.
        - `workspace_chars` contains key codes that should be forwarded to the
          active workspace handler (e.g. Enter).
    """

    def __init__(
        self,
        display: Any,
        storage: Sequence[str],
        yoffset: int = 2,
        margin: int = 1,
        color_text: int = 0,
        color_border: int = 63488,
        name: Optional[str] = None,
        workspace_chars: Optional[Iterable[int]] = None,
    ) -> None:
        # Keep all original init attributes (do not remove / rename).
        self.display = display
        self.stdscr = display.stdscr
        self.storage = storage
        self.yoffset = yoffset
        self.margin = margin
        self.color_text = color_text
        self.color_border = color_border
        self.name = name
        self.workspace_chars = (
            list(workspace_chars) if workspace_chars else [10]
        )

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Initialize geometry, window and panel objects."""
        self.posy = 0
        self.posx = 0
        self.max_width = 0

        scr_h, scr_w = self.stdscr.getmaxyx()
        usable_h = scr_h - self.yoffset - 1
        usable_w = scr_w

        # Max window size inside margins (and never below 2 for borders)
        max_h = max(2, usable_h - (2 * self.margin))
        max_w = max(2, usable_w - (2 * self.margin))

        # Desired height: storage lines + 2 border lines
        desired_h = len(self.storage) + 2

        self.nlines = min(max_h, desired_h)
        self.ncols = max_w

        begin_x = self.margin

        # Center within usable area, then clamp
        center_off = (usable_h - self.nlines) // 2
        begin_y = self.yoffset + max(0, center_off)
        begin_y = min(begin_y, self.yoffset + max(0, usable_h - self.nlines))

        self.win = curses.newwin(self.nlines, self.ncols, begin_y, begin_x)
        self.panel = curses.panel.new_panel(self.win)
        self.panel.hide()

    def draw(self, storage: Optional[Sequence[str]] = None) -> None:
        """Render current viewport and show the panel."""
        page_h = max(0, self.nlines - 2)
        view_w = max(0, self.ncols - 2)

        if storage is not None:
            self.storage = storage
            self.posy = 0
            self.posx = 0

        data = self.storage
        it = data[self.posy : self.posy + page_h]
        self.max_width = max((len(x) for x in it), default=0)

        self.win.erase()

        for row, line in enumerate(it, start=1):
            try:
                slice_ = line[self.posx : self.posx + view_w]
                text = "{:<{w}}".format(slice_, w=view_w)
                self.win.addstr(row, 1, text, self.color_text)
            except curses.error:
                pass

        try:
            self.win.attron(self.color_border)
            self.win.box()
            self.win.attroff(self.color_border)
        except curses.error:
            pass

        self.panel.show()
        self.panel.top()
        curses.panel.update_panels()
        try:
            self.win.refresh()
        except curses.error:
            pass

    def erase(self) -> None:
        """Hide the panel and refresh the underlying screen."""
        self.panel.hide()
        curses.panel.update_panels()
        try:
            self.stdscr.refresh()
        except curses.error:
            pass

    def handle_char(self, char: int) -> None:
        """
        Handle navigation keys and forward selected keys to active workspace.

        Args:
            char: The key code from `getch()`.
        """
        page_y = self.nlines - 2
        view_x = self.ncols - 2

        max_y = max(0, len(self.storage) - page_y)
        max_x = max(0, self.max_width - view_x)

        # Forward selected keys to the workspace (e.g. Enter).
        if char in self.workspace_chars:
            ws = self.display.active_workspace
            if ws is not None:
                ws.handle_char(char)
            return

        if char == curses.KEY_DOWN:
            if self.posy < max_y:
                self.posy += 1

        elif char == curses.KEY_UP:
            if self.posy > 0:
                self.posy -= 1

        elif char == curses.KEY_HOME:
            self.posy = 0
            self.posx = 0

        elif char == curses.KEY_END:
            self.posy = max_y
            self.posx = max_x

        elif char == curses.KEY_NPAGE:
            self.posy = min(self.posy + page_y, max_y)

        elif char == curses.KEY_PPAGE:
            self.posy = max(self.posy - page_y, 0)

        elif char == curses.KEY_RIGHT:
            if self.posx < max_x:
                self.posx += 1

        elif char == curses.KEY_LEFT:
            if self.posx > 0:
                self.posx -= 1

        self.draw()

class ObjectPanel(object):
    """
    A bordered panel that renders an object's attributes using an iterator.

    The iterator (`attr_iterator`) is responsible for converting `obj` into an
    iterable of cells: (ypos, xpos, text, color_attr).

    Keys listed in `workspace_chars` are forwarded to the active workspace
    handler (so you can keep ENTER etc. working consistently).
    """

    def __init__(
        self,
        display: Any,
        obj: Any,
        attr_iterator: AttrIterator,
        callback: Optional[Callable[[int], None]] = None,
        yoffset: int = 2,
        margin: int = 1,
        color_border: int = 63488,
        name: Optional[str] = None,
        workspace_chars: Optional[Sequence[int]] = None,
    ) -> None:
        self.display = display
        self.obj = obj
        self.attr_iterator = attr_iterator
        self.callback = callback
        self.yoffset = yoffset
        self.margin = margin
        self.color_border = color_border
        self.name = name
        self.workspace_chars = (
            list(workspace_chars) if workspace_chars is not None else [10]
        )

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Create the underlying curses window and panel."""
        self.stdscr = self.display.stdscr
        scr_h, scr_w = self.stdscr.getmaxyx()

        usable_h = max(2, scr_h - self.yoffset - 1)
        usable_w = max(2, scr_w - (2 * self.margin))

        self.nlines = usable_h
        self.ncols = usable_w

        begin_y = max(0, self.yoffset)
        begin_x = max(0, self.margin)

        # Clamp start so window fits.
        begin_y = min(begin_y, max(0, scr_h - self.nlines))
        begin_x = min(begin_x, max(0, scr_w - self.ncols))

        self.win = curses.newwin(self.nlines, self.ncols, begin_y, begin_x)
        self.panel = curses.panel.new_panel(self.win)
        self.panel.hide()

    def draw(self, obj: Optional[Any] = None) -> None:
        """
        Draw the panel contents.

        Args:
            obj: Optional override object to render; defaults to `self.obj`.
        """
        self.win.erase()

        try:
            self.win.attron(self.color_border)
            self.win.box()
            self.win.attroff(self.color_border)
        except curses.error:
            pass

        target = self.obj if obj is None else obj

        maxy, maxx = self.win.getmaxyx()
        for ypos, xpos, text, color in self.attr_iterator(target):
            # Basic bounds guard; still keep try/except for safety.
            if ypos < 0 or xpos < 0 or ypos >= maxy or xpos >= maxx:
                continue
            try:
                self.win.addstr(ypos, xpos, text[: max(0, maxx - xpos)], color)
            except curses.error:
                pass

        self.panel.show()
        self.panel.top()
        curses.panel.update_panels()
        curses.doupdate()

    def handle_char(self, char: int) -> None:
        """
        Handle a keypress.

        - Keys in `workspace_chars` are forwarded to the active workspace.
        - Otherwise `callback(char)` is called if provided.
        """
        if char in self.workspace_chars:
            ws = getattr(self.display, "active_workspace", None)
            if ws is not None:
                ws.handle_char(char)
            return

        if self.callback is not None:
            self.callback(char)

    def erase(self) -> None:
        """Hide and clear the panel."""
        try:
            self.win.erase()
            self.win.noutrefresh()
        except curses.error:
            pass

        self.panel.hide()
        curses.panel.update_panels()
        curses.doupdate()

class Confirmation(object):
    """
    Simple modal confirmation panel.

    Displays a small centered box with a message (e.g. "Do you confirm (Y/N)?")
    and forwards keystrokes to an optional callback.

    Typical usage:
        panel = Confirmation(display, callback=on_key)
        panel.draw()
        display.active_handle_char = panel.handle_char

    Notes:
        - This class does not interpret Y/N itself; it just forwards `char`
          to `callback(char)`.
        - Coordinates are clamped so the window always stays on-screen.
    """

    def __init__(
        self,
        display: Any,
        text: str = "Do you confirm (Y/N)?",
        callback: Optional[Callable[[int], None]] = None,
        yoffset: int = -1,
        margin: int = 1,
        color_border: int = 13312,
        color_text: int = 0,
    ) -> None:
        self.display = display
        self.text = text
        self.callback = callback
        self.yoffset = yoffset
        self.margin = margin
        self.color_border = color_border
        self.color_text = color_text

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Create the underlying curses window and panel."""
        self.stdscr = self.display.stdscr
        maxy, maxx = self.stdscr.getmaxyx()

        nlines = 3 + (2 * self.margin)
        ncols = len(self.text) + (2 * self.margin) + 2

        # Clamp to screen size so curses.newwin doesn't raise.
        nlines = max(2, min(nlines, maxy))
        ncols = max(2, min(ncols, maxx))

        begin_y = max(0, maxy // 2 + self.yoffset - (self.margin + 1))
        begin_x = max(0, maxx // 2 - (len(self.text) // 2) - (self.margin + 1))

        # Also clamp start so the window fits on-screen.
        begin_y = min(begin_y, max(0, maxy - nlines))
        begin_x = min(begin_x, max(0, maxx - ncols))

        self.win = curses.newwin(nlines, ncols, begin_y, begin_x)
        self.panel = curses.panel.new_panel(self.win)

        self.draw()

    def handle_char(self, char: int) -> None:
        """
        Forward a keystroke to the callback (if provided).

        Args:
            char: Key code returned by `getch()`.
        """
        if self.callback is not None:
            self.callback(char)

    def draw(self) -> None:
        """Render the confirmation box and update panels."""
        self.panel.top()
        self.panel.show()

        try:
            self.win.erase()
            self.win.attron(self.color_border)
            self.win.box()
            self.win.attroff(self.color_border)

            y = self.margin + 1
            x = self.margin + 1

            # Avoid writing outside window if terminal is tiny.
            maxy, maxx = self.win.getmaxyx()
            if 0 <= y < maxy and 0 <= x < maxx:
                self.win.addstr(y, x, self.text[: maxx - x - 1],
                                self.color_text)
        except curses.error:
            pass

        curses.panel.update_panels()
        curses.doupdate()

    def erase(self) -> None:
        """Hide the panel and refresh the underlying screen."""
        try:
            self.win.erase()
            self.win.noutrefresh()
        except curses.error:
            pass

        self.panel.hide()
        curses.panel.update_panels()
        curses.doupdate()

class ProgressBar(object):
    """
    A 1-line progress bar panel driven by a queue.

    The queue is expected to provide tuples: (ok, err, total). The bar displays
    progress as (ok + err) / total and overlays the "filled" portion in a
    different color.

    Typical usage:
        - Create the ProgressBar once (it creates/shows its panel).
        - Call draw() repeatedly from your main loop.
        - Optionally provide a callback that is called once when progress hits
          100% (fraction >= 1.0).
    """

    def __init__(
        self,
        display: Any,
        queue: Any,
        callback: Optional[Callable[[], None]] = None,
        text: str = "In Progress",
        yoffset: int = 0,
        color_forground: int = 122112,
        color_background: int = 126720,
        width: int = 33,
        workspace_chars: Optional[Sequence[int]] = None,
    ) -> None:
        self.display = display
        self.queue = queue
        self.callback = callback
        self.text = text
        self.yoffset = yoffset
        self.color_forground = color_forground
        self.color_background = color_background
        self.width = width
        self.workspace_chars = (
            list(workspace_chars) if workspace_chars is not None else [10]
        )

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Create the curses window and panel."""
        self.stdscr = self.display.stdscr
        self.fraction = 0.0
        self._done = False

        maxy, maxx = self.stdscr.getmaxyx()

        nlines = 1
        ncols = self.width if self.width else max(1, maxx - 4)
        ncols = max(1, min(ncols, maxx))  # clamp to screen width

        begin_y = maxy // 2 + self.yoffset
        begin_x = (maxx - ncols) // 2

        # Clamp to keep the window on-screen
        begin_y = max(0, min(begin_y, maxy - nlines))
        begin_x = max(0, min(begin_x, maxx - ncols))

        self.win = curses.newwin(nlines, ncols, begin_y, begin_x)
        self.panel = curses.panel.new_panel(self.win)
        self.panel.show()
        self.panel.top()

    def handle_char(self, char: int) -> None:
        """
        Forward specific keys back to the active workspace.

        This lets ENTER (etc.) behave consistently while the progress bar is up.
        """
        if char in self.workspace_chars:
            ws = getattr(self.display, "active_workspace", None)
            if ws is not None:
                ws.handle_char(char)

    def draw(self) -> None:
        """
        Render the current progress state.

        If the queue contains a progress tuple, it is consumed and used to
        update the bar; otherwise the bar is redrawn with the current fraction.
        """
        # Use the actual window width for formatting/drawing
        _, w = self.win.getmaxyx()

        # Pull latest progress update if available
        try:
            if not self.queue.empty():
                ok, err, total = self.queue.get_nowait()  # type: ignore[misc]
                try:
                    self.queue.task_done()  # type: ignore[attr-defined]
                except Exception:
                    pass

                done = ok + err
                if total and total > 0:
                    self.fraction = float(done) / float(total)
                else:
                    self.fraction = 0.0

                # Clamp
                if self.fraction < 0.0:
                    self.fraction = 0.0
                elif self.fraction > 1.0:
                    self.fraction = 1.0

                label = "{} {}/{}".format(self.text, done, total)
            else:
                label = self.text
        except Exception:
            # If the queue isn't the shape you expect, keep drawing safely.
            label = self.text

        filled_width = int(self.fraction * w)

        # Center label; keep at most w chars
        text = "{:^{width}}".format(label, width=w)[:w]

        self.win.erase()
        try:
            self.win.addstr(0, 0, text, self.color_background)
        except curses.error:
            pass
        try:
            self.win.addstr(0, 0, text[:filled_width], self.color_forground)
        except curses.error:
            pass

        curses.panel.update_panels()
        curses.doupdate()

        # Fire completion callback once
        if not self._done and self.fraction >= 1.0 and self.callback is not None:
            self._done = True
            self.callback()

    def erase(self) -> None:
        """Hide and clear the progress bar panel."""
        try:
            self.win.erase()
            self.win.noutrefresh()
        except curses.error:
            pass

        self.panel.hide()
        curses.panel.update_panels()
        curses.doupdate()

class FilterPanel(object):
    """
    A simple modal panel to show filter help, display the current filter,
    and let the user type a new filter (1–2 lines) via curses.textpad.Textbox.

    The panel reads keys directly from display.stdscr in a small internal
    loop (handle_char()). On ENTER it validates (optional) and calls the
    callback (optional). ESC cancels.
    It is blocking and should be run prior to running async coros. 
    """

    def __init__(
        self,
        display: Any,
        storage: Sequence[str],
        current_filter: str = "",
        validator: Optional[Callable[[str], Optional[str]]] = None,
        callback: Optional[Callable[[str], Any]] = None,
        yoffset: int = 1,
        margin: int = 1,
        name: Optional[str] = None,
        color_border: int = 0,
        color_text: int = 0,
        color_err: int = 2560,
        color_filter: int = 12288
    ) -> None:
        self.display = display
        self.storage = list(storage)
        self.current_filter = current_filter
        self.validator = validator
        self.callback = callback

        self.yoffset = yoffset
        self.margin = margin
        self.name = name
        self.color_border = color_border
        self.color_text = color_text
        self.color_err = color_err
        self.color_filter = color_filter

        self.cur_filter_label = "Current Filter: "
        self.new_filter_label = "    New Filter: "

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Create the panel windows and textbox."""
        self.stdscr = self.display.stdscr
        maxy, maxx = self.stdscr.getmaxyx()

        nlines = maxy - self.yoffset - (2 * self.margin)
        ncols = maxx - (2 * self.margin)
        begin_y = self.yoffset + self.margin
        begin_x = self.margin

        # Clamp to avoid invalid sizes (can happen on tiny terminals)
        nlines = max(3, nlines)
        ncols = max(10, ncols)

        self.win = curses.newwin(nlines, ncols, begin_y, begin_x)
        self.panel = curses.panel.new_panel(self.win)
        self.maxy, self.maxx = self.win.getmaxyx()
        self.err = ""

        # Current Filter Window
        cf_y = self.cf_y = min(len(self.storage) + 3, nlines - 5)
        cf_x = self.cf_x = len(self.cur_filter_label) + 1
        cf_width = self.cf_width = max(1, ncols - cf_x - 1)
        cf_height = 2
        self.cfwin = self.win.derwin(cf_height, cf_width, cf_y, cf_x)

        # New Filter Textbox (2 lines)
        tb_y = self.tb_y = min(len(self.storage) + 5, nlines - 3)
        tb_x = len(self.new_filter_label) + 1
        tb_width = max(1, ncols - tb_x - 1)
        tb_height = 2
        self.tbwin = self.win.derwin(tb_height, tb_width, tb_y, tb_x)
        self.textbox = curses.textpad.Textbox(self.tbwin, insert_mode=True)

    def draw(self) -> None:
        """Redraw the full panel."""
        try:
            self.win.attron(self.color_border)
            self.win.box()
            self.win.attroff(self.color_border)
        except curses.error:
            pass

        self.draw_help()
        self.draw_error()
        self.draw_current_filter()
        self.draw_new_filter()

        self.win.noutrefresh()
        self.cfwin.noutrefresh()
        self.tbwin.noutrefresh()
        curses.doupdate()

    def draw_help(self) -> None:
        """Draw the help text (storage) and the ENTER hint."""
        for r, line in enumerate(self.storage, 1):
            try:
                self.win.addstr(r, 1, line, self.color_text | curses.A_DIM)
            except curses.error:
                pass

        ypos = self.maxy - 2
        xpos = self.maxx // 2 - 4
        color = self.color_text | curses.A_REVERSE
        try:
            self.win.addstr(ypos, xpos, " ENTER ", color)
        except curses.error:
            pass

    def draw_error(self) -> None:
        """Draw the current validation error line (if any)."""
        try:
            err = "{:{w}}".format(self.err[: self.cf_width], w=self.cf_width)
            self.win.addstr(self.cf_y - 1, self.cf_x, err, self.color_err)
        except curses.error:
            pass

    def draw_current_filter(self) -> None:
        """Draw the 'Current Filter' label and the current filter value."""
        try:
            label = "{:<{w}}".format(self.cur_filter_label[: self.cf_width],
                                    w=self.cf_width)
            filter = "{}".format(self.current_filter)
            self.win.addstr(self.cf_y, 1, label, self.color_text)
            self.cfwin.addstr(0, 0, filter, self.color_filter)
        except curses.error:
            pass

    def draw_new_filter(self) -> None:
        """Draw the 'New Filter' label."""
        try:
            self.win.addstr(
                self.tb_y, 1, self.new_filter_label, self.color_text
            )
        except curses.error:
            pass

    def _close(self) -> None:
        """Hide and clear the panel."""
        try:
            curses.curs_set(0)
        except curses.error:
            pass

        try:
            self.win.erase()
            self.win.noutrefresh()
        except curses.error:
            pass

        self.panel.hide()
        curses.panel.update_panels()
        curses.doupdate()

    def handle_char(self) -> Optional[int]:
        """
        Run the modal input loop.

        Returns:
            Optional[int]:
              - 1 when cancelled (ESC)
              - None on submit (ENTER) or normal exit
        """
        try:
            curses.curs_set(1)
        except curses.error:
            pass

        self.draw()

        while True:
            char = self.stdscr.getch()

            if char == curses.ERR:
                time.sleep(0.1)
                continue

            # ESC to cancel
            if char == 27:
                self._close()
                return 1

            # Enter to submit
            if char in (10, 13):
                saved_y, saved_x = self.tbwin.getyx()

                try:
                    curses.curs_set(0)
                except curses.error:
                    pass

                result = self.textbox.gather()

                # Textbox uses newlines for multi-line input; join and strip.
                result = result.replace("\n", "").strip()

                if self.validator is not None:
                    err = self.validator(result)
                    if err:
                        self.err = err
                        self.tbwin.move(saved_y, saved_x)
                        try:
                            curses.curs_set(1)
                        except curses.error:
                            pass
                        self.draw()
                        continue

                if self.callback is not None:
                    self.callback(result)

                self._close()
                return None

            # Normal editing keys
            if char in (curses.KEY_BACKSPACE, 127, 8):
                char = curses.ascii.BS
            elif char == curses.KEY_DC:
                char = curses.ascii.EOT

            try:
                self.textbox.do_command(char)
                self.draw()
            except curses.error:
                # Ignore curses drawing/editing errors on edge conditions
                pass
            except Exception:
                # Keep your original behavior: don't let exceptions kill UI
                pass

class Workspace(object):
    """
    A single workspace (tab) containing:

    - A bordered frame window
    - A header window for column headers
    - A body window for storage rows
    - A curses panel attached to the body
    - A Menubar instance
    - Cursor and scrolling state

    Responsibilities:
    - Drawing itself
    - Handling navigation keys
    - Triggering buttons
    - Switching workspaces
    """

    def __init__(
        self,
        display: Any,
        layout: Any,
        buttons: Sequence[Any],
        storage: MemoryStorage,
        name: str,
        attr_iterator: Optional[
            Callable[..., Iterable[Any]]
        ] = None,
        yoffset: int = 2,
        menubar_height: int = 1,
        header_height: int = 3,
        filter_group: Optional[Any] = None,
        color_border: int = 63488,
        autoscroll: bool = True
    ) -> None:
        self.display = display
        self.layout = layout
        self.storage = storage
        self.buttons = list(buttons)
        self.name = name
        self.attr_iterator = attr_iterator
        self.yoffset = yoffset # This accounts for the Tab areas
        self.menubar_height = menubar_height
        self.header_height = header_height
        self.filter_group = filter_group
        self.color_border = color_border
        self.autoscroll = autoscroll

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Initialize curses windows, panels, and state."""
        self.stdscr = self.display.stdscr
        self.maxy, self.maxx = self.stdscr.getmaxyx()
        self.loop = None

        self.body_posy = 0
        self.body_posx = 0
        self.storage_cursor = 0

        self.menubar = Menubar(self.display, buttons=self.buttons)

        # Whole workspace area win and panel
        workspace_h = self.maxy - self.yoffset - self.menubar_height
        self.win = curses.newwin(workspace_h, self.maxx, self.yoffset, 0)
        self.panel = curses.panel.new_panel(self.win)
        self.active_panel = self.panel
        self.panel.show()

        # Workspace header area for column names
        self.headerwin = self.win.derwin(self.header_height, self.maxx, 0, 0)

        # Workspace body area for rows
        body_h = workspace_h - self.header_height - 1 # 1 for border
        body_w = self.maxx - 2 # 2 for border
        self.bodywin = self.win.derwin(body_h, body_w, self.header_height, 1)

        self.button_map: Dict[int, Any] = {}
        for button in self.buttons:
            self.button_map[button.char_int] = button
            try:
                upper = ord(chr(button.char_int).upper())
                self.button_map[upper] = button
            except Exception:
                pass
        
        self.draw()

    def draw(self, dim: bool=False) -> None:
        """Redraw frame, header, body, and menubar."""
        self.draw_bodywin(dim)
        self.draw_box(dim)
        self.draw_headerwin(dim)
        self.menubar.draw()

    def _layout_iter(self, obj: Optional[Any] = None) -> Iterable[Any]:
        """
        Return an iterator yielding:
        (ypos, xpos, text, color)
        """
        if self.attr_iterator is not None:
            return (
                self.attr_iterator()
                if obj is None
                else self.attr_iterator(obj)
            )

        if hasattr(self.layout, "iter_attrs"):
            return self.layout.iter_attrs(obj)

        return []

    def draw_box(self, dim: bool=False) -> None:
        """Draw box"""
        colorb = self.color_border | curses.A_DIM if dim else self.color_border
        try:
            self.win.attron(colorb)
            self.win.box()
            self.win.attroff(colorb)
        except curses.error:
            pass
        
        self.win.noutrefresh()

    def draw_headerwin(self, dim: bool=False) -> None:
        """Draw column headers and separators."""
        colorb = self.color_border | curses.A_DIM if dim else self.color_border
        
        try:
            self.headerwin.erase()
            self.headerwin.attron(colorb)
            self.headerwin.box()
            self.headerwin.attroff(colorb)
        except curses.error:
            pass

        for idx, cell in enumerate(self._layout_iter()):
            try:
                _, xpos, text, color = cell
            except Exception:
                continue

            color = color | curses.A_DIM if dim else color

            try:
                if idx > 0:
                    self.headerwin.addstr(0, xpos - 1, u"┬", colorb)
                    self.headerwin.addstr(1, xpos - 1, u"│", colorb)
                    self.headerwin.addstr(2, xpos - 1, u"┼", colorb)

                self.headerwin.addstr(1, xpos, text, color)
                self.headerwin.addstr(2, 0, u"├", colorb)
                self.headerwin.addstr(2, self.maxx - 1, u"┤", colorb)
            except curses.error:
                pass

        self.headerwin.refresh()

    def draw_bodywin(self, dim: bool=False, xoffset: int=1) -> None:
        """Draw visible rows from storage. The xoffset compensates for
           the left border and is subtracted from xpos.
        """
        if self.panel.hidden():
           return
 
        try:
            self.bodywin.erase()
        except curses.error:
            pass

        body_h, _ = self.bodywin.getmaxyx()
        n = len(self.storage)

        if self.autoscroll and n > 0:
            # Keep the selection pinned to the last item.
            self.storage_cursor = max(0, n - body_h)
            self.body_posy = min(body_h - 1, n - 1 - self.storage_cursor)
        else:
            # Clamp state if storage shrank or cursor went out of range.
            max_cursor = max(0, n - body_h)
            self.storage_cursor = min(self.storage_cursor, max_cursor)
            if n == 0:
                self.body_posy = 0
            else:
                self.body_posy = min(self.body_posy, min(body_h - 1, n - 1))

        end_idx = min(self.storage_cursor + body_h, len(self.storage))
        visible = self.storage.select((self.storage_cursor, end_idx))
        colorb = self.color_border | curses.A_DIM if dim else self.color_border

        for row, obj in enumerate(visible):
            for cell in self._layout_iter(obj):
                try:
                    _, xpos, text, color = cell
                except Exception:
                    continue

                if row != self.body_posy:
                    color |= curses.A_DIM
                    
                xpos = max(0, xpos - xoffset)
                color = color | curses.A_DIM if dim else color

                try:
                    self.bodywin.addstr(row, xpos, text, color)
                    self.bodywin.addstr(row, xpos + len(text), u"│", colorb)
                except curses.error:
                    pass

        if not self.panel.hidden():
            self.bodywin.noutrefresh()
            #self.draw_box(dim)
        self.menubar.draw()

    def cursor_handler(self, char: int) -> None:
        """Update cursor/scroll state and control autoscroll."""
        body_h, _ = self.bodywin.getmaxyx()
        n = len(self.storage)

        last_visible = max(0, body_h - 1)
        max_cursor = max(0, n - body_h)

        def at_last_item() -> bool:
            if n == 0:
                return True
            return (self.storage_cursor + self.body_posy) >= (n - 1)

        if char == curses.KEY_DOWN:
            if n == 0:
                return

            if (
                self.body_posy == last_visible and
                self.storage_cursor < max_cursor
            ):
                self.storage_cursor += 1
            
            elif (
                    self.body_posy < last_visible and
                    self.body_posy < n - 1
            ):
                self.body_posy += 1

            if at_last_item():
                self.autoscroll = True

        elif char == curses.KEY_UP:
            if n == 0:
                return

            self.autoscroll = False
            if self.body_posy == 0 and self.storage_cursor > 0:
                self.storage_cursor -= 1
            elif self.body_posy > 0:
                self.body_posy -= 1

        elif char == curses.KEY_HOME:
            self.autoscroll = False
            self.storage_cursor = 0
            self.body_posy = 0

        elif char == curses.KEY_END:
            self.autoscroll = True
            if n == 0:
                self.storage_cursor = 0
                self.body_posy = 0
            else:
                self.storage_cursor = max_cursor
                self.body_posy = min(last_visible, n - 1 - self.storage_cursor)

        elif char == curses.KEY_NPAGE:
            if n == 0:
                return

            self.autoscroll = False

            # If already at/beyond last visible item, jump to END
            if at_last_item():
                self.autoscroll = True
                self.storage_cursor = max_cursor
                self.body_posy = min(last_visible, n - 1 - self.storage_cursor)
                return

            # Otherwise, move down by one page.
            new_abs = min(n - 1, self.storage_cursor + self.body_posy + body_h)
            self.storage_cursor = min(new_abs, max_cursor)
            self.body_posy = body_h #new_abs - self.storage_cursor

            if at_last_item():
                self.autoscroll = True

        elif char == curses.KEY_PPAGE:
            if n == 0:
                return

            self.autoscroll = False

            new_abs = max(0, self.storage_cursor + self.body_posy - body_h)
            self.storage_cursor = min(new_abs, max_cursor)
            self.body_posy = new_abs - self.storage_cursor

    def handle_char(self, char: int) -> None:
        """Handle navigation, workspace switching, and buttons."""
        if char in (9, curses.KEY_BTAB, 8, curses.KEY_BACKSPACE):
            if self.panel.hidden():
                self.display.active_handle_char(char)

            self.stdscr.erase()
            ws_len = max(1, len(self.display.workspaces))

            if char in (9, curses.KEY_BTAB):
                self.display.active_ws_idx = (
                    self.display.active_ws_idx + 1
                ) % ws_len
                if getattr(self.display, "tab", None):
                    self.display.tab.next_tab()

            elif char in (8, curses.KEY_BACKSPACE):
                self.display.active_ws_idx = (
                    self.display.active_ws_idx - 1
                ) % ws_len
                if getattr(self.display, "tab", None):
                    self.display.tab.prev_tab()

            aws = self.display.active_workspace
            if aws:
                try:
                    aws.bodywin.erase()
                except curses.error:
                    pass

                aws.draw()
                aws.panel.top()
                aws.panel.show()
                self.display.active_handle_char = aws.handle_char

            curses.panel.update_panels()
            return

        if char in (
            curses.KEY_UP,
            curses.KEY_DOWN,
            curses.KEY_LEFT,
            curses.KEY_RIGHT,
            curses.KEY_HOME,
            curses.KEY_END,
            curses.KEY_NPAGE,
            curses.KEY_PPAGE,
        ):
            self.cursor_handler(char)
            self.draw_bodywin()
            return

        if char in self.button_map:
            self.button_map[char].toggle(self)
            if self.panel == self.active_panel:
                self.draw()

############################## END WORKSPACE ##################################
############################## BEGIN UTILS ####################################

def get_available_terminal_types() -> List[str]:
    """
    Get list of available terminal types from the system.

    Returns:
        List of strings of available terminal types.
    """
    try:
        output = os.popen("toe -a").read().splitlines()            
        types = [line.split()[0] for line in output if line.strip()]
        return types
    except Exception:
        return []

def change_terminal(to_type="xterm-256color"):
    """
    Change the terminal type environment variable.
    
    Args:
        to_type: The terminal type to change to
        
    Returns:
        The original terminal type
    """
    old_term = os.environ.get("TERM", "")
    available_types = get_available_terminal_types()

    if to_type != old_term:
        if to_type in available_types:
            os.environ["TERM"] = to_type
            logger.info(f"Changed terminal to '{to_type}'")
        else:
            logger.error(f"Terminal {to_type} is not available")

    return old_term

def get_local_ip() -> str:
    """Returns local IP used for the communication with Branch Gateways."""
    command = "netstat -tan | grep ESTABLISHED | grep -E ':(1039|2944|2945)'"
    connections = os.popen(command).read()
    pattern = r"([0-9.]+):1039|2944|2945"

    local_ips = re.findall(pattern, connections)
    if local_ips:
        return local_ips[0]

    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    return local_ip

############################## END UTILS ######################################
############################## BEGIN UI FUNCTIONS #############################
def hide_panel(ws):
    ws.active_panel.panel.hide()
    del ws.active_panel
    ws.panel.top()
    ws.active_panel = ws.panel
    ws.draw(dim=False)
    curses.panel.update_panels()
    curses.doupdate()
    ws.display.active_handle_char = ws.handle_char

    return 1

def make_filterpanel(ws, group):
    
    if not group or FILTER_MENUs.get(group) is None:
        return

    logger.debug("Make filterpanel requested")
    
    storage = FILTER_MENUs[group].splitlines()
    current = FILTER_GROUPs[ws.filter_group]["current_filter"]

    def filter_callback(filter):
        update_filter(group, filter)

    panel = FilterPanel(
        ws.display,
        storage = storage,
        current_filter = current,
        validator = filter_validator,
        callback = filter_callback,
        name = f"FilterPanel({group})"
    )

    ws.draw(dim=True)    
    ws.active_panel = panel
    panel.panel.show()
    panel.panel.top()
    panel.draw()
    is_canceled = panel.handle_char()
    return is_canceled

def discovery_start(ws):
    logger.info("Discovery start requested")

    ws.bodywin.erase()
    ws.draw(dim=True)

    is_canceled = make_filterpanel(ws, "bgw")
    if is_canceled:
        ws.draw()
        return

    GWs.clear()
    BGWs.clear()

    ip_filter = FILTER_GROUPs["bgw"]["groups"]["ip_filter"]
    loop = startup_async_loop()
    progress_queue = Queue(loop=loop)
    
    panel = ProgressBar(
        ws.display,
        queue=progress_queue,
        workspace_chars = [ord("s"), ord("S")]
    )

    def progress_callback(progress_update: Tuple[int, int, int]) -> None:
        """
        Handle progress updates from discovery tasks.

        Args:
            progress_update: A tuple of (ok, err, total) counts.
        """
        nonlocal progress_queue, panel, ws

        progress_queue.put_nowait(progress_update)
        ws.menubar.draw()
        panel.draw()

    task = schedule_task(
        discovery(
            loop=loop,  
            callback=progress_callback,
            ip_filter=ip_filter
        ),
        name="discovery",
        loop=loop,
    )

    def discovery_done_callback(fut: asyncio.Future, ws: Any) -> None:
        if fut.cancelled() or ws.display.loop_shutdown_requested:
            return
        ws.display.update_title(ws.display.title)
        curses.flushinp()
        curses.ungetch(ord("s"))

    task.add_done_callback(partial(discovery_done_callback, ws=ws))

    ws.draw(dim=True)
    ws.active_panel = panel
    panel.panel.show()
    panel.panel.top()
    curses.panel.update_panels()
    curses.doupdate()

    ws.display.loop = loop
    ws.display.active_handle_char = panel.handle_char

    return panel

def discovery_stop(ws):
    logger.info("Discovery stop requested")
    
    loop = ws.display.loop

    if loop:
        ws.display.loop_shutdown_requested = True
        request_shutdown(loop)

    hide_panel(ws)

    return 1

def polling_start(ws):
    logger.info("Polling start requested")
    
    def process_item_callback():
        nonlocal ws
        aws = ws.display.active_workspace
        polling_workspace = any(x.name == "button_polling" for x in aws.buttons)

        if polling_workspace:
            ws.display.update_title(ws.display.title)

            if aws.panel != aws.active_panel:
                rtpdetails = aws.storage.select(aws.storage_cursor + aws.body_posy)
                aws.active_panel.draw(rtpdetails)
            else:
                aws.draw()
            curses.doupdate()
            aws.menubar.draw()

    loop = ws.display.loop

    if loop or not BGWs:
        return

    for bgw in BGWs.values():
        bgw.last_seen_dt = None

    loop = startup_async_loop()
    schedule_http_server(loop=loop)
    schedule_queries(loop=loop, bgws=BGWs, callback=process_item_callback)
    ws.display.loop = loop

    return 1

def polling_stop(ws):
    logger.info("Polling stop requested")
    loop = ws.display.loop
    if loop:
        ws.display.loop_shutdown_requested = True
        request_shutdown(loop)

    return 1

def capture_toggle(ws):
    if not ws.display.loop:
        return

    bgw = ws.storage.select(ws.storage_cursor + ws.body_posy)

    if "running" in bgw.capture_status:
        commands = ["capture stop"]
        status = "stopping"
    elif "stopped" in bgw.capture_status:
        commands = ["clear capture-buffer", "capture start"]
        if not bgw.has_filter_501:
            commands = CONFIG["capture_setup"] + commands[:]
        status = "starting"
    else:
        return

    bgw.queue.put_nowait(commands)
    bgw.packet_capture = status
    logger.info(f"PCAP {status} requested")

    if ws.active_panel == ws.panel:
        if not ws.display.active_workspace.panel.hidden():
            ws.display.active_workspace.draw_bodywin()

    return 1

def capture_upload(ws):
    if not ws.display.loop or not CONFIG.get("http_server"):
        logger.info("HTTP server not configured, request ignored")
        return

    bgw = ws.storage.select(ws.storage_cursor + ws.body_posy)

    if bgw.pcap_upload == "requested":
        return

    http_server = CONFIG.get("http_server", "0.0.0.0")
    http_port = CONFIG.get("http_port")
    upload_dir = CONFIG.get("upload_dir")
    if http_server == "0.0.0.0":
        http_server = get_local_ip()

    dest = f"{http_server}:{http_port}/{upload_dir}"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{bgw.gw_number}.cap"

    command = f"copy capture-file https http://{dest}/{filename}"
    bgw.queue.put_nowait(command)
    bgw.pcap_upload = "requested"
    logger.info(f"PCAP upload '{command}' requested")

    if ws.active_panel == ws.panel:
        if not ws.display.active_workspace.panel.hidden():
            ws.display.active_workspace.draw_bodywin()

    return 1

def clear_storage(ws):

    if not ws.storage:
        return

    def clear_storage_callback(char: int) -> None:
        nonlocal ws
        if char in (ord("y"), ord("Y")):
            ws.storage.clear()
            if ws.storage.name == "BGWs":
                GWs.clear()
        hide_panel(ws)

    logger.info("Clear storage requested")
    panel = Confirmation(ws.display, callback=clear_storage_callback)

    ws.draw(dim=True)    
    ws.active_panel = panel
    panel.panel.show()
    panel.panel.top()
    panel.draw()
    curses.panel.update_panels()
    curses.doupdate()
    ws.display.active_handle_char = panel.handle_char

    return panel

def make_textpanel(ws, *attr_names):
    bgw = ws.storage.select(ws.storage_cursor + ws.body_posy)

    if bgw is None:
        return

    logger.info("Make textpanel requested")

    storage = []
    for attr_name in attr_names:
        if not hasattr(bgw, attr_name):
            continue
        attr = str(getattr(bgw, attr_name)).strip()
        storage.extend(["", f"COMMAND: {attr_name}", ""])
        storage.extend([x.rstrip() for x in attr.splitlines()])

    if not storage:
        return

    panel = TextPanel(
        display = ws.display,
        storage = storage,
        name = f"TextPanel({attr})",
    )

    ws.draw(dim=True)    
    ws.active_panel = panel
    panel.panel.show()
    panel.panel.top()
    panel.draw()
    curses.panel.update_panels()
    curses.doupdate()
    ws.display.active_handle_char = panel.handle_char

    return panel

def show_system(ws):
    panel = make_textpanel(ws, "show_system")
    return panel if panel else None

def show_mg_list(ws):
    panel = make_textpanel(ws, "show_mg_list")
    return panel if panel else None

def show_port(ws):
    panel = make_textpanel(ws, "show_port")
    return panel if panel else None

def show_config(ws):
    panel = make_textpanel(ws,
            "show_running_config",
            "show_sla_monitor"
        )
    return panel if panel else None

def show_status(ws):
    panel = make_textpanel(ws,
        "show_rtp_stat_summary",
        "show_voip_dsp",
        "show_utilization",
        "show_capture"
    )
    return panel if panel else None

def show_misc(ws):
    panel = make_textpanel(ws,
        "show_temp",
        "show_faults",
        "show_announcements_files"
    )
    return panel if panel else None

def show_rtp(ws):
    rtpdetails = ws.storage.select(ws.storage_cursor + ws.body_posy)

    if not rtpdetails:
        return

    logger.info("Show RTP objectpanel requested")

    rtp_attr_iter = partial(
        iter_attrs,
        spec=RTP_LAYOUT,
        colors=COLORS,
        xoffset=0,
        yoffset=0,
        default_y=0,
        header=False,
    )

    panel = ObjectPanel(
        display=ws.display,
        obj=rtpdetails,
        attr_iterator=rtp_attr_iter,
        name = "ObjectPanel(RTP)"
    )

    ws.draw(dim=True)    
    ws.active_panel = panel
    panel.panel.show()
    panel.panel.top()
    panel.draw()
    curses.panel.update_panels()
    curses.doupdate()
    ws.display.active_handle_char = panel.handle_char

    return panel

def show_pcap(ws):
    capture = ws.storage.select(ws.storage_cursor + ws.body_posy)

    if not capture:
        return

    logger.info("Show PCAP textpanel requested")

    panel = TextPanel(
        display = ws.display,
        storage = capture.rtpinfos.splitlines(),
        name = "TextPanel(PCAP)",
    )

    ws.draw(dim=True)    
    ws.active_panel = panel
    panel.panel.show()
    panel.panel.top()
    panel.draw()
    curses.panel.update_panels()
    curses.doupdate()
    ws.display.active_handle_char = panel.handle_char

    return panel

############################## END UI FUNCTIONS ###############################
############################## BEGIN MAIN #####################################

def main(stdscr, miny: int=24, minx: int=80):
        curses.start_color()
        curses.use_default_colors()

        def must_resize(stdscr, miny, minx):
            maxy, maxx = stdscr.getmaxyx()

            if maxy >= miny and maxx >= minx:
                return False

            lines = (
                f"Resize screen to  {miny}x{minx}",
                f"Current size      {maxy}x{maxx}",
                "Press 'q' to exit",
            )

            yoffset = max(0, maxy // 2 - 2)
            try:
                for i, line in enumerate(lines):
                    xoffset = max(0, (maxx - len(line)) // 2)
                    stdscr.addstr(yoffset + 2*i, xoffset, line)
            except curses.error:
                pass

            stdscr.box()
            stdscr.refresh()
            return True

        while must_resize(stdscr, miny, minx):
            char = stdscr.getch()
            if char == curses.ERR:
                time.sleep(0.1)
            elif char == curses.KEY_RESIZE:
                stdscr.erase()
            elif chr(char) in ("q", "Q"):
                return

        stdscr.erase()
        stdscr.refresh()
        stdscr.resize(miny, minx)

        mydisplay = MyDisplay(stdscr, miny=miny, minx=minx)

        button_discovery = Button(
            char_int = ord("s"),
            func_on = discovery_start,
            label_on = "Stop  Disc",
            label_off = "Start Disc",
            func_off = discovery_stop,
            status_label = "Discovery",
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_polling = Button(
            char_int = ord("s"),
            func_on = polling_start,
            label_on = "Stop Poll",
            label_off = "Start Poll",
            func_off = polling_stop,
            status_label = " Polling ",
            status_color_on = 66304,
            status_color_off = 68096,
            name = "button_polling"
        )

        button_clear_storage = Button(
            char_int = ord("c"),
            func_on = clear_storage,
            label_on = "Clear RTP",
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_system = Button(
            char_int = ord("\n"),
            func_on = show_system,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_misc = Button(
            char_int = ord("\n"),
            func_on = show_misc,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_mg_list = Button(
            char_int = ord("\n"),
            func_on = show_mg_list,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_port = Button(
            char_int = ord("\n"),
            func_on = show_port,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_config = Button(
            char_int = ord("\n"),
            func_on = show_config,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_pcap = Button(
            char_int = ord("\n"),
            func_on = show_pcap,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_status = Button(
            char_int = ord("\n"),
            func_on = show_status,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_rtp = Button(
            char_int = ord("\n"),
            func_on = show_rtp,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_capture = Button(
            char_int = ord("t"),
            func_on = capture_toggle,
            label_on = "Toggle PCAP",
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_upload = Button(
            char_int = ord("u"),
            func_on = capture_upload,
            label_on = "Upload PCAP",
            status_color_on = 66304,
            status_color_off = 68096
        )
        
        workspaces = [
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["SYSTEM"]),
                buttons=[
                    button_discovery,
                    button_show_system
                ],
                storage=BGWs,
                name="SYSTEM",
                filter_group="bgw"
            ),
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["MISC"]),
                buttons=[
                    button_discovery,
                    button_show_misc
                ],
                storage=BGWs,
                name="MISC",
                filter_group="bgw"
            ),
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["MODULE"]),
                buttons=[
                    button_discovery,
                    button_show_mg_list
                ],
                storage=BGWs,
                name="MODULE",
                filter_group="bgw"
            ),
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["PORT"]),
                buttons=[
                    button_discovery,
                    button_show_port
                ],
                storage=BGWs,
                name="PORT",
                filter_group="bgw"
            ),
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["CONFIG"]),
                buttons=[
                    button_discovery,
                    button_show_config
                ],
                storage=BGWs,
                name="CONFIG",
                filter_group="bgw"
            ),
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["STATUS"]),
                buttons=[
                    button_polling,
                    button_show_status,
                    button_capture,
                    button_upload
                ],
                storage=BGWs,
                name="STATUS",
                filter_group="bgw"
            ),
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["RTPSTATS"]),
                buttons=[
                    button_polling,
                    button_show_rtp,
                    button_clear_storage
                ],
                storage=RTPs,
                name="RTPSTATS",
            ),
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["PCAP"]),
                buttons=[
                    button_show_pcap
                ],
                storage=PCAPs,
                name="PCAP",
                filter_group=None
            )
        ]

        mydisplay.workspaces = workspaces
        mydisplay.run()

############################## END MAIN ######################################

def get_user() -> str:
    """Prompt user for SSH username of gateways.

    Returns:
        str: The input string of SSH username.
    """
    while True:
        user = input("Enter SSH user of media-gateways: ")
        user = user.strip()
        confirm = input(f"Is '{user}' correct (Y/N)?: ")
        if confirm.lower().startswith("y"):
            break
    return user

def get_passwd() -> str:
    """Prompt user for SSH password of gateways.

    Returns:
        str: The input string of SSH password.
    """
    while True:
        passwd = input("Enter SSH password of media-gateways: ")
        passwd = passwd.strip()
        confirm = input(f"Is '{passwd}' correct (Y/N)?: ")
        if confirm.lower().startswith("y"):
            break
    return passwd

@contextmanager
def terminal_context(term_type="xterm-256color"):
    """
    Context manager to temporarily change terminal type.
    
    Args:
        term_type: The terminal type to change to
    """
    old_term = change_terminal(term_type)
    old_locale = locale.setlocale(locale.LC_ALL, None)

    try:
        locale.setlocale(locale.LC_ALL, "")
        yield

    finally:
        try:
            locale.setlocale(locale.LC_ALL, old_locale)
        except locale.Error as e:
            logger.error(f"Failed to restore locale {old_locale}: {e}")

        if term_type != old_term:
            os.environ["TERM"] = old_term
            logger.info(f"Changed terminal to '{old_term}'")

@contextmanager
def application_context(CONFIG):
    """
    Context manager to handle application startup and shutdown.
    
    Sets up logging, configures terminal, and ensures proper cleanup.
    """
    # Set up logging
    loglevel = CONFIG["loglevel"].upper()

    if loglevel not in ("NOTSET", "DISABLED", "NONE"):
        logging.basicConfig(
            format=LOG_FORMAT,
            filename=CONFIG["logfile"],
            level=loglevel
        )
    else:
        logging.disable(logging.CRITICAL)

    # Save terminal state for restoration
    fd = sys.stdin.fileno()
    orig_term = termios.tcgetattr(fd)

    try:
        yield
    finally:
        print("Shutting down")
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, orig_term)
            curses.endwin()
        except:
            pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Monitors Avaya Gateways')
    parser.add_argument('-u', dest='user',
                        default=CONFIG.get('user', ''),
                        help='SSH user of the G4xx Gateway')
    parser.add_argument('-p', dest='passwd',
                        default=CONFIG.get('passwd', ''),
                        help='SSH password of the G4xx Gateway')
    parser.add_argument('-n', dest='polling_secs',
                        default=CONFIG.get('polling_secs', 20),
                        help='Polling frequency, default 20s')
    parser.add_argument('-m', dest='max_polling',
                        default=CONFIG.get('max_polling', 20),
                        help='Max simultaneous polling sessions, default 20')
    parser.add_argument('-t', dest='timeout',
                        default=CONFIG.get('timeout', 20),
                        help='Query timeout, default 20s')
    parser.add_argument('-i', dest='ip_filter', metavar='IP',
                        default="",
                        help='IP of gateways to discover, default empty')
    parser.add_argument('-l', dest='storage_maxlen',
                        default=CONFIG.get('storage_maxlen', 999),
                        help='max number of RTP stats to store, default 999')
    parser.add_argument('--http-server', dest='http_server',
                        default=CONFIG.get('http_server', ''),
                        help='HTTP server IP, default 0.0.0.0')
    parser.add_argument('--http-port', dest='http_port',
                        default=CONFIG.get('http_port', 8080),
                        help='HTTP server port, default 8080')
    parser.add_argument('--upload_dir', dest='upload_dir',
                        default=CONFIG.get('upload_dir', '/tmp'),
                        help='PCAP Upload directory, default /tmp')
    parser.add_argument('--no-http', dest='no_http', action='store_true',
                        default=False,
                        help='Don\'t run HTTP server, default False')
    parser.add_argument('--nok-rtp-only', dest='nok_rtp_only',
                        action='store_true',
                        default=CONFIG.get('nok_rtp_only', False),
                        help='Store only NOK RTPs, default False')
    parser.add_argument('--loglevel', dest='loglevel',
                        default=CONFIG.get('loglevel', 'NOTSET'),
                        help='loglevel, default NOTSET (no logging)')
    parser.add_argument('--logfile', dest='logfile',
                        default=CONFIG.get('logfile', 'monitorBGW.log'),
                        help='log file, default monitorBGW.log')
    args = parser.parse_args()

    if not args.user:
        args.user = get_user()
    if not args.passwd:
        args.passwd = get_passwd()

    if args.no_http:
        args.http_server = ""

    CONFIG.update(vars(args))
    RTPs.maxlen = int(args.storage_maxlen)

    if args.ip_filter:
        filter = f"-i {args.ip_filter}"
        if filter_validator(filter) is None:
            update_filter("bgw", filter)

    with application_context(CONFIG):
        with terminal_context("xterm-256color"):
            try:
                curses.wrapper(main)
            except (KeyboardInterrupt, SystemExit):
                logger.info("Application terminated by user")
            except Exception as e:
                logger.exception("Unhandled exception:")
                print(f"\nError: {e}", file=sys.stderr)
                sys.exit(1)
            else:
                logger.info("Application exited normally")
