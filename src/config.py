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