#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS ##################################

import re
from typing import Optional, Any, Dict, Set
from asyncio import Queue
from datetime import datetime
import logging
logger = logging.getLogger(__name__)

############################## END IMPORTS ####################################
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

        matches = re.findall(r"(.*Avaya Inc)", self.show_port)
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

if __name__ == "__main__":
    bgw = BGW(**{'lan_ip': '10.10.48.58', 'proto': 'ptls', 'polling_secs': 10, 'gw_name': 'AvayaG450A', 'gw_number': '001', 'polls': 1, 'avg_poll_secs': 10, 'active_session_ids': set(), 'last_seen': datetime(2025, 12, 16, 14, 33, 39), 'last_session_id': '', 'show_announcements_files': '\r\n ID      File               Description    Size (Bytes)      Date\r\n---- ------------------ ------------------ ------------ -------------------\r\n101   moh.wav            announcement file      239798    2022-08-23,8:45:26  \r\n102   emergency.wav      announcement file       26618    2023-03-24,11:36:10 \r\n103   public_announceme  announcement file      201914    2024-10-24,7:37:52  \r\n104   mohtest.wav        announcement file     9648106    2025-07-15,14:50:16 \r\n\r\nNv-Ram:\r\nTotal bytes used             : 10119680  \r\nTotal bytes free             : 12672000  \r\nTotal bytes capacity (fixed) : 22791680', 'show_capture': '\r\n\r\nCapture service is enabled and active\r\nCapture start time 09/12/2025-09:25:13\r\nCapture stop time not-stopped\r\nCurrent buffer size is 1024 KB\r\nBuffer mode is non-cyclic\r\nMaximum number of bytes captured from each frame: 4096\r\nCapture list 501 on all interfaces\r\nCapture IPSec decrypted\r\nNumber of captured frames in file: 604 (out of 145200 total captured frames)\r\nMemory buffer occupancy: 4.62% (including overheads)', 'show_faults': '\r\n\r\nCURRENTLY ACTIVE FAULTS\r\n--------------------------------------------------------------------------\r\n\r\n-- Media Module Faults --\r\n\t+ Insertion failure, mmid = v5, 11/24-07:37:04.00\r\n\r\nCurrent Alarm Indications, ALM LED is off\r\n--------------------------------------------------------------------------\r\nNone', 'show_lldp_config': '\r\n\r\nLldp Configuration \r\n-------------------\r\nApplication status: disable \r\nTx interval: 30 seconds\r\nTx hold multiplier: 4 seconds\r\nTx delay: 2 seconds\r\nReinit delay: 2 seconds', 'show_mg_list': '\r\nSLOT   TYPE         CODE        SUFFIX  HW VINTAGE  FW VINTAGE \r\n----   --------     ----------  ------  ----------  -----------\r\nv1     -- Not Installed --\r\nv2     -- Not Installed --\r\nv3     E1T1         MM710       B       16          52\r\nv4     -- Not Installed --\r\nv5     -- Initializing --\r\nv6     Analog       MM714       B       23          94\r\nv7     -- Not Installed --\r\nv8     -- Not Installed --\r\nv10    Mainboard    G450        B       2           42.36.0(A)', 'show_port': '\r\nPort   Name             Status    Vlan Level  Neg     Dup. Spd. Type\r\n------ ---------------- --------- ---- ------ ------- ---- ---- ----------------\r\n10/5   NO NAME          connected 1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/5\r\n\r\n10/6   NO NAME          no link   1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/6', 'show_rtp_stat_summary': '', 'show_running_config': '\r\n\r\n! version 42.36.0\r\nConfig info release 42.36.0 time "13:33:51 16 DEC 2025 " serial_number 10IS41452851\r\n !\r\nencrypted-username +ikJzwEP/t+XkAlH3l+zsw== password G6uSyomIZMSDb0NnT4RwvSb4IrSGUtuQ9ypCGFikR4w= access-type fe/kaDE5GWBC9Nfj6bNkgA==\r\n!\r\nencrypted-username mJ6sF5BOZeIUWsyCb3C1bw== password 8tMk4PMmywAU0cVXzSERF/aaj9WF0EAq4dB4c0qOLbU= access-type gf0PKwZMZRJ4zRba06ZC3w==\r\nhostname "AvayaG450A"\r\nset system location "Calgary" \r\nno ip telnet \r\nip tftp-server file-system-size 2288\r\nset port mirror source-port 10/5 mirror-port 10/6 sampling always direction both\r\n!\r\nip capture-list 501\r\n name "udp"\r\n!\r\n ip-rule 1\r\n  ip-protocol udp\r\n exit\r\n ip-rule default\r\n  composite-operation "No-Capture"\r\n exit\r\n!\r\nexit\r\n!\r\nds-mode t1\r\n!\r\ninterface Vlan 1\r\n icc-vlan\r\n server-blade-vlan 5\r\n ip address 10.10.48.58     255.255.255.0  \r\n pmi\r\n exit\r\n!\r\ninterface FastEthernet 10/3\r\n exit\r\n!\r\ninterface FastEthernet 10/4\r\n exit\r\n!\r\ninterface Console\r\n speed 9600\r\n exit\r\n!\r\ninterface USB-Modem\r\n description "Default Modem Setup"\r\n timeout absolute 10\r\n ppp authentication ras\r\n no shutdown\r\n ip address 10.3.248.253    255.255.255.252\r\n exit\r\n!\r\ncapture max-frame-size 4096\r\ncapture buffer-mode non-cyclic\r\ncapture filter-group 501\r\nlogin authentication min-password-length 8\r\n!\r\nlogin authentication lockout 0 attempt 0\r\n! Avaya Login Confirmation Received.\r\nEASGManage enableEASG\r\nproduct-id 8c2ae2eead3e6cca800be892bb6e3411\r\n!\r\nset logging file enable \r\nset logging file condition all Error \r\nset logging file condition BOOT Debug \r\n!\r\nno snmp-server community \r\nencrypted-snmp-server user JSXE8Ccs0N0TnuoQek8jwLmaP391mjHjbt9glvbZ2M0= gAAa6QMAG08/c+A= v3ReadISO v3 auth sha 1FCIRMijXV+77fer97/S9O3FlfqIPrTOC5uTFcklYM8=  priv aes128 yyv5YmpCoEn5xZ24B7MR4Y03gnnqwygOY3eQTGRZZB0= \r\nencrypted-snmp-server user 0Ce9aP8Q25tEoXTe0YGwKmt2qLFQJ+UOpG6SMzseQdg= gAAa6QMAG08/c+A= v3TrapISO v3 auth sha TgX0mUpViHn56rSWounTurOYUdreS7rWWY7KssAnYj4=  priv aes128 p5Rdzsia/+4+Uc7f9oeJOj38gI6qX+2Fy1WDL5PTkh8= \r\nsnmp-server group v3ReadISO v3 priv read iso  \r\nsnmp-server group v3TrapISO v3 priv notify iso  \r\nsnmp-server host 10.10.48.92 traps v3 priv bbysnmpv3trap \r\n!\r\nip default-gateway 10.10.48.254    1 low  \r\n!\r\nset sync interface primary v3\r\nset sync source primary\r\nrtp-stat-service\r\nrtp-stat fault\r\nanalog-test\r\nexit\r\n!\r\nset sla-monitor enable\r\nset sla-server-ip-address 10.10.48.198\r\nudp keepalive 10\r\nset mgc list 10.10.48.240\r\nset mediaserver 10.10.48.240 10.10.48.240 23 telnet\r\nset mediaserver 10.10.48.240 10.10.48.240 5023 sat\r\n!#\r\n!# End of configuration file. Press Enter to continue.', 'show_sla_monitor': '\r\n\r\nSLA Monitor:                  Enabled\r\nRegistered Server IP Address: 0.0.0.0\r\nRegistered Server IP Port:    0\r\nConfigured Server IP Address: 10.10.48.198\r\nConfigured Server IP Port:    50011\r\nCapture Mode:                 None\r\nVersion:                      2.7.0', 'show_system': '\r\nSystem Name             : \r\nSystem Location         : Calgary\r\nSystem Contact          : \r\nUptime (d,h:m:s)        : 22,06:00:13\r\nCall Controller Time    : 13:33:56 16 DEC 2025 \r\nSerial No               : 13TG01116522\r\nModel                   : G450\r\nChassis HW Vintage      : 1\r\nChassis HW Suffix       : A\r\nMainboard HW Vintage    : 2\r\nMainboard HW Suffix     : B\r\nMainboard HW CS         : 2.1.7\r\nMainboard FW Vintage    : 42.36.0\r\nLAN MAC Address         : 00:1b:4f:3f:73:e0\r\nWAN1 MAC Address        : 00:1b:4f:3f:73:e1\r\nWAN2 MAC Address        : 00:1b:4f:3f:73:e2\r\nSERVICES MAC address    : 00:1b:4f:3f:73:e3\r\nMemory #1               : 256MB\r\nMemory #2               : Not present\r\nCompact Flash Memory    : No CompactFlash card is installed\r\nPSU #1                  : AC 400W\r\nPSU #2                  : Not present\r\nMedia Socket #1         : MP160 VoIP DSP Module\r\nMedia Socket #2         : Not present\r\nMedia Socket #3         : Not present\r\nMedia Socket #4         : Not present\r\nFAN Tray                : Present', 'show_temp': '\r\nAmbient\r\n-------\r\nTemperature : 36C (97F)\r\nHigh Warning: 42C (108F)\r\nLow Warning : -5C (23F)', 'show_utilization': '\r\n\r\nMod   CPU      CPU     RAM      RAM\r\n      5sec     60sec   used(%)  Total(Kb)\r\n---   ------   -----  -------  ----------\r\n10    Appl. Disabled    48%     190838 Kb', 'show_voip_dsp': '\r\nDSP #1 PARAMETERS\r\n--------------------------------------------------------------\r\nBoard type     : MP160\r\nHw Vintage     : 0 B\r\nFw Vintage     : 182\r\n\r\nDSP#1 CURRENT STATE\r\n--------------------------------------------------------------\r\nIn Use         : 0 of 160 channels, 0 of 4800 points (0.0% used)\r\nState          : Idle\r\nAdmin State    : Release\r\n\r\nCore# Channels Admin     State\r\n      In Use   State\r\n----- -------- --------- -------\r\n    1  0 of 40   Release Idle\r\n    2  0 of 40   Release Idle\r\n    3  0 of 40   Release Idle\r\n    4  0 of 40   Release Idle\r\n\r\n\r\nDSP #2 Not Present\r\n\r\n\r\nDSP #3 Not Present\r\n\r\n\r\nDSP #4 Not Present', 'queue': Queue(), '_active_session': None, '_announcements': None, '_capture_service': None, '_chassis_hw': None, '_comp_flash': None, '_cpu_util': None, '_dsp': None, '_faults': None, '_fw': None, '_hw': None, '_inuse_dsp': None, '_last_seen_time': None, '_lldp': None, '_location': None, '_mac': None, '_mainboard_hw': None, '_memory': None, '_mm_groupdict': None, '_mm_v1': None, '_mm_v2': None, '_mm_v3': None, '_mm_v4': None, '_mm_v5': None, '_mm_v6': None, '_mm_v7': None, '_mm_v8': None, '_mm_v10': None, '_model': None, '_port1': None, '_port1_status': None, '_port1_neg': None, '_port1_duplex': None, '_port1_speed': None, '_port2': None, '_port2_status': None, '_port2_neg': None, '_port2_duplex': None, '_port2_speed': None, '_port_redu': None, '_psu1': None, '_psu2': None, '_ram_util': None, '_rtp_stat_service': None, '_serial': None, '_slamon_service': None, '_sla_server': None, '_snmp': None, '_snmp_trap': None, '_temp': None, '_total_session': None, '_uptime': None})
    print(bgw)
