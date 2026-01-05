#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS ##################################

import re
from datetime import datetime
from typing import Any, Dict, Optional

############################## END IMPORTS ####################################

import logging
logger = logging.getLogger(__name__)

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

if __name__ == "__main__":
    d = {
        "2024-11-04,10:06:07,001,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 1\r\nStatus: Terminated, QOS: Ok, EngineId: 10\r\nStart-Time: 2024-11-04,10:06:07, End-Time: 2024-11-04,10:07:07\r\nDuration: 00:00:00\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.110:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 4.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
        "2025-12-14,10:06:07,001,00002": "\r\nshow rtp-stat detailed 00002\r\n\r\nSession-ID: 1\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:06:07, End-Time: -\r\nDuration: - \r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.110:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
    }
    for global_id, value in d.items():
        rtpdetails = parse_rtpstat(global_id, value)
        if rtpdetails:
            print(rtpdetails.bgw_number)
            print(rtpdetails.rx_rtp_packets)
            print(rtpdetails.nok)
            print(rtpdetails.is_active)
            print(rtpdetails.local_ssrc_hex)
            print(rtpdetails.remote_ssrc_hex)
            print(rtpdetails.start_datetime)
            print(rtpdetails.end_datetime)
            print(rtpdetails.duration_secs)
