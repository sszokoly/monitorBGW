#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS #################################

from datetime import datetime
import re

############################## BEGIN IMPORTS #################################

from utils import run_cmd, CommandResult, logger

############################## BEGIN VARIABLES ###############################
############################## END VARIABLES #################################
############################## BEGIN CLASSES #################################

class Capture:
    """A consistent container for command output."""

    remote_ip: str
    filename: str
    file_size: int
    received_timestamp: datetime
    capinfos: str
    rtpinfos: str
    bgw_number: str

    def __init__(
        self,
        remote_ip: str,
        filename: str,
        file_size: int,
        received_timestamp: datetime,
        capinfos: str = "",
        rtpinfos: str = "",
        bgw_number: str = ""
    ) -> None:
        """
        Initializes the CommandResult object.
        """
        self.remote_ip = remote_ip
        self.filename = filename
        self.file_size = file_size
        self.received_timestamp = received_timestamp
        self.capinfos = capinfos
        self.rtpinfos = rtpinfos
        self.bgw_number = bgw_number

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
            f"bgw_number={repr(self.bgw_number)}"
        ]

        return f"Capture({', '.join(fields)})"

############################## END CLASSES ###################################
############################## BEGIN FUNCTIONS ###############################

async def rtpinfos(pcapfile):
    program = "tshark"
    args = ["-n", "-q", "-o", "rtp.heuristic_rtp:TRUE",
            "-z", "rtp,streams", "-r", pcapfile]
    result = await run_cmd(program, args)
    logger.debug(f"rtpinfos {result}")
    return "" if result.returncode else result.stdout.strip()

async def capinfos(pcapfile):
    program = "capinfos"
    args = [pcapfile]
    result = await run_cmd(program, args)
    logger.debug(f"capinfos {result}")
    return "" if result.returncode else result.stdout.strip()

if __name__ == "__main__":
    from utils import asyncio_run
    
    pcapfile1 = "uploads/2025_12_20@13_12_33_003"
    capinfos_output1 = asyncio_run(capinfos(pcapfile1))
    rtpinfos_output1 = asyncio_run(rtpinfos(pcapfile1))
    
    capture1 = Capture(**{
        "remote_ip": "10.10.48.58",
        "filename": "2025_12_20@13_12_33_003",
        "file_size": 6539,
        "received_timestamp": datetime.now(),
        "capinfos": capinfos_output1,
        "rtpinfos": rtpinfos_output1,
        "bgw_number": "001"
    })

    pcapfile2 = "uploads/2025_12_19@22_05_45_002"
    capinfos_output2 = asyncio_run(capinfos(pcapfile2))
    rtpinfos_output2 = asyncio_run(rtpinfos(pcapfile2))

    capture2 = Capture(**{
        "remote_ip": "10.44.244.51",
        "filename": "2025_12_19@22_05_45_002",
        "file_size": 6539,
        "received_timestamp": datetime.now(),
        "capinfos": capinfos_output2,
        "rtpinfos": rtpinfos_output2,
        "bgw_number": "004"
    })
    
    print(capture1.first_packet_time)
    print(capture1.last_packet_time)
    print(capture1.rtp_streams)
    print(capture1.rtp_problems)
    print(capture1)
    print(capture2)