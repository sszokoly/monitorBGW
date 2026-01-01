#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS #################################
import argparse
import re
############################## END IMPORTS ###################################
from utils import logger
############################## BEGIN VARIABLES ################################

FILTER_GROUPs = {
    "bgw": {
        "current_filter": "",
        "no_filter": False,
        "groups": {
            "ip_filter": set(),
            }
        },
}

FILTER_MENUs = {
    "bgw":
"""                                BGW FILTER
Filter Usage:
    -i <IP>    <IP> address of Branch Gateway(s) separated by | or ,
    -n         no filter, clear current filter
 
Filter examples:
  To discover only gateway 10.10.10.1 and 10.10.10.2
    -i 10.10.10.1|10.10.10.2  OR  -i 10.10.10.1,10.10.10.2
"""}
############################## END VARIABLES #################################
############################## BEGIN CLASSES #################################

class NoExitArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)

############################## END CLASSES ###################################
############################## BEGIN FUNCTIONS ###############################
def is_valid_ipv4(ip):
    """
    Validate IPv4 address using regex.
    Returns True if valid, False otherwise.
    """
    _octet = r"(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)"
    pattern = rf"^({_octet}\.){{3}}{_octet}$"
    return bool(re.match(pattern, ip))

def parse_and_validate_i(s):
    """Parse IP list and validate each IP"""
    ips = set(re.split(r"[,|\|]", s))
    for ip in ips:
        ip = ip.strip()
        if not is_valid_ipv4(ip):
            raise argparse.ArgumentTypeError(f"Invalid IP: {ip}")
    return ips

def parse_and_validate_b(s):
    """Parse IP list and validate each IP"""
    result = set()
    nums = set(re.split(r"[,|\|]", s))
    for num in nums:
        if len(num) > 3 or not num.isdigit() or num == "0":
            raise argparse.ArgumentTypeError(f"Invalid number: {num}")
        num = f"{num.strip():0>3}"
        result.add(num)
    return result

def create_filter_parser():
    parser = NoExitArgumentParser(add_help=False)
    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "-n",
        dest="no_filter",
        action="store_true",
        default=False,
        help="No filter",
    )

    group.add_argument(
        "-i",
        dest="ip_filter",
        type=parse_and_validate_i,
        default=set(),
        help="BGW IP filter list separated by | or ,",
    )

    return parser

filter_parser = create_filter_parser()

def filter_validator(line):
    line = line.replace("'", "").replace('"', '').strip()

    try:
        args = filter_parser.parse_args(line.split())
        logger.debug(args)

    except Exception as e:
        logger.error(repr(e))
        return f"{e}"

def update_filter(group, filter, filter_groups=FILTER_GROUPs):
    args = vars(filter_parser.parse_args(filter.split()))
    
    if filter_groups.get(group) is not None:
        if args.get("no_filter"):
            filter_groups[group]["current_filter"] = ""
            filter_groups[group]["no_filter"] = args["no_filter"]
            logger.info(f"Cleared 'current_filter'")
    
        elif filter:
            filter_groups[group]["current_filter"] = filter
            logger.info(f"Updated 'current_filter' to '{filter}'")
    
        if filter_groups[group].get("groups") is not None:
            for key in filter_groups[group]["groups"]:
                if args.get(key) is not None:
                    if args.get("no_filter"):
                        filter_groups[group]["groups"][key].clear()
                    else:
                        filter_groups[group]["groups"][key] = args[key]
                    logger.info(f"Updated '{key}' to '{args[key]}'")

############################## END FUNCTIONS #################################

if __name__ == "__main__":
    line = '-i 10.10.10.2'
    err = filter_validator(line)
    print(err)
