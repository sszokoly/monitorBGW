#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS ##################################

import base64
import os
import re
import sys
import resource
import textwrap
import zlib
from typing import Optional, Set, Dict, Iterable, List

############################## END IMPORTS ####################################

#from async_loop import GWs, RTPs
from config import logger, config
from bgw import BGW

############################## BEGIN VARIABLES ################################

COMPRESSED_EXPECT_SCRIPT = '''\
eJzVWntz2zYS/1+fAqHpxi/akq/pTN261+ZxzV0uj4nTm8lIqoYmIZkXimAA0I/T6LvfYgGQAEn50X
RycxqPRYG7i8UPu4vdJbceHVWCH51nxRG9LmkiB1vk7bmMs0KQhC2XcZESVsmykmTO2ZL8chnfxOQp
j4vkgvwaS3oV3wDLeyorDiz/OHv7hlxl8oIs9D2SFXN20BIliLp+/+EdETKWmZBZIkDI679/IP/MEl
oICr8uKRcZK8jwcESe04QcD4+/G2zd9iEf6LLMYV7yr5hn8XlOBbmVYTAQVJI8LmZZSVb6e41jlaCc
rNR//buMhbhKyUp/6zEuy5nSX5BVfWmoOb2c5bGQM0GFWsQsU7w9ow59nMjskjr3hGHp3tBcBlMgs1
d6PKXn1YKs8Gs9uB2yLfICd/2+iBnIWClBFUHGOWweiRg5kzxL5Esm5Ct68+yCJp+yYnFaMHXvN0Dx
VcGuCnVb/C3L6elRSi+PiirPpyhOZksKlkFGQwMHW5aSBJPdLRKYLfKxDPQwT8hwEHMOZuYCMtNDq9
V67dzFPdIiPIqcLWa43cPBIJvDWKiRW8PlgMAHFQCiOWhOAu0lM6SZhdpmDuF2gLQoYIyU9BqwESS0
rNNGovogTUpzCuZa0+Bd0MlOm54vyJiVtGhISDzF26DHLCsk5UWck2juEAwH6zu3Xe38O84Smlb8zj
3HbYdNSci/BeBPRRKXFNYiJPdRggEyhn+w92QZl+5yg8kkUP/gyxkL9FjgjhU4VrhDHIe4OyRxSAYG
MRLCtBoYjqEIBxAIVFyymdIdd9yqtcjZOWBn3H9xNSviJcXvankO9mCMDsBvm9+kVgQ+LavrmlkND2
oQrFZa6biEfU3N4CTQakyCEzIJxi7Oxsamk+CA9HIazftYza3beXG1m7jx5mb+GqN+xc3NO/ktsrdI
sSSbZdmNUEIsyAr2ecYhSI3w95xxGsPJtVp9ojfkMs4rCgYx1lu36MSQqWvC6NuPQhSHVuTND0oZx+
1RzV8RTD3tWymqM3W9oVF/6IYGT/p6fQCSXLP7IgC69vv/AcJ6HXjur8Yb/09yCl5kEpnVSl80oYDT
hajOSRTnuQo3kyKK5A1o8xkCB/lcZXDicSLKOKFEwQaDCStkVlQ0igjQj38nk+neq8CPDKGZD6Kcvu
rO9YZB+JcXsVohzdPDveA+XM9ZQR/dk1atxug3wQN1IxPiZsM3/F/ybHEhLfnUAXMJ2YxNOjrxVJ/e
tfHVk5kR2LIgNLyBPclUBuIeFnt4NoERgiZxweQFhGObQpawlYKSqxh25fBQoeBwojzOYbeCRsQvWs
Izd1LHkPSMKSM3rAKxhXT3l+x8PHqz+9fuLJhwVJzTQlq7Ck1uAD93zqv5nPJdj8VYrKX2uVvCFUwf
3VPQIDWzivWtIjSZ09dS1QPQ8Yj/BVgPxSrYc3b58OtqfLduX1khkVNamhPivkrapL3f+3RZ8UHTdF
zOSXEh/axyScZehK5jjqLqiUw5nQORYbXRREeoLfIMFsnjPPsPTeugQa9pUqmaRRenWskLuJPrEJOq
DH8B1zrCKfKZ5a1DHaa8cH5aLYfq1GlFP118qbwdihM/mUCypkpolxnqg7VxqLiD5y+e/vbrCZRnSn
FKHttVPm7AnOeVuEByF1QnG49lBTVaEks88J1oPFYhvA7D4DqqOAFQlmIxdTQ0Eh6dqqW6epri6/jJ
X3zVhUxBCkjWssjVha6EEHwAum8VG8FoAfLi/fu370/IQ0T3gNQyYmNbQdBB0CLg7Pc339RnZwGVYN
DFxN/wHavSruXrzGKzFXNbG7Dd85hgec3mtdwDU3nDyQ5FrWRlqZYOVq3zIzTrrgULZcLLdIbS0IbL
mcq40An0zm62a5swWh8IHUn12j0QrI15ThTWF+5U05YVGFb6WSUnCm5P1655GPhGG+KLuT1sUhfIcH
sbLSu/kO0hwVbHtJ3W+IsMxAW7Uhl0pDyH2DTaiAumbetyl+svzmiODQqzIG83IGxRiIhlnskmn1N+
3MnVx5ANQiiHq993xsPo++n+7kTsq4oZZcwIlFRdYHNzdvQAEWbp7XCHXSZ/AzqdsRb6D8JWCSOjP4
Bt4/MNlwUrQmy6kBmhPaDZtRtwfERgKg+Agl5tNL86i+5pIbZ+14C15RlbddDoFbcZm3G/n0y7iLXL
84cYM1R8BelXLdhOA41Bls5SmmTLOHd4eslxsE0O6MB9MKWS1zg0NGSfjNZrvSx9oAAN0P94auZoSP
0lWf/oIA8OugTzDLaHT0AlkOWEuCLhSplRn8+0BDnFVlwChdoGWZU9pWs772iOf8XQHAFdm7hX/vGU
QlZEHntaPNZJlHGGx8Yrbk1MHBczaZw+sYKnmLeSJUspyQQpWBElN0meJXWdOiWnpyQa9ePfWmRg9C
Q6HY5QrCPTRb5PG3zEgQF2zuMlPSHfDr//7ss0WcbXEQqLBGSkWuBdajwzvHjMPhmO/pAGXiuCBAUj
WWmtKWokt8juQ4N90iote5gjXoET9YmNwJolS1jeywlal0xkkkaspDzGTN2g0KGl15ncOHVK5zEUBf
ea4A2LHjRH76Dd53mWS7C4BWfgpgq1HtPPc1oswHNCf6twV1sZdttFN5cGJ+RHsHD6U/CD43c9Oe6w
q9BDSxBf7TsrEXuY+LloSwoZkeG0J9zJmMu+g7Hm8yPel8Y1NZ2Ja/UMdUlx+1LxWz0CXbJL2hgEig
xIk7sk1tYwytSzKDerg7YTrgWNOQQi7OJFWYEZSVQwSSJ6DUdznVGL9pTTL5TmKWtOjDvSshb1/TIw
PxfwClb3yPN6AXfUpT2CbXR00MoBizrK6ZMi2ETrIbuByIPg4e4Fsv4UO6x9aEn5gmKNplJL9T1CKz
v202wQeg5mANlRwooEkpZQk+LXcWNFtkOTCwYuGVVF9rmiaDDI7j9108T3ewKpHkK+jsEN70OpCuOz
Mr4qyNnZS9W4K2iiovhA4KAAMKLPsLy99Tq0j6dD9Vz3Z/MATQl4qTo+FCXkDALAwO89B+/U433G0x
NsYZpmtX7mD8WVCWs9jS/c1UiF4Sv0LNsH8btgP6hnwpIcP/nWjZKUzf8MUfDXWszeO8qXGaaUECyL
jKZ+F3vTTA3bc+RqJnvi6t00m43tqcaF5CqY2Hc/MFFQUcI8UcXAZ54PKMuyz1wDmML+1pRQMdV168
7494mAGizamaT7u+PJjiq9enqfqmfQeYqLZtO8QUAL930Cag4nkqqXRoL97Y/R9jLaTg+2X55svz7Z
PlMBDfjxLLKhAFybU/AAIWk6MOe6ja53RWYVstz0zXN7BLElUB16njxW3tShSz3t3+sK3RCgqjJncW
qD7GgYtLtNuXO4qk3DRo19Y2fQOsTrqyHUM6rpyiC5gbX7L/X0gBU278r4b1i0SrpxT6egiUmduqun
rHZaAooFo2Lqc9W+4IbMdi1mStSerobi9I68njmwj+A21Kw+ZSzV2xswjPYVKdc+mYj9ncnZ/u6Bk7
/Zno8DTt9EPc8L7tNISamMwY5UY64WFkw9Ud6Pu852+1Fuw8p2b7JNdQ5L++SNOgvvzI3bqLrZFPbO
tmpMMhNaPMN2a7HWusm/jZAp+YmM+tU3+QhX515WpPS6ZiKjaS+1zk/RdOsmgDjAv0A1MpWs5pUKF+
5+ed0H8TthPYffUe7Brmm1aC9/qzdMH8/gl4V+VU9rOsCjYGxekpkOMNyHPPkvN1tpKA==
'''

