#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS ##################################

import os
import re
import socket
from typing import List

############################## END IMPORTS ####################################

import logging
logger = logging.getLogger(__name__)

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

if __name__ == "__main__":
    from aloop import connected_gws
    print(connected_gws(ip_filter=["10.10.10.1", "10.10.10.2"]))
