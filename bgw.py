#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS #################################

import re
from typing import (
    Optional,
    Any,
    Dict,
)
from queue import Queue
from datetime import datetime

############################## END IMPORTS ###################################
############################## BEGIN CLASSES #################################

class BGW:
    def __init__(
        self,
        bgw_ip: str,
        proto: str = "",
        polling_secs=10,
        bgw_name: str = "",
        bgw_number: str = "",
        show_announcements_files: str = "",
        show_capture: str = "",
        show_faults: str = "",
        show_lldp_config: str = "",
        show_mg_list: str = "",
        show_port: str = "",
        show_rtp_stat_summary: str = "",
        show_running_config: str = "",
        show_sla_monitor: str = "",
        show_system: str = "",
        show_temp: str = "",
        show_utilization: str = "",
        show_voip_dsp: str = "",
        **kwargs,
    ) -> None:
        self.bgw_ip = bgw_ip
        self.proto = proto
        self.polling_secs = polling_secs
        self.bgw_name = bgw_name
        self.bgw_number = bgw_number
        self.polls = 0
        self.avg_poll_secs = 0
        self.active_session_ids = set()
        self.last_seen = ""
        self.last_seen_dt: Optional[datetime] = None
        self.last_session_id: Optional[str] = None
        self.show_announcements_files = show_announcements_files
        self.show_capture = show_capture
        self.show_faults = show_faults
        self.show_lldp_config = show_lldp_config
        self.show_mg_list = show_mg_list
        self.show_port = show_port
        self.show_rtp_stat_summary = show_rtp_stat_summary
        self.show_running_config = show_running_config
        self.show_sla_monitor = show_sla_monitor
        self.show_system = show_system
        self.show_temp = show_temp
        self.show_utilization = show_utilization
        self.show_voip_dsp = show_voip_dsp
        self.queue = Queue()
        self._active_session = None
        self._announcements = None
        self._capture_service = None
        self._chassis_hw = None
        self._comp_flash = None
        self._cpu_util = None
        self._dsp = None
        self._faults = None
        self._fw = None
        self._hw = None
        self._inuse_dsp = None
        self._last_seen_time = None
        self._lldp = None
        self._location = None
        self._mac = None
        self._mainboard_hw = None
        self._memory = None
        self._mm_groupdict = None
        self._mm_v1 = None
        self._mm_v2 = None
        self._mm_v3 = None
        self._mm_v4 = None
        self._mm_v5 = None
        self._mm_v6 = None
        self._mm_v7 = None
        self._mm_v8 = None
        self._mm_v10 = None
        self._model = None
        self._port1 = None
        self._port1_status = None
        self._port1_neg = None
        self._port1_duplex = None
        self._port1_speed = None
        self._port2 = None
        self._port2_status = None
        self._port2_neg = None
        self._port2_duplex = None
        self._port2_speed = None
        self._port_redu = None
        self._psu1 = None
        self._psu2 = None
        self._ram_util = None
        self._rtp_stat_service = None
        self._serial = None
        self._slamon_service = None
        self._sla_server = None
        self._snmp = None
        self._snmp_trap = None
        self._temp = None
        self._total_session = None
        self._uptime = None

    @property
    def active_session(self) -> str:
        """
        Returns the Active Session column from the RTP-Stat summary.
        """
        if self.show_rtp_stat_summary:
            m = re.search(r"nal\s+\S+\s+(\S+)", self.show_rtp_stat_summary)
            return m.group(1) if m else "?/?"
        return "NA"

    @property
    def announcements(self) -> str:
        """
        Returns the number of announcement files as a string.
        """
        if self.show_announcements_files:
            if self._announcements is None:
                m = re.findall(
                    r"announcement file", self.show_announcements_files
                )
                self._announcements = str(len(m))
            return self._announcements
        return "NA"

    @property
    def capture_service(self) -> str:
        """
        Returns the capture service admin and running state.
        """
        if self.show_capture:
            if self._capture_service is None:
                m = re.search(r" service is (\w+) and (\w+)", self.show_capture)
                admin_state = m.group(1) if m else "?"
                running_state = m.group(2) if m else "?"
                if admin_state == "disabled":
                    self._capture_service = "disabled"
                else:
                    self._capture_service = f"{admin_state}/{running_state}"
            return self._capture_service
        return "NA"

    @property
    def chassis_hw(self) -> str:
        """
        Returns the chassis hardware version as a string.
        """
        if self.show_system:
            if self._chassis_hw is None:
                vintage_search = re.search(
                    r"Chassis HW Vintage\s+:\s+(\S+)", self.show_system
                )
                vintage = vintage_search.group(1) if vintage_search else "?"

                suffix_search = re.search(
                    r"Chassis HW Suffix\s+:\s+(\S+)", self.show_system
                )
                suffix = suffix_search.group(1) if suffix_search else "?"

                self._chassis_hw = f"{vintage}{suffix}"
            return self._chassis_hw
        return "NA"

    @property
    def comp_flash(self) -> str:
        """
        Returns the compact flash memory if installed.
        """
        if self.show_system:
            if self._comp_flash is None:
                m = re.search(r"Flash Memory\s+:\s+(.*)", self.show_system)
                if m:
                    if "No" in m.group(1):
                        self._comp_flash = ""
                    else:
                        self._comp_flash = m.group(1).replace(" ", "")
                else:
                    self._comp_flash = ""
            return self._comp_flash
        return "NA"

    @property
    def cpu_util(self) -> str:
        """
        Returns the last 5s and 60s CPU utilization as a string in percentage.
        """
        if self.show_utilization:
            m = re.search(r"10\s+(\d+)%\s+(\d+)%", self.show_utilization)
            self._cpu_util = f"{m.group(1)}%/{m.group(2)}%" if m else "?/?"
            return self._cpu_util
        return "NA"

    @property
    def dsp(self) -> str:
        """
        Returns the total number of DSPs as a string.
        """
        if self.show_system:
            if self._dsp is None:
                m = re.findall(
                    r"Media Socket .*?: M?P?(\d+) ", self.show_system
                )
                self._dsp = str(sum(int(x) for x in m)) if m else "?"
            return self._dsp
        return "NA"

    @property
    def faults(self) -> str:
        """
        Returns the number of faults as string.
        """
        if self.show_faults:
            if self._faults is None:
                if "No Fault Messages" in self.show_faults:
                    self._faults = 0
                else:
                    m = re.findall(r"\s+\+ (\S+)", self.show_faults)
                    self._faults = len(m)
            return str(self._faults)
        return "NA"

    @property
    def fw(self) -> str:
        """
        Returns the firmware version as a string.
        """
        if self.show_system:
            if self._fw is None:
                m = re.search(r"FW Vintage\s+:\s+(\S+)", self.show_system)
                self._fw = m.group(1) if m else "?"
            return self._fw
        return "NA"

    @property
    def hw(self) -> str:
        """
        Returns the hardware version as a string.
        """
        if self.show_system:
            if self._hw is None:
                m = re.search(r"HW Vintage\s+:\s+(\S+)", self.show_system)
                hw_vintage = m.group(1) if m else "?"
                m = re.search(r"HW Suffix\s+:\s+(\S+)", self.show_system)
                hw_suffix = m.group(1) if m else "?"
                self._hw = f"{hw_vintage}{hw_suffix}"
            return self._hw
        return "NA"

    @property
    def last_seen_time(self) -> str:
        """
        Returns the last seen time as a string in 24h format.
        """
        if self.last_seen:
            return f"{self.last_seen:{'%H:%M:%S'}}"
        return "NA"

    @property
    def lldp(self) -> str:
        """
        Returns the LLDP configuration state.
        """
        if self.show_lldp_config:
            if self._lldp is None:
                if "Application status: disable" in self.show_lldp_config:
                    self._lldp = "disabled"
                else:
                    self._lldp = "enabled"
            return self._lldp
        return "NA"

    @property
    def location(self) -> str:
        """
        Returns the system location as a string.
        """
        if self.show_system:
            if self._location is None:
                m = re.search(r"System Location\s+:\s+(\S+)", self.show_system)
                self._location = m.group(1) if m else ""
            return self._location
        return "NA"

    @property
    def mac(self) -> str:
        """
        Returns the LAN MAC address as a string, without colons.
        """
        if self.show_system:
            if self._mac is None:
                m = re.search(r"LAN MAC Address\s+:\s+(\S+)", self.show_system)
                self._mac = m.group(1).replace(":", "") if m else "?"
            return self._mac
        return "NA"

    @property
    def mainboard_hw(self) -> str:
        """
        Returns the mainboard hardware version as a string.
        """
        if self.show_system:
            if self._mainboard_hw is None:
                vintage = re.search(
                    r"Mainboard HW Vintage\s+:\s+(\S+)", self.show_system
                )
                vintage = vintage.group(1) if vintage else "?"

                suffix = re.search(
                    r"Mainboard HW Suffix\s+:\s+(\S+)", self.show_system
                )
                suffix = suffix.group(1) if suffix else "?"

                self._mainboard_hw = f"{vintage}{suffix}"
            return self._mainboard_hw
        return "NA"

    @property
    def memory(self) -> str:
        """
        Returns the total memory as a string in the format "<number>MB".
        """
        if self.show_system:
            if self._memory is None:
                m = re.findall(r"Memory #\d+\s+:\s+(\S+)", self.show_system)
                self._memory = f"{sum(self._to_mbyte(x) for x in m)}MB"
            return self._memory
        return "NA"

    @property
    def mm_groupdict(self) -> Dict[str, Dict[str, str]]:
        """
        Returns a dictionary of module group information.

        Returns:
            Dict[str, Dict[str, str]]: A dictionary where each key is a slot
            and the corresponding values are a dictionary containing module
            details.
        """
        if self._mm_groupdict:
            return self._mm_groupdict

        if self.show_mg_list:
            groupdict: Dict[str, Dict[str, str]] = {}
            for text in (ln.strip() for ln in self.show_mg_list.splitlines()):
                if text.startswith("v") and "Not Installed" not in text:
                    m = re.search(
                        r"".join(
                            (
                                r".*?(?P<slot>\S+)",
                                r".*?(?P<type>\S+)",
                                r".*?(?P<code>\S+)",
                                r".*?(?P<suffix>\S+)",
                                r".*?(?P<hw_vint>\S+)",
                                r".*?(?P<fw_vint>\S+)",
                            )
                        ),
                        text,
                    )
                    if m:
                        groupdict.update({m.group("slot"): m.groupdict()})
            self._mm_groupdict = groupdict
            return self._mm_groupdict
        return {}

    def _mm_v(self, slot: int) -> str:
        """
        Retrieves the module code and suffix for the given slot.

        Args:
            slot: The slot number to retrieve the module details for.

        Returns:
            str: The module details for the given slot.
        """
        code = self.mm_groupdict.get(f"v{slot}", {}).get("code", "")
        if code == "ICC":
            code = self.mm_groupdict.get(f"v{slot}", {}).get("type", "")
        suffix = self.mm_groupdict.get(f"v{slot}", {}).get("suffix", "")
        return f"{code}{suffix}"

    @property
    def mm_v1(self) -> str:
        """
        Returns the media module code and suffix for slot 1.
        """
        if self.show_mg_list:
            if self._mm_v1 is None:
                self._mm_v1 = self._mm_v(1)
            return self._mm_v1
        return "NA"

    @property
    def mm_v2(self) -> str:
        """
        Returns the media module code and suffix for slot 2.
        """
        if self.show_mg_list:
            if self._mm_v2 is None:
                self._mm_v2 = self._mm_v(2)
            return self._mm_v2
        return "NA"

    @property
    def mm_v3(self) -> str:
        """
        Returns the media module code and suffix for slot 3.
        """
        if self.show_mg_list:
            if self._mm_v3 is None:
                self._mm_v3 = self._mm_v(3)
            return self._mm_v3
        return "NA"

    @property
    def mm_v4(self) -> str:
        """
        Returns the media module code and suffix for slot 4.
        """
        if self.show_mg_list:
            if self._mm_v4 is None:
                self._mm_v4 = self._mm_v(4)
            return self._mm_v4
        return "NA"

    @property
    def mm_v5(self) -> str:
        """
        Returns the media module code and suffix for slot 5.
        """
        if self.show_mg_list:
            if self._mm_v5 is None:
                self._mm_v5 = self._mm_v(5)
            return self._mm_v5
        return "NA"

    @property
    def mm_v6(self) -> str:
        """
        Returns the media module code and suffix for slot 6.
        """
        if self.show_mg_list:
            if self._mm_v6 is None:
                self._mm_v6 = self._mm_v(6)
            return self._mm_v6
        return "NA"

    @property
    def mm_v7(self) -> str:
        """
        Returns the media module code and suffix for slot 7.
        """
        if self.show_mg_list:
            if self._mm_v7 is None:
                self._mm_v7 = self._mm_v(7)
            return self._mm_v7
        return "NA"

    @property
    def mm_v8(self) -> str:
        """
        Returns the media module code and suffix for slot 8.
        """
        if self.show_mg_list:
            if self._mm_v8 is None:
                self._mm_v8 = self._mm_v(8)
            return self._mm_v8
        return "NA"

    @property
    def mm_v10(self) -> str:
        """
        Returns the media module hw vintage and suffix for slot 10.
        """
        if self.show_mg_list:
            if self._mm_v10 is None:
                suffix = self.mm_groupdict.get("v10", {}).get("suffix", "")
                hw_vint = self.mm_groupdict.get("v10", {}).get("hw_vint", "")
                self._mm_v10 = f"{hw_vint}{suffix}"
            return self._mm_v10
        return "NA"

    @property
    def model(self) -> str:
        """
        Returns the gateway model as a string.
        """
        if self.show_system:
            if self._model is None:
                m = re.search(r"Model\s+:\s+(\S+)", self.show_system)
                self._model = m.group(1) if m else "?"
            return self._model
        return "NA"

    @property
    def port1(self) -> str:
        """
        Returns the LAN port 1 identifier as a string.
        """
        if self._port1 is None:
            pdict = self._port_groupdict(0)
            self._port1 = pdict.get("port", "?") if pdict else "NA"
        return self._port1

    @property
    def port1_status(self) -> str:
        """
        Returns the LAN port 1 link status as a string.
        """
        if self._port1_status is None:
            pdict = self._port_groupdict(0)
            self._port1_status = pdict.get("status", "?") if pdict else "NA"
        return self._port1_status

    @property
    def port1_neg(self) -> str:
        """
        Returns the LAN port 1 auto-negotiation status as a string.
        """
        if self._port1_neg is None:
            pdict = self._port_groupdict(0)
            self._port1_neg = pdict.get("neg", "?") if pdict else "NA"
        return self._port1_neg

    @property
    def port1_duplex(self) -> str:
        """
        Returns the LAN port 1 duplexity status as a string.
        """
        if self._port1_duplex is None:
            pdict = self._port_groupdict(0)
            self._port1_duplex = pdict.get("duplex", "?") if pdict else "NA"
        return self._port1_duplex

    @property
    def port1_speed(self) -> str:
        """
        Returns the LAN port 1 speed as a string.
        """
        if self._port1_speed is None:
            pdict = self._port_groupdict(0)
            self._port1_speed = pdict.get("speed", "?") if pdict else "NA"
        return self._port1_speed

    @property
    def port2(self) -> str:
        """
        Returns the LAN port 2 identifier as a string.
        """
        if self._port2 is None:
            pdict = self._port_groupdict(1)
            self._port2 = pdict.get("port", "?") if pdict else "NA"
        return self._port2

    @property
    def port2_status(self) -> str:
        """
        Returns the LAN port 2 link status as a string.
        """
        if self._port2_status is None:
            pdict = self._port_groupdict(1)
            self._port2_status = pdict.get("status", "?") if pdict else "NA"
        return self._port2_status

    @property
    def port2_neg(self) -> str:
        """
        Returns the LAN port 2 auto-negotiation status as a string.
        """
        if self._port2_neg is None:
            pdict = self._port_groupdict(1)
            self._port2_neg = pdict.get("neg", "?") if pdict else "NA"
        return self._port2_neg

    @property
    def port2_duplex(self) -> str:
        """
        Returns the LAN port 2 duplexity status as a string.
        """
        if self._port2_duplex is None:
            pdict = self._port_groupdict(1)
            self._port2_duplex = pdict.get("duplex", "?") if pdict else "NA"
        return self._port2_duplex

    @property
    def port2_speed(self) -> str:
        """
        Returns the LAN port 2 speed as a string.
        """
        if self._port2_speed is None:
            pdict = self._port_groupdict(1)
            self._port2_speed = pdict.get("speed", "?") if pdict else "NA"
        return self._port2_speed

    @property
    def port_redu(self) -> str:
        """
        Returns the port numbers used for port redundancy.
        """
        if self.show_running_config:
            if self._port_redu is None:
                m = re.search(
                    r"port redundancy \d+/(\d+) \d+/(\d+)",
                    self.show_running_config,
                )
                self._port_redu = f"{m.group(1)}/{m.group(2)}" if m else ""
            return self._port_redu
        return "NA"

    @property
    def psu1(self) -> str:
        """
        Returns the Power Supply Unit 1 as a string.
        """
        if self.show_system:
            if self._psu1 is None:
                m = re.search(r"PSU #1\s+:\s+\S+ (\S+)", self.show_system)
                self._psu1 = m.group(1) if m else ""
            return self._psu1
        return "NA"

    @property
    def psu2(self) -> str:
        """
        Returns the Power Supply Unit 2 as a string.
        """
        if self.show_system:
            if self._psu2 is None:
                m = re.search(r"PSU #2\s+:\s+\S+ (\S+)", self.show_system)
                self._psu2 = m.group(1) if m else ""
            return self._psu2
        return "NA"

    @property
    def ram_util(self) -> str:
        """
        Returns the current RAM utilization as percentage.
        """
        if self.show_utilization:
            m = re.search(r"10\s+S+\s+\S+\s+(\d+)%", self.show_utilization)
            self._ram_util = f"{m.group(1)}%" if m else ""
            return self._ram_util
        return "NA"

    @property
    def rtp_stat_service(self) -> str:
        """
        Returns the RTP-Stat service status as a string.
        """
        if self._rtp_stat_service is None:
            m = re.search(r"rtp-stat-service", self.show_running_config)
            self._rtp_stat_service = "enabled" if m else "disabled"
        return self._rtp_stat_service

    @property
    def serial(self) -> str:
        """
        Returns the serial number of the gateway as a string.
        """
        if self.show_system:
            if self._serial is None:
                m = re.search(r"Serial No\s+:\s+(\S+)", self.show_system)
                self._serial = m.group(1) if m else "?"
            return self._serial
        return "NA"

    @property
    def slamon_service(self) -> str:
        """
        Returns the SLAMon service admin status as a string.
        """
        if self.show_sla_monitor:
            if self._slamon_service is None:
                m = re.search(r"SLA Monitor:\s+(\S+)", self.show_sla_monitor)
                self._slamon_service = m.group(1).lower() if m else "?"
            return self._slamon_service
        return "NA"

    @property
    def sla_server(self) -> str:
        """
        Returns the SLAMon server IP address the gateway is registered to.
        """
        if self.show_sla_monitor:
            if self._sla_server is None:
                m = re.search(
                    r"Registered Server IP Address:\s+(\S+)",
                    self.show_sla_monitor,
                )
                self._sla_server = m.group(1) if m else ""
            return self._sla_server
        return "NA"

    @property
    def snmp(self) -> str:
        """
        Returns the configured SNMP version(s) as a string.

        Returns "v2&3" if both SNMPv2 and SNMPv3 are configured,
        "v2" if only SNMPv2 is configured, "v3" if only SNMPv3
        is configured, and "NA" if neither is configured.
        """
        if self.show_running_config:
            if self._snmp is None:
                snmp = []
                lines = [
                    line.strip()
                    for line in self.show_running_config.splitlines()
                ]

                if any(
                    line.startswith("snmp-server community") for line in lines
                ):
                    snmp.append("2")

                if any(
                    line.startswith("encrypted-snmp-server community")
                    for line in lines
                ):
                    snmp.append("3")

                self._snmp = "v" + "&".join(snmp) if snmp else ""
            return self._snmp
        return "NA"

    @property
    def snmp_trap(self) -> str:
        """
        Returns "enabled" if SNMP traps are configured and "disabled" if not.
        """
        if self.show_running_config:
            if self._snmp_trap is None:
                m = re.search(
                    r"snmp-server bgw_ip (\S+) traps", self.show_running_config
                )
                self._snmp_trap = "enabled" if m else "disabled"
            return self._snmp_trap
        return "NA"

    @property
    def temp(self) -> str:
        """
        Returns the ambient temperature as a string.
        """
        if self.show_temp:
            if self._temp is None:
                m = re.search(
                    r"Temperature\s+:\s+(\S+) \((\S+)\)", self.show_temp
                )
                self._temp = f"{m.group(1)}/{m.group(2)}" if m else "?/?"
            return self._temp
        return "NA"

    @property
    def total_session(self) -> str:
        """
        Returns the Total Session column from the RTP-Stat summary.
        """
        if self.show_rtp_stat_summary:
            m = re.search(
                r"nal\s+\S+\s+\S+\s+(\S+)", self.show_rtp_stat_summary
            )
            return m.group(1) if m else "?/?"
        return "NA"

    @property
    def uptime(self) -> str:
        """
        Returns the gateway's uptime as a string.
        """
        if self.show_system:
            if self._uptime is None:
                m = re.search(r"Uptime \(\S+\)\s+:\s+(\S+)", self.show_system)
                if m:
                    self._uptime = (
                        m.group(1)
                        .replace(",", "d")
                        .replace(":", "h", 1)
                        .replace(":", "m")
                        + "s"
                    )
                else:
                    self._uptime = "?"
            return self._uptime
        return "NA"

    @property
    def inuse_dsp(self) -> str:
        """
        Returns the total number of in-use DSPs as a string.
        """
        inuse = 0
        dsps = re.findall(r"In Use\s+:\s+(\d+)", self.show_voip_dsp)
        for dsp in dsps:
            try:
                inuse += int(dsp)
            except Exception:
                pass
        return str(inuse)

    @property
    def is_capturing(self) -> bool:
        if self._capture_service:
            return (
                "enabled/active" in self._capture_service
                and "capture stopped" not in self._capture_service
            )
        return False

    def update(
        self,
        bgw_name: Optional[str] = None,
        bgw_number: Optional[str] = None,
        last_session_id: Optional[str] = None,
        last_seen: Optional[str] = None,
        commands: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> None:
        """
        Updates the BGW instance with new data.

        Args:
            last_seen: The last time the BGW was seen, in the format
                "%Y-%m-%d,%H:%M:%S".
            bgw_name: The name of the gateway.
            bgw_number: The number of the gateway.
            commands: A dictionary of commands and their output.
            **kwargs: Additional keyword arguments.

        Returns:
            None
        """
        self.bgw_name = bgw_name
        self.bgw_number = bgw_number
        self.last_session_id = last_session_id
        self.last_seen = last_seen

        if last_seen:
            last_seen_dt = datetime.strptime(last_seen, "%Y-%m-%d,%H:%M:%S")
            if not self.last_seen_dt:
                self.last_seen_dt = last_seen_dt

            delta = last_seen_dt - self.last_seen_dt
            if delta:
                delta_secs = delta.total_seconds()
                self.avg_poll_secs = round(
                    (self.avg_poll_secs + delta_secs) / 2, 1
                )
            else:
                self.avg_poll_secs = self.polling_secs

            if not self.bgw_number and bgw_number:
                self.bgw_number = bgw_number
            if not self.bgw_name and bgw_name:
                self.bgw_name = bgw_name

            self.polls += 1

        if commands:
            for cmd, value in commands.items():
                bgw_attr = cmd.replace(" ", "_").replace("-", "_")
                setattr(self, bgw_attr, value)

    def _port_groupdict(self, idx: int) -> Dict[str, str]:
        """
        Extract port information from the 'show_port' string.

        Args:
            idx: The index of the port information to extract.

        Returns:
            A dictionary containing port details.
        """
        if self.show_port:
            matches = re.findall(r"(.*Avaya Inc)", self.show_port)

            if not matches:
                return {}

            line = matches[idx] if idx < len(matches) else ""
            if line:
                m = re.search(
                    r"".join(
                        (
                            r".*?(?P<port>\d+/\d+)",
                            r".*?(?P<name>.*)",
                            r".*?(?P<status>(connected|no link))",
                            r".*?(?P<vlan>\d+)",
                            r".*?(?P<level>\d+)",
                            r".*?(?P<neg>\S+)",
                            r".*?(?P<duplex>\S+)",
                            r".*?(?P<speed>\S+)",
                        )
                    ),
                    line,
                )
                if m:
                    return m.groupdict()
        return {}

    def properties_asdict(self) -> Dict[str, Any]:
        """
        Return a dictionary of this instance's properties.

        The dictionary will contain the names of the properties as keys and
        the values of the properties as values.

        Returns:
            A dictionary of the instance's properties.
        """
        properties = {}
        for name in dir(self.__class__):
            obj = getattr(self.__class__, name)
            if isinstance(obj, property):
                val = obj.__get__(self, self.__class__)
                properties[name] = val
        return properties

    def asdict(self) -> Dict[str, Any]:
        """
        Return a dictionary of this instance's properties and attributes.

        The dictionary will contain the names of the properties and attributes
        as keys and the values of the properties and attributes as values.

        Returns:
            A dictionary of the instance's properties and attributes.
        """
        attrs = self.__dict__
        return {**self.properties_asdict(), **attrs}

    @staticmethod
    def _to_mbyte(str: str) -> int:
        """
        Converts the string representation of Memory to MB as an integer.

        Args:
            str: A Memory string from the output of 'show_system'

        Returns:
            An integer representing the number of megabytes.
        """
        m = re.search(r"(\d+)([MG]B)", str)
        if m:
            num, unit = int(m.group(1)), m.group(2)
            if unit == "MB":
                return num
            elif unit == "GB":
                return 1024 * num
        return 0

    def __repr__(self):
        return f"BGW({self.__dict__})"
    
############################## END CLASSES ###################################

if __name__ == "__main__":
    bgw = BGW(**{'bgw_ip': '10.10.48.58', 'proto': 'ptls', 'polling_secs': 10, 'bgw_name': 'AvayaG450A', 'bgw_number': '001', 'polls': 1, 'avg_poll_secs': 10, 'active_session_ids': set(), 'last_seen': datetime(2025, 12, 16, 14, 33, 39), 'last_session_id': '', 'show_announcements_files': '\r\n ID      File               Description    Size (Bytes)      Date\r\n---- ------------------ ------------------ ------------ -------------------\r\n101   moh.wav            announcement file      239798    2022-08-23,8:45:26  \r\n102   emergency.wav      announcement file       26618    2023-03-24,11:36:10 \r\n103   public_announceme  announcement file      201914    2024-10-24,7:37:52  \r\n104   mohtest.wav        announcement file     9648106    2025-07-15,14:50:16 \r\n\r\nNv-Ram:\r\nTotal bytes used             : 10119680  \r\nTotal bytes free             : 12672000  \r\nTotal bytes capacity (fixed) : 22791680', 'show_capture': '\r\n\r\nCapture service is enabled and active\r\nCapture start time 09/12/2025-09:25:13\r\nCapture stop time not-stopped\r\nCurrent buffer size is 1024 KB\r\nBuffer mode is non-cyclic\r\nMaximum number of bytes captured from each frame: 4096\r\nCapture list 501 on all interfaces\r\nCapture IPSec decrypted\r\nNumber of captured frames in file: 604 (out of 145200 total captured frames)\r\nMemory buffer occupancy: 4.62% (including overheads)', 'show_faults': '\r\n\r\nCURRENTLY ACTIVE FAULTS\r\n--------------------------------------------------------------------------\r\n\r\n-- Media Module Faults --\r\n\t+ Insertion failure, mmid = v5, 11/24-07:37:04.00\r\n\r\nCurrent Alarm Indications, ALM LED is off\r\n--------------------------------------------------------------------------\r\nNone', 'show_lldp_config': '\r\n\r\nLldp Configuration \r\n-------------------\r\nApplication status: disable \r\nTx interval: 30 seconds\r\nTx hold multiplier: 4 seconds\r\nTx delay: 2 seconds\r\nReinit delay: 2 seconds', 'show_mg_list': '\r\nSLOT   TYPE         CODE        SUFFIX  HW VINTAGE  FW VINTAGE \r\n----   --------     ----------  ------  ----------  -----------\r\nv1     -- Not Installed --\r\nv2     -- Not Installed --\r\nv3     E1T1         MM710       B       16          52\r\nv4     -- Not Installed --\r\nv5     -- Initializing --\r\nv6     Analog       MM714       B       23          94\r\nv7     -- Not Installed --\r\nv8     -- Not Installed --\r\nv10    Mainboard    G450        B       2           42.36.0(A)', 'show_port': '\r\nPort   Name             Status    Vlan Level  Neg     Dup. Spd. Type\r\n------ ---------------- --------- ---- ------ ------- ---- ---- ----------------\r\n10/5   NO NAME          connected 1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/5\r\n\r\n10/6   NO NAME          no link   1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/6', 'show_rtp_stat_summary': '', 'show_running_config': '\r\n\r\n! version 42.36.0\r\nConfig info release 42.36.0 time "13:33:51 16 DEC 2025 " serial_number 10IS41452851\r\n !\r\nencrypted-username +ikJzwEP/t+XkAlH3l+zsw== password G6uSyomIZMSDb0NnT4RwvSb4IrSGUtuQ9ypCGFikR4w= access-type fe/kaDE5GWBC9Nfj6bNkgA==\r\n!\r\nencrypted-username mJ6sF5BOZeIUWsyCb3C1bw== password 8tMk4PMmywAU0cVXzSERF/aaj9WF0EAq4dB4c0qOLbU= access-type gf0PKwZMZRJ4zRba06ZC3w==\r\nhostname "AvayaG450A"\r\nset system location "Calgary" \r\nno ip telnet \r\nip tftp-server file-system-size 2288\r\nset port mirror source-port 10/5 mirror-port 10/6 sampling always direction both\r\n!\r\nip capture-list 501\r\n name "udp"\r\n!\r\n ip-rule 1\r\n  ip-protocol udp\r\n exit\r\n ip-rule default\r\n  composite-operation "No-Capture"\r\n exit\r\n!\r\nexit\r\n!\r\nds-mode t1\r\n!\r\ninterface Vlan 1\r\n icc-vlan\r\n server-blade-vlan 5\r\n ip address 10.10.48.58     255.255.255.0  \r\n pmi\r\n exit\r\n!\r\ninterface FastEthernet 10/3\r\n exit\r\n!\r\ninterface FastEthernet 10/4\r\n exit\r\n!\r\ninterface Console\r\n speed 9600\r\n exit\r\n!\r\ninterface USB-Modem\r\n description "Default Modem Setup"\r\n timeout absolute 10\r\n ppp authentication ras\r\n no shutdown\r\n ip address 10.3.248.253    255.255.255.252\r\n exit\r\n!\r\ncapture max-frame-size 4096\r\ncapture buffer-mode non-cyclic\r\ncapture filter-group 501\r\nlogin authentication min-password-length 8\r\n!\r\nlogin authentication lockout 0 attempt 0\r\n! Avaya Login Confirmation Received.\r\nEASGManage enableEASG\r\nproduct-id 8c2ae2eead3e6cca800be892bb6e3411\r\n!\r\nset logging file enable \r\nset logging file condition all Error \r\nset logging file condition BOOT Debug \r\n!\r\nno snmp-server community \r\nencrypted-snmp-server user JSXE8Ccs0N0TnuoQek8jwLmaP391mjHjbt9glvbZ2M0= gAAa6QMAG08/c+A= v3ReadISO v3 auth sha 1FCIRMijXV+77fer97/S9O3FlfqIPrTOC5uTFcklYM8=  priv aes128 yyv5YmpCoEn5xZ24B7MR4Y03gnnqwygOY3eQTGRZZB0= \r\nencrypted-snmp-server user 0Ce9aP8Q25tEoXTe0YGwKmt2qLFQJ+UOpG6SMzseQdg= gAAa6QMAG08/c+A= v3TrapISO v3 auth sha TgX0mUpViHn56rSWounTurOYUdreS7rWWY7KssAnYj4=  priv aes128 p5Rdzsia/+4+Uc7f9oeJOj38gI6qX+2Fy1WDL5PTkh8= \r\nsnmp-server group v3ReadISO v3 priv read iso  \r\nsnmp-server group v3TrapISO v3 priv notify iso  \r\nsnmp-server host 10.10.48.92 traps v3 priv bbysnmpv3trap \r\n!\r\nip default-gateway 10.10.48.254    1 low  \r\n!\r\nset sync interface primary v3\r\nset sync source primary\r\nrtp-stat-service\r\nrtp-stat fault\r\nanalog-test\r\nexit\r\n!\r\nset sla-monitor enable\r\nset sla-server-ip-address 10.10.48.198\r\nudp keepalive 10\r\nset mgc list 10.10.48.240\r\nset mediaserver 10.10.48.240 10.10.48.240 23 telnet\r\nset mediaserver 10.10.48.240 10.10.48.240 5023 sat\r\n!#\r\n!# End of configuration file. Press Enter to continue.', 'show_sla_monitor': '\r\n\r\nSLA Monitor:                  Enabled\r\nRegistered Server IP Address: 0.0.0.0\r\nRegistered Server IP Port:    0\r\nConfigured Server IP Address: 10.10.48.198\r\nConfigured Server IP Port:    50011\r\nCapture Mode:                 None\r\nVersion:                      2.7.0', 'show_system': '\r\nSystem Name             : \r\nSystem Location         : Calgary\r\nSystem Contact          : \r\nUptime (d,h:m:s)        : 22,06:00:13\r\nCall Controller Time    : 13:33:56 16 DEC 2025 \r\nSerial No               : 13TG01116522\r\nModel                   : G450\r\nChassis HW Vintage      : 1\r\nChassis HW Suffix       : A\r\nMainboard HW Vintage    : 2\r\nMainboard HW Suffix     : B\r\nMainboard HW CS         : 2.1.7\r\nMainboard FW Vintage    : 42.36.0\r\nLAN MAC Address         : 00:1b:4f:3f:73:e0\r\nWAN1 MAC Address        : 00:1b:4f:3f:73:e1\r\nWAN2 MAC Address        : 00:1b:4f:3f:73:e2\r\nSERVICES MAC address    : 00:1b:4f:3f:73:e3\r\nMemory #1               : 256MB\r\nMemory #2               : Not present\r\nCompact Flash Memory    : No CompactFlash card is installed\r\nPSU #1                  : AC 400W\r\nPSU #2                  : Not present\r\nMedia Socket #1         : MP160 VoIP DSP Module\r\nMedia Socket #2         : Not present\r\nMedia Socket #3         : Not present\r\nMedia Socket #4         : Not present\r\nFAN Tray                : Present', 'show_temp': '\r\nAmbient\r\n-------\r\nTemperature : 36C (97F)\r\nHigh Warning: 42C (108F)\r\nLow Warning : -5C (23F)', 'show_utilization': '\r\n\r\nMod   CPU      CPU     RAM      RAM\r\n      5sec     60sec   used(%)  Total(Kb)\r\n---   ------   -----  -------  ----------\r\n10    Appl. Disabled    48%     190838 Kb', 'show_voip_dsp': '\r\nDSP #1 PARAMETERS\r\n--------------------------------------------------------------\r\nBoard type     : MP160\r\nHw Vintage     : 0 B\r\nFw Vintage     : 182\r\n\r\nDSP#1 CURRENT STATE\r\n--------------------------------------------------------------\r\nIn Use         : 0 of 160 channels, 0 of 4800 points (0.0% used)\r\nState          : Idle\r\nAdmin State    : Release\r\n\r\nCore# Channels Admin     State\r\n      In Use   State\r\n----- -------- --------- -------\r\n    1  0 of 40   Release Idle\r\n    2  0 of 40   Release Idle\r\n    3  0 of 40   Release Idle\r\n    4  0 of 40   Release Idle\r\n\r\n\r\nDSP #2 Not Present\r\n\r\n\r\nDSP #3 Not Present\r\n\r\n\r\nDSP #4 Not Present', 'queue': Queue(), '_active_session': None, '_announcements': None, '_capture_service': None, '_chassis_hw': None, '_comp_flash': None, '_cpu_util': None, '_dsp': None, '_faults': None, '_fw': None, '_hw': None, '_inuse_dsp': None, '_last_seen_time': None, '_lldp': None, '_location': None, '_mac': None, '_mainboard_hw': None, '_memory': None, '_mm_groupdict': None, '_mm_v1': None, '_mm_v2': None, '_mm_v3': None, '_mm_v4': None, '_mm_v5': None, '_mm_v6': None, '_mm_v7': None, '_mm_v8': None, '_mm_v10': None, '_model': None, '_port1': None, '_port1_status': None, '_port1_neg': None, '_port1_duplex': None, '_port1_speed': None, '_port2': None, '_port2_status': None, '_port2_neg': None, '_port2_duplex': None, '_port2_speed': None, '_port_redu': None, '_psu1': None, '_psu2': None, '_ram_util': None, '_rtp_stat_service': None, '_serial': None, '_slamon_service': None, '_sla_server': None, '_snmp': None, '_snmp_trap': None, '_temp': None, '_total_session': None, '_uptime': None})
    print(bgw)
