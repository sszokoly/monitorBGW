#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN CONFIG ###################################

CONFIG = {
    "user": "root",
    "passwd": "cmb@Dm1n",
    "max_polling": 20,
    "timeout": 20,
    "polling_secs": 15,
    "loglevel": "DEBUG",
    "logfile": "debug.log",
    "http_server": "0.0.0.0",
    "http_port": 8080,
    "upload_dir": "/tmp",
    "discovery_commands": [
        "set utilization cpu",
        "rtp-stat-service",
        "show running-CONFIG",
        "show system",
        "show faults",
        "show capture",
        "show voip-dsp",
        "show temp",
        "show port",
        "show sla-monitor",
        "show utilization",
        "show announcements files",
        "show lldp CONFIG",
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