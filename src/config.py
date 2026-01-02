#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS ##################################

import logging

############################## END IMPORTS ####################################

config = {
    "user": "root",
    "passwd": "cmb@Dm1n",
    "max_polling": 20,
    "timeout": 20,
    "polling_secs": 15,
    "loglevel": "DEBUG",
    "logfile": "bgw.log",
    "http_server": "0.0.0.0",
    "http_port": 8080,
    "upload_dir": "/tmp",
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

FORMAT = "%(asctime)s - %(levelname)8s - %(message)s [%(funcName)s:%(lineno)s]"
logger = logging.getLogger(__name__)
logging.basicConfig(
        format=FORMAT,
        filename="debug.log",
        level=config["loglevel"].upper(),
    )

# logger = logging.getLogger()
# logger.setLevel(config["loglevel"].upper())

# logging.basicConfig(format=FORMAT)
# logger.setLevel(config["loglevel"])

############################## END VARIABLES ##################################
if __name__ == "__main__":
    print(config)