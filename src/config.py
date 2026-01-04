#!/usr/bin/env python
# -*- encoding: utf-8 -*-

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
        "show utilization",
        "show announcements files",
        "show lldp config",
        "show mg list",
        "show rtp-stat thresholds"
    ],
    "query_commands": [
        "show voip-dsp",
        "show rtp-stat summary",
        "show capture",
        "show utilization"
    ],
}

############################## END CONFIG #####################################