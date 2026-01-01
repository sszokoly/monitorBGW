#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS #################################

import asyncio
import base64
import gc
import logging
import os
import re
import textwrap
import zlib
from asyncio import coroutines
from asyncio import events
from asyncio import tasks
from typing import Any, Callable, Coroutine, Optional, Tuple, List, Set, Dict

############################## BEGIN IMPORTS #################################
############################## BEGIN VARIABLES ###############################

config = {
    "bgw_user": "root",
    "bgw_passwd": "cmb@Dm1n",
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
logger = logging.getLogger()
logger.setLevel(config["loglevel"].upper())

TASKs = set()

COMPRESSED_EXPECT_SCRIPT = '''\
eJzVWntz2zYS/1+fAqHlxi/akq/pTN261+ZxzV0uj4nTm8lIqoYiIZkXimAA0I/T6LvfYgGQAElZdt
PJzWk8FgXuLhY/7C52l9x5dFIKfjJL8xN6U9BY9nbI25mM0lyQmC2XUZ4QVsqilGTO2ZL8chXdRuQp
j/L4kvwaSXod3QLLeypLDiz/uHj7hlyn8pIs9D2S5nN21BAliLp+/+EdETKSqZBpLEDI679/IP9MY5
oLCr+uKBcpy8ngeEie05icDk6/6+3c9SEf6LLIYF7yr4in0SyjgtzJ0OsJKslscT1NC7LS3+tqrBSU
61F1VY8XkRDXib6jr/U9LoupWo8gq+pS3yk4vZpmkZBTQYVa1DQF/q5Rhz6KZXpFnXvCsLRvaC6DMZ
DZKz2e0Fm5ICv8WvfuhnCHvEAruC+CBkJWSFBFkFEGm0lCRi4kT2P5kgn5it4+u6TxpzRfnOdM3fsN
0HyVs+tc3RZ/SzN6fpLQq5O8zLIJipPpkoKlkOHAwMGWhSTBeH+HBDjSxDLQwzwmg17EOZidC8hUD6
1W67VzF/dIi/AoMrbQWz/o9dI5jPU1cmu47BH4oAJANAfNSaC9Zoo00762oWO4HSAtChghJb0BbATp
W9ZJLVF9kCahGQXzrWjwLuhkp01mCzJiBc1rEhJN8DboMU1zSXkeZSScOwSD3nrrtqudf8dZTJOSb9
1z3HbYlJj8WwD+VMRRQWEtQnIfJRggI/gHe0+WUeEuNxiPA/UPvpyxQI8F7liOY7k7xHGIu0MSh2Rg
ECN9mFYDwzE04QACgYpLNlW6445btRYZmwF2JhyorzxaUn1RLmdgEcbsAP6mAY4rVeDTsLu2oVUAoQ
7BaqXVjgrY2cQMjgOtyDg4I+Ng5CJtrGwyDo7IRk6l+yZedW8LNy54Iz/e3SyhwqlLQHVzK79F9w4p
lmSzLLsZSogFWkE/TzmEqiH+njNOIzjPVqtP9JZcRVlJwSxGevsWrUgycQ0ZPfxRH8WhLXnzg1LGfT
tU81cEU0+6VorqTFyfqNUfuAHCk75eH4Ek1/S+CIC2Df9/gLBeB14QUON1FIgzGuVTk96sVvqiDgic
LkQ5I2GUZSrojPMwlLegzWcIH+RzmcK5x4koopgSBRsMxiyXaV7SMCRAP/qdjCcHrwI/OvTNfBDr9F
V7rjcMDgF5GakV0iw5Pgjuw/Wc5fTRPWnVaox+YzxWNzIhbjaIw/8lTxeX0pJPHDCXkNPY1KMVVfUZ
XhlfNZkZgS0L+oY3sOeZykPcI+MATygwQtAkypm8hJBsE8sCtlJQch3BrhwfKxQcTpTHOexWUIv4RU
t45k7qGJKeMWHklpUgNpfu/pK9jydv9v/angXTjpJzmktrV32TIcDPvVk5n1O+77EYi7XUPndDuILp
o3sWGqSmVrGuVfRN/vS1VPUAdDzifwHWQ7EKDpxdPv66Gm/X7SsrJDJKC3NC3FdJm7p3e58uLj5omp
bLOYkuJKFlJsnIi9BVzFFUHZEpo3MgMqw2mugItUOewSJ5lKX/oUkVNOgNjUtVueiSVSt5CXcyHWIS
lecv4FpHOEU+tbxVqMPEF85Pq+VAnTqN6KdLMJW9Q4niJxNIVtcKzWJDfbBi7ivu4PmLp7/9egZFml
Kcksd2lY9rMOdZKS6R3AXVyckjWUKlFkcSD3wnGo9UCK/CMLiOKlEAlKVYTBwNjYRH52qprp6mBDt9
8hdfdSETkAKStSxyfanrIQQfgO5axUYwGoC8eP/+7fsz8hDRHSA1jNjYVhC0ELQIOPv9zTfV2ZlDPR
i0MfE3fM+qtG/5WrPYbMXc1gZs9zwiWGSzeSX3yNTfcLJDaStZUailg1Xr/AjNum3BQpnwMpmiNLTh
YqoyLnQCvbOb7domjNYH+o6kau0eCNbGPCfqVxfuVJOGFRhW+lklJwpuT9e2eRj4hhvii7k9qFMXyH
A72y0rv5ztIMGGx6SZ1viLDMQlu1YZdKg8h9g02ogLJk3rcpfrL85ojm0KsyBvNyBsUYiIRZbKOp9T
ftzK1UeQDUIoh6vf90aD8PvJ4f5YHKq6GWVMCZRUbWAzc3Z0ANFPk7vh7reZ/A1o9cca6D8IWyWMDP
8AtrXP11wWrBCxaUNmhHaAZtduwPERgak8AHJ6vdH8qiy6o5HY+F0B1pRnbNVBo1PcZmxG3X4yaSPW
LM8fYsxQ8eWkW7VgNwk0BmkyTWicLqPM4ekkx8EmOaAD98GUCl7hUNOQQzJcr/Wy9IECNED/47mZoy
b1l2T9o4U8OOgSzDPYHTwBlUCWE+LymCtlhl0+0xDkFFtRARRqG2RZdJSuzbyjPv4VQ30EtG3iXvnH
UwpZEXnsafFYJ1HGGR4br7gzMXFczKRx+sQKnmLeSpYsoSQVJGd5GN/GWRpXdeqEnJ+TcNiNf2ORgd
GT6HQ4RLGOTBf5Lm3wwQcG2DmPlvSMfDv4/rsv02QZ3YQoLBSQkWqB29R4ZnjxmH0yGP4hDbxWBAly
RtLCWlNYS26Q3YcGm6VlUnQwh7wEJ+oSG4I1SxazrJMTtC6YSCUNWUF5hJm6QaFFS29SuXHqhM4jKA
ruNcEbFj5ojs5Bu8/zNJNgcQvOwE0Vah2mn2U0X4Dn9P2twl1tZNhNF91cGpyRH8HC6U/BD47fdeS4
g7ZCDy1BfLW3ViL2MPFz0YYUMiSDSUe4kxGXXQdjxedHvC+Na2o6E9eqGaqS4u6l4rd6MLpkV7Q2CB
QZkDp3ia2tYZSpZlFuVgVtJ1wLGnEIRNjFC9McM5IwZ5KE9AaO5iqjFs0pJ18ozVPWnBhb0rIG9f0y
MD8X8ApW98jzegFb6tIOwTY6OmhlgEUV5fRJEWyi9ZDdQORB8HD3All/ih1WPrSkfEGxRlOppfoeop
Wd+mk2CJ2BGUB2FLM8hqSlr0nx67S2ItuhyQQDlwzLPP1cUjQYZPefvWni+z2HVI8iX0fghvehVIXx
RRFd5+Ti4qVq3OU0VlG8J3BQABjhZ1jewXrdtw+p+/aR/s/mQZoS8lJ1fShKyRgEgZ7ffw7eqQf9jC
dn2MY0Dev6DQAoskx462iA4e6GKhxfo4fZfojfDftBPSGW5PTJt260pGz+Z4iCv8aCDt5RvkwxtYSg
mac08bvZm2aq2Z4jVz3ZE1fvuulsbFA1MCRXQcW+GYIJg4oW5ukqBkDznMC+a4E0AcxRDWhaqJ2qCn
Zv9PtYQDUW7o2Tw/3ReE8VYR1dUNU96HiqiyZUv1NAc/cNA2oOKpKo10qCw92P4e4y3E2Odl+e7b4+
271QwQ348VyyYQHcnFPwBiFp0jNnvI2026K0Cl9uKueFAASyIVAdgJ48VtxWYUw9/z9oC90QrMoiY1
FiA+5wEDQ7T5lz0KqNw6aNfaen1zjQq6sB1DaqAcsg0YG1+6/9dIDVr9+e8d+5aJR3o46uQR2fWjVY
R4nttAcUC0bIxOeq/MENn826zJSrHR0Oxekdfx1zYE/Bba5ZfYpIqvc5YBjtK1TufTYWh3vji8P9Iy
eXs/0fB5yuiTqeHdynqZJQGYEdqSZdJSyYeKK8H9vOeftRbsOKZp+ySTWDpX3yRp2Ft+bGbVSdbQp7
Z9s2JrHpWzz7zTZjpXWdixshE/ITGXarb3ITrs7ANE/oTcVEhpNOap2roulWDQFxhH+BamoqWc77FS
7e3QLbT+X3+tUkfnu5A7y676Ld/K3eMX1Wg2Pm+m0+rWoPz4OReW9m0sOY3+fxfwGYjHc7
'''

def unwrap_and_decompress(wrapped_text):
    base64_str = wrapped_text.replace("\n", "")
    compressed_bytes = base64.b64decode(base64_str)
    original_string = zlib.decompress(compressed_bytes).decode("utf-8")
    return original_string

EXPECT_SCRIPT = unwrap_and_decompress(COMPRESSED_EXPECT_SCRIPT)

logging.basicConfig(format=FORMAT)
logger.setLevel(config["loglevel"])

############################## END VARIABLES #################################
############################## BEGIN CLASSES #################################

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

############################## END CLASSES ###################################
############################## BEGIN FUNCTIONS ###############################

def create_bgw_script(bgw, script_template=EXPECT_SCRIPT) -> str:
    debug = 1 if logger.getEffectiveLevel() == 10 else 0

    if not bgw.last_seen:
        rtp_stats = 0
        commands = config["discovery_commands"][:]
        prev_last_session_id = ""
        prev_active_session_ids = set()

    else:
        rtp_stats = 1
        prev_last_session_id = bgw.last_session_id
        prev_active_session_ids = sorted(bgw.active_session_ids)
        commands = config["query_commands"][:]
        if not bgw.queue.empty():
            queued_commands = bgw.queue.get()
            if isinstance(queued_commands, str):
                queued_commands = [queued_commands]
            commands = queued_commands + commands
            logger.info(f"Queued commands: '{queued_commands}' - {bgw.bgw_ip}")

    template_args = {
        "bgw_ip": bgw.bgw_ip,
        "bgw_user": config["bgw_user"],
        "bgw_passwd": config["bgw_passwd"],
        "prev_last_session_id": f'"{prev_last_session_id}"',
        "prev_active_session_ids": "{"
        + " ".join(f'"{c}"' for c in prev_active_session_ids)
        + "}",
        "rtp_stats": rtp_stats,
        "commands": "{" + " ".join(f'"{c}"' for c in commands) + "}",
        "debug": debug,
    }

    logger.debug(f"Template variables {template_args} - {bgw.bgw_ip}")
    script = script_template.format(**template_args)
    return script

def connected_gws(ip_filter: Optional[Set[str]] = None) -> Dict[str, str]:
    """Return a dictionary of connected G4xx media-gateways

    Args:
        ip_filter (Optional[Set[str]], optional): IP addresses to filter.

    Returns:
        Dict[str, str]: A dictionary of connected gateways.
    """
    result: Dict[str, str] = {}
    ip_filter = set(ip_filter) if ip_filter else set()

    command = "netstat -tan | grep ESTABLISHED | grep -E ':(1039|2944|2945)'"
    pattern = r"([0-9.]+):(1039|2944|2945)\s+([0-9.]+):([0-9]+)"
    protocols = {"1039": "ptls", "2944": "tls", "2945": "unenc"}

    connections = os.popen(command).read()

    for m in re.finditer(pattern, connections):
        ip, port = m.group(3, 2)

        proto = protocols.get(port, "unknown")
        logging.debug(f"Found GW using {proto} - {ip}")

        if not ip_filter or ip in ip_filter:
            result[ip] = proto
            logging.info(f"Added GW to results - {ip}")

    if not result:
        # For testing purposes, return a dummy dictionary
        return {"10.44.244.51": "tls", "10.10.48.58": "ptls"}

    return {ip: result[ip] for ip in sorted(result)}

async def _run_cmd(
    program: str, args: List[str], name: Optional[str] = None
) -> Tuple[str, str, Optional[int]]:
    proc = None

    try:
        proc = await asyncio.create_subprocess_exec(
            program,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        logger.debug(f"Created PID {proc.pid} - {name}")

    except Exception as e:
        error_msg = f"{e.__class__.__name__} - {name}"
        logger.error(error_msg)
        raise e

    try:
        stdout_bytes, stderr_bytes = await proc.communicate()

        return (
            stdout_bytes.decode().strip(),
            stderr_bytes.decode().strip(),
            proc.returncode,
        )

    except asyncio.CancelledError as e:
        if proc.returncode is None:
            logger.debug(f"Killing PID {proc.pid} - {name}")
            try:
                proc.kill()
                await proc.wait()
            except Exception as e2:
                error_msg = f"Cleanup {e2.__class__.__name__} - {name}"
                logger.error(error_msg)
        raise e

    except Exception as e:
        raise

    finally:
        if proc:
            # WORKAROUND FOR PYTHON 3.6:
            if hasattr(proc, "_transport") and proc._transport:  # type: ignore
                try:
                    proc._transport.close()  # type: ignore
                    proc._transport = None  # type: ignore
                except Exception:
                    pass

async def run_cmd(
    program: str,
    args: List[str],
    timeout: float = 10.0,
    name: Optional[str] = None,
) -> CommandResult:
    """
    Controller function that catches all exceptions and returns a structured result.
    """
    try:
        logger.info(f"Starting '{program}' - {name}")
        stdout, stderr, returncode = await asyncio.wait_for(
            _run_cmd(program, args, name), timeout=timeout
        )

        logger.info(f"Completed '{program}' with rc {returncode} - {name}")
        return CommandResult(stdout, stderr, returncode=returncode, name=name)

    except asyncio.TimeoutError:
        logger.error(f"TimeoutError after {timeout}secs - {name}")
        return CommandResult("", "", None, error_type="Timeout")

    except asyncio.CancelledError:
        raise

    except Exception as e:
        e_name = e.__class__.__name__
        error_msg = f"{e_name} - {name}"
        if e_name != "CancelledError":
            logger.error(f"{error_msg}")
        return CommandResult("", "", None, error_type=error_msg, name=name)

def done_task_callback(task):
    name = task.name if hasattr(task, "name") else task._coro.__name__
    TASKs.discard(task)
    logger.debug(f"Discarded task from TASKs - {name}")

def schedule_task(
    coro: Coroutine[Any, Any, Any],
    name: Optional[str] = None,
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> asyncio.Task:
    """Patched version of create_task that assigns a name to the task.

    Parameters
    ----------
    loop : asyncio.AbstractEventLoop
        The event loop to create the task in.
    coro : Coroutine[Any, Any, Any]
        The coroutine to run in the task.
    name : Optional[str], optional
        The name to assign to the task. Defaults to None.

    Returns
    -------
    asyncio.Task
        The newly created task.
    """
    name = name if name else coro.__name__
    loop = loop if loop else asyncio.get_event_loop()

    task = asyncio.ensure_future(coro, loop=loop)
    task.name = name  # type: ignore
    logger.debug(f"Scheduled '{coro.__name__}' - {task.name}")  # type: ignore

    task.add_done_callback(done_task_callback)
    TASKs.add(task)
    logger.debug(f"Added task to TASKs - {name}")

    return task

############################## END FUNCTIONS #################################

def custom_exception_handler(loop, context):
    exc = context.get("exception")
    # Suppress the spurious TimeoutError reported at shutdown.
    if isinstance(exc, asyncio.CancelledError) or isinstance(
        exc, asyncio.TimeoutError
    ):
        # Optionally, log that we suppressed it:
        # print("Suppressed spurious TimeoutError during shutdown.")
        logger.error(f"{repr(exc)} silenced")
        return
    # For other exceptions, call the default handler.
    loop.default_exception_handler(context)

if __name__ == "__main__":
    pass
