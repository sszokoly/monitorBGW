#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS ##################################

import argparse
import re
from typing import Optional, Set

############################## END IMPORTS ####################################

import logging
logger = logging.getLogger(__name__)

############################## BEGIN FILTER ###################################

FILTER_GROUPs = {
    "bgw": {
        "current_filter": "",
        "no_filter": False,
        "groups": {
            "ip_filter": set(),
            "ip_input": set()
            }
        },
}

FILTER_MENUs = {
    "bgw":
"""                                BGW FILTER
Filter Usage:
    -f <IP>    <IP> address filter of gateways separated by | or ,
    -i <IP>    <IP> address input of gateways separated by | or ,
    -n         no filter, clear current filter
 
Filter examples:
  You may use -f when the script is run on a Communication Manager
  You must use -i when the script is run outside a Communication Manager
  To discover only gateway 10.10.10.1 and 10.10.10.2
    -f 10.10.10.1|10.10.10.2  OR  -f 10.10.10.1,10.10.10.2
"""}

class NoExitArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def is_valid_ipv4(ip: str) -> bool:
    """
    Validate whether a string is a valid IPv4 address.

    This function uses a regular expression to ensure the address:
      - Consists of exactly four octets separated by dots
      - Each octet is in the range 0–255

    Args:
        ip: The IPv4 address string to validate.

    Returns:
        True if the string is a valid IPv4 address, False otherwise.
    """
    octet = r"(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)"
    pattern = rf"^({octet}\.){{3}}{octet}$"

    return re.match(pattern, ip) is not None

def parse_and_validate_i(value: str) -> Set[str]:
    """
    Parse and validate a list of IPv4 addresses.

    The input string may contain IPv4 addresses separated by commas or
    pipe characters (`","` or `"|"`). Each IP is stripped of surrounding
    whitespace and validated.

    Args:
        value: A string containing one or more IPv4 addresses.

    Returns:
        A set of validated IPv4 address strings.

    Raises:
        argparse.ArgumentTypeError: If any IP address is invalid.
    """
    raw_ips = re.split(r"[,\|]", value)
    ips: Set[str] = set()

    for ip in raw_ips:
        ip = ip.strip()
        if not ip:
            continue

        if not is_valid_ipv4(ip):
            raise argparse.ArgumentTypeError(f"Invalid IP: {ip}")

        ips.add(ip)

    return ips

def create_filter_parser() -> "NoExitArgumentParser":
    """
    Create an argument parser for workspace filtering.

    This parser is intended for use in the curses UI filter panel. It supports a
    mutually exclusive choice between:

    - `-n`: disable filtering
    - `-f <ips>`: provide a set of BGW IPv4 addresses to discover (filter)
    - `-i <ips>`: provide a set of BGW IPv4 addresses to discover (input)

    Returns:
        A configured NoExitArgumentParser instance.
    """
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
        "-f",
        dest="ip_filter",
        type=parse_and_validate_i,
        default=set(),  # type: Set[str]
        help="BGW IP filter list separated by | or ,",
    )

    group.add_argument(
        "-i",
        dest="ip_input",
        type=parse_and_validate_i,
        default=set(),  # type: Set[str]
        help="BGW IP input list separated by | or ,",
    )

    return parser

filter_parser = create_filter_parser()

def filter_validator(line: str) -> Optional[str]:
    """
    Validate and parse a filter command line.

    This function is typically used as a validator for user input (e.g. from a
    curses text field). It sanitizes the input, attempts to parse it using the
    global `filter_parser`, and logs the parsed arguments for debugging.

    If parsing fails, the error is logged and the error message is returned.
    Returning a string is assumed to signal validation failure to the caller.

    Args:
        line: Raw input line containing filter arguments.

    Returns:
        None if the input is valid and successfully parsed.
        A string error message if validation or parsing fails.
    """
    # Strip quotes and surrounding whitespace
    cleaned = line.replace("'", "").replace('"', "").strip()

    try:
        args = filter_parser.parse_args(cleaned.split())
        logger.debug(args)
        return None

    except Exception as e:
        logger.error(repr(e))
        return str(e)

from typing import Any, Dict, MutableMapping


def update_filter(
    group: str,
    filter: str,
    filter_groups: MutableMapping[str, Dict[str, Any]] = FILTER_GROUPs,
) -> None:
    """
    Update the active filter configuration for a given filter group.

    This function parses a filter string using the global `filter_parser` and
    updates the corresponding entry in `filter_groups`. It supports:
    - Clearing filters via the `--no-filter` flag
    - Updating the current raw filter string
    - Updating individual filter sub-groups (e.g. `ip_filter`, `ip_input`)

    The structure of `filter_groups` is expected to be:

        {
            "<group>": {
                "current_filter": str,
                "no_filter": bool,
                "groups": {
                    "<filter_name>": Any,
                },
            }
        }

    Args:
        group:
            The top-level filter group key (e.g. "bgw").
        filter:
            The raw filter string entered by the user.
        filter_groups:
            A mutable mapping holding all filter group configurations.
            Defaults to the global `FILTER_GROUPs`.

    Returns:
        None
    """
    # Parse arguments from the filter string
    args = vars(filter_parser.parse_args(filter.split()))

    group_cfg = filter_groups.get(group)
    if group_cfg is None:
        return

    # Handle "no filter" case
    if args.get("no_filter"):
        group_cfg["current_filter"] = ""
        group_cfg["no_filter"] = True
        logger.info("Cleared 'current_filter'")

    # Update current filter string
    elif filter:
        group_cfg["current_filter"] = filter
        group_cfg["no_filter"] = False
        logger.info(f"Updated 'current_filter' to '{filter}'")

    # Update individual filter groups (e.g. ip_filter)
    groups = group_cfg.get("groups")
    if not groups:
        return

    for key in groups:
        if key not in args:
            continue

        if args.get("no_filter"):
            groups[key].clear()
        else:
            groups[key] = args[key]

        logger.info(f"Updated '{key}' to '{groups[key]}'")

############################## END FILTER #####################################

def parse_and_validate_b(s):
    """Parse BGW number"""
    result = set()
    nums = set(re.split(r"[,|\|]", s))
    for num in nums:
        if len(num) > 3 or not num.isdigit() or num == "0":
            raise argparse.ArgumentTypeError(f"Invalid number: {num}")
        num = f"{num.strip():0>3}"
        result.add(num)
    return result

if __name__ == "__main__":
    line = '-f 10.10.10.2'
    err = filter_validator(line)
    print(err)