def compress_and_wrap(input_string, column_width=78):
    """Compresses, base64 encodes and wraps text"""
    compressed_bytes = zlib.compress(input_string.encode("utf-8"))
    base64_bytes = base64.b64encode(compressed_bytes)
    wrapped = textwrap.fill(base64_bytes.decode("utf-8"), width=column_width)
    return wrapped

def unwrap_and_decompress(wrapped_text):
    """Unwraps, base64 decodes and decompresses string"""
    base64_str = wrapped_text.replace("\n", "")
    compressed_bytes = base64.b64decode(base64_str)
    original_string = zlib.decompress(compressed_bytes).decode("utf-8")
    return original_string

EXPECT_SCRIPT = unwrap_and_decompress(COMPRESSED_EXPECT_SCRIPT)

############################## END VARIABLES ##################################
############################## BEGIN CLASSES ##################################

class CommandResult:
    """A consistent container for command output."""

    stdout: str
    stderr: str
    returncode: Optional[int]
    error_type: Optional[str]
    name: Optional[str]

    def __init__(
        self,
        stdout: str,
        stderr: str,
        returncode: Optional[int],
        error_type: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        """
        Initializes the CommandResult object.
        """
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.error_type = error_type
        self.name = name

    def __repr__(self) -> str:
        """
        Provides a string representation for debugging and printing
        """
        fields = [
            f"name={repr(self.name)}",
            f"stdout={repr(self.stdout)}",
            f"stderr={repr(self.stderr)}",
            f"returncode={self.returncode}",
        ]
        if self.error_type is not None:
            fields.append(f"error_type={repr(self.error_type)}")

        return f"CommandResult({', '.join(fields)})"

############################## END CLASSES ####################################
############################## BEGIN FUNCTIONS ################################

def create_bgw_script(
    bgw: "BGW",
    script_template: str = EXPECT_SCRIPT,
) -> str:
    """
    Generate an Expect script for querying a BGW.

    The generated script depends on whether the BGW has been seen before:
    - If this is the first discovery, discovery commands are used and RTP
      statistics are disabled.
    - If the BGW has been seen previously, query commands are used and RTP
      statistics are enabled.
    - Any queued commands are prepended to the command list.

    Args:
        bgw: The BGW instance to generate the script for.
        script_template: The Expect script template to format.

    Returns:
        A fully formatted Expect script as a string.
    """
    debug: int = 1 if logger.getEffectiveLevel() == 10 else 0

    if not bgw.last_seen:
        # Initial discovery
        rtp_stats: int = 0
        commands: List[str] = config["discovery_commands"][:]
        prev_last_session_id: str = ""
        prev_active_session_ids: Iterable[str] = []

    else:
        # Regular polling
        rtp_stats = 1
        prev_last_session_id = bgw.last_session_id or ""
        prev_active_session_ids = sorted(bgw.active_session_ids)
        commands = config["query_commands"][:]

        if not bgw.queue.empty():
            queued_commands = bgw.queue.get()
            if isinstance(queued_commands, str):
                queued_commands = [queued_commands]

            commands = list(queued_commands) + commands
            logger.info(
                "Queued commands: '%s' - %s",
                queued_commands,
                bgw.lan_ip,
            )

    template_args = {
        "lan_ip": bgw.lan_ip,
        "user": config["user"],
        "passwd": config["passwd"],
        "prev_last_session_id": f'"{prev_last_session_id}"',
        "prev_active_session_ids": "{"
        + " ".join(f'"{sid}"' for sid in prev_active_session_ids)
        + "}",
        "rtp_stats": rtp_stats,
        "commands": "{"
        + " ".join(f'"{cmd}"' for cmd in commands)
        + "}",
        "debug": debug,
    }

    logger.debug(
        "Template variables %s - %s",
        template_args,
        bgw.lan_ip,
    )

    return script_template.format(**template_args)

def connected_gws(
    ip_filter: Optional[Set[str]] = None,
    ip_input: Optional[List[str]] = None
) -> Dict[str, str]:
    """Return a dictionary of connected G4xx media-gateways

    Args:
        ip_filter: IP addresses of BGWs to return if/when found.
        ip_input: Manually fed list of BGW addresses, netstat will not run.

    Returns:
        Dict: A dictionary of connected gateways.
    """
    result: Dict[str, str] = {}
    ip_filter = set(ip_filter) if ip_filter else set()
    ip_input = list(ip_input) if ip_input else []

    if ip_input:
        return {ip:"na" for ip in ip_input}

    command = "netstat -tan | grep ESTABLISHED | grep -E ':(1039|2944|2945)'"
    pattern = r"([0-9.]+):(1039|2944|2945)\s+([0-9.]+):([0-9]+)"
    protocols = {"1039": "ptls", "2944": "tls", "2945": "unenc"}

    connections = os.popen(command).read()

    for m in re.finditer(pattern, connections):
        ip, port = m.group(3, 2)

        proto = protocols.get(port, "unknown")
        logger.debug(f"Found GW using {proto} - {ip}")

        if not ip_filter or ip in ip_filter:
            result[ip] = proto
            logger.info(f"Added GW to results - {ip}")

    if not result:
        # For testing purposes, return a dummy dictionary
        return {"10.10.48.58": "ptls", "10.44.244.51": "tls"}

    return {ip: result[ip] for ip in sorted(result)}

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

############################## END FUNCTIONS ##################################

if __name__ == "__main__":
    print(connected_gws(ip_input=["10.10.10.1", "10.10.10.2"]))
