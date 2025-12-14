#!/usr/bin/env python
# -*- encoding: utf-8 -*-
import re
from datetime import datetime
from utils import logger

RTP_DETAILED_PATTERNS = (
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


class RTPDetailed:
    def __init__(self, **params) -> None:
        """
        Class that contains the RTP stat details of a BGW RTP session.

        :param params: keyword arguments.
        """
        self.bgw_number: str = ""
        self.global_id: str = ""
        self.qos: str = "ok"
        self.rx_rtp_packets: str = "0"
        self.status: str = ""
        self.local_ssrc: str = ""
        self.remote_ssrc: str = ""
        self.start_time: str = ""
        self.end_time: str = ""

        for k, v in params.items():
            setattr(self, k, v)

    @property
    def is_ok(self) -> bool:
        """
        True if the QoS is 'ok' and BGW received RTP packets.

        Return: Whether the QoS is 'ok'.
        """
        return self.qos.lower() == "ok" and int(self.rx_rtp_packets) > 0

    @property
    def is_active(self) -> bool:
        """
        True of RTP is Terminated, False otherwise.

        Returns:
            bool: True of RTP is Terminated, False otherwise.
        """
        return self.status != "Terminated"

    @property
    def local_ssrc_hex(self) -> str:
        """
        SSRC of local RTP in hexadecimal.

        Returns:
            str: SSRC of local RTP in hexadecimal.
        """
        try:
            return hex(int(self.local_ssrc))
        except ValueError:
            return ""

    @property
    def remote_ssrc_hex(self) -> str:
        try:
            return hex(int(self.remote_ssrc))
        except ValueError:
            return ""

    @property
    def start_datetime(self) -> datetime | None:
        if self.start_time:
            return datetime.strptime(self.start_time, "%Y-%m-%d,%H:%M:%S")
        return None

    @property
    def end_datetime(self) -> datetime | None:
        if not self.end_time or self.end_time == "-":
            return None
        return datetime.strptime(self.end_time, "%Y-%m-%d,%H:%M:%S")

    @property
    def duration_secs(self) -> int | None:
        if self.start_datetime is None:
            return None

        if self.end_datetime is None:
            return int((datetime.now() - self.start_datetime).total_seconds())

        return int((self.end_datetime - self.start_datetime).total_seconds())

    def __repr__(self) -> str:
        """
        Return a string representation of the RTPDetailed object.

        :return: A string representation of the RTPDetailed object.
        """
        return f"RTPDetailed=({self.__dict__})"

    def __str__(self) -> str:
        """
        Return a string representation of the RTPDetailed object.

        The string is formatted according to the SESSION_FORMAT string,
        which is a template string that uses the attributes of the RTPDetailed
        object as replacement values.

        :return: A string representation of the RTPDetailed object
        """
        return str(self.__dict__)

    def asdict(self):
        return self.__dict__


reRTPDetailed = re.compile(r"".join(RTP_DETAILED_PATTERNS), re.M | re.S | re.I)


def parse_rtpstat(global_id, rtpstat):
    """
    Returns RTPDetailed instance with RTP stat attributes.
    """
    bgw_number, session_id = global_id.split(",")[2:]

    try:
        m = reRTPDetailed.search(rtpstat)
        if m:
            d = m.groupdict()
            d["bgw_number"] = bgw_number
            d["global_id"] = global_id
            rtpdetailed = RTPDetailed(**d)
        else:
            logger.error(f"Unable to parse {session_id} from BGW {bgw_number}")
            logger.debug(repr(rtpstat))
            rtpdetailed = None

    except Exception as e:
        logger.error(f"Error {e.__class__.__name__} with session {session_id}")
        return None

    return rtpdetailed


if __name__ == "__main__":
    d = {
        "2024-11-04,10:06:07,001,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 1\r\nStatus: Terminated, QOS: Ok, EngineId: 10\r\nStart-Time: 2024-11-04,10:06:07, End-Time: 2024-11-04,10:07:07\r\nDuration: 00:00:00\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.110:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 4.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
        "2025-12-14,10:06:07,001,00002": "\r\nshow rtp-stat detailed 00002\r\n\r\nSession-ID: 1\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:06:07, End-Time: -\r\nDuration: - \r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.110:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
    }
    for global_id, value in d.items():
        rtpdetailed = parse_rtpstat(global_id, value)
        if rtpdetailed:
            print(rtpdetailed.bgw_number)
            print(rtpdetailed.rx_rtp_packets)
            print(rtpdetailed.is_ok)
            print(rtpdetailed.is_active)
            print(rtpdetailed.local_ssrc_hex)
            print(rtpdetailed.remote_ssrc_hex)
            print(rtpdetailed.start_datetime)
            print(rtpdetailed.end_datetime)
            print(rtpdetailed.duration_secs)
