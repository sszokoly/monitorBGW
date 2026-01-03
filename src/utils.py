#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS ##################################

import os
import sys
import resource
from typing import List

############################## END IMPORTS ####################################

from storage import GWs, RTPs
import logging
logger = logging.getLogger(__name__)

############################## BEGIN UTILS ####################################

def memory_usage_resource():
    """int: Returns the memory usage of this tool in MB."""
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.)

def update_title():
    """Updates terminal status line."""
    l = []
    l.append("MemUsage:{0:>4}MB".format(memory_usage_resource()))
    l.append("Num of BGWs: {0:>3}".format(len(GWs)))
    l.append("Num of RTP Sessions: {0:>4}".format(len(RTPs)))
    sys.stdout.write("\x1b]2;%s\x07" % "      ".join(l).ljust(80))
    sys.stdout.flush()

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

############################## END UTILS ######################################

if __name__ == "__main__":
    from aloop import connected_gws
    print(connected_gws(ip_input=["10.10.10.1", "10.10.10.2"]))
