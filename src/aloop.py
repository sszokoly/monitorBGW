#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS ##################################

import asyncio
import json
import os
import re
import time
from asyncio import Queue, Semaphore
from datetime import datetime
from typing import Any, Callable, MutableMapping, Coroutine, Dict, List, Optional, Tuple, Set, Mapping, Iterable, no_type_check_decorator

############################## END IMPORTS ####################################

from config import CONFIG
from bgw import BGW
from storage import MemoryStorage, AbstractRepository
from rtpparser import parse_rtpstat
from ahttp import start_http_server
from rtpparser import RTPDetails
from script import EXPECT_SCRIPT
from storage import GWs, BGWs, PCAPs, RTPs
import logging
logger = logging.getLogger(__name__)

############################## BEGIN ALOOP ####################################

TASKs = set()
BGWMap = Mapping[str, Any]
Progress = Tuple[int, int, int]
ProgressCallback = Callable[[Progress], None]

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

class Capture:
    """A consistent container for command output."""

    remote_ip: str
    filename: str
    file_size: int
    received_timestamp: datetime
    capinfos: str
    rtpinfos: str
    gw_number: str

    def __init__(
        self,
        remote_ip: str,
        filename: str,
        file_size: int,
        received_timestamp: datetime,
        capinfos: str = "",
        rtpinfos: str = "",
        gw_number: str = ""
    ) -> None:
        """
        Initializes the Capture object.
        """
        self.remote_ip = remote_ip
        self.filename = filename
        self.file_size = file_size
        self.received_timestamp = received_timestamp
        self.capinfos = capinfos
        self.rtpinfos = rtpinfos
        self.gw_number = gw_number

        self._first_packet_time = None
        self._last_packet_time = None
        self._rtp_streams = None
        self._rtp_problems = None

    @property
    def received_timestamp_str(self):
        return self.received_timestamp.strftime("%Y-%m-%d,%H:%M:%S")

    @property
    def first_packet_time(self):
        if self._first_packet_time:
            return self._first_packet_time
        
        if not self.capinfos:
            return ""
        
        m = re.search(r"First packet time:\s+(.*?)\.", self.capinfos)
        self._first_packet_time = m.group(1) if m else ""
        return self._first_packet_time 
            
    @property
    def last_packet_time(self):
        if self._last_packet_time:
            return self._last_packet_time
        
        if not self.capinfos:
            return ""
        
        m = re.search(r"Last packet time:\s+(.*?)\.", self.capinfos)
        self._last_packet_time = m.group(1) if m else ""
        return self._last_packet_time

    @property
    def rtp_problems(self):
        if self._rtp_problems:
            return self._rtp_problems
        
        if not self.rtpinfos:
            return 0
        
        lines = self.rtpinfos.splitlines()
        problems = sum(1 for x in lines if x.strip().endswith("X"))
        self._rtp_problems = problems
        
        return self._rtp_problems

    @property
    def rtp_streams(self):
        if self._rtp_streams:
            return self._rtp_streams
        
        if not self.rtpinfos:
            return ""
        
        rtps = sum(1 for x in self.rtpinfos.splitlines() if "0x" in x)
        self._rtp_streams = rtps
        
        return self._rtp_streams

    def __repr__(self) -> str:
        """
        Provides a string representation for debugging and printing
        """
        fields = [
            f"remote_ip={repr(self.remote_ip)}",
            f"filename={repr(self.filename)}",
            f"file_size={repr(self.file_size)}",
            f"received_timestamp={repr(self.received_timestamp)}",
            f"capinfos={repr(self.capinfos)}",
            f"rtpinfos={repr(self.rtpinfos)}",
            f"gw_number={repr(self.gw_number)}"
        ]

        return f"Capture({', '.join(fields)})"

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
        commands: List[str] = CONFIG["discovery_commands"][:]
        prev_last_session_id: str = ""
        prev_active_session_ids: Iterable[str] = []

    else:
        # Regular polling
        rtp_stats = 1
        prev_last_session_id = bgw.last_session_id or ""
        prev_active_session_ids = sorted(bgw.active_session_ids)
        commands = CONFIG["query_commands"][:]

        if not bgw.queue.empty():
            queued_commands = bgw.queue.get_nowait()
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
        "user": CONFIG["user"],
        "passwd": CONFIG["passwd"],
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

    return {ip: result[ip] for ip in sorted(result)}

async def _run_cmd(
    program: str,
    args: List[str],
    name: Optional[str] = None,
) -> Tuple[str, str, Optional[int]]:
    """
    Execute an external command asynchronously and capture output.

    This is a small wrapper around `asyncio.create_subprocess_exec()` that
    returns decoded stdout/stderr and the process return code.

    Cancellation handling:
        - If the coroutine is cancelled while the subprocess is still running,
          the subprocess is killed and waited for.

    Python 3.6 note:
        - Some environments can leave transports open longer than desired; the
          `finally` block includes a defensive transport close workaround.

    Args:
        program: Executable name/path.
        args: Argument vector (without the program itself).
        name: Optional label used in logs to identify the caller/context.

    Returns:
        A tuple of (stdout_text, stderr_text, returncode). The return code is
        typically an int; it may be None only in unusual edge cases.

    Raises:
        OSError / FileNotFoundError: If the program cannot be executed.
        asyncio.CancelledError: If the coroutine is cancelled.
        Exception: Propagates unexpected failures from subprocess execution.
    """
    proc: Optional[asyncio.subprocess.Process] = None

    try:
        proc = await asyncio.create_subprocess_exec(
            program,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.debug("Created PID %s - %s", proc.pid, name)

        stdout_bytes, stderr_bytes = await proc.communicate()

        stdout_text = stdout_bytes.decode(errors="replace").strip()
        stderr_text = stderr_bytes.decode(errors="replace").strip()
        return stdout_text, stderr_text, proc.returncode

    except asyncio.CancelledError:
        if proc is not None and proc.returncode is None:
            logger.debug("Killing PID %s - %s", proc.pid, name)
            try:
                proc.kill()
                await proc.wait()
            except Exception as e2:
                logger.error("Cleanup %s - %s", e2.__class__.__name__, name)
        raise

    except Exception as e:
        # Keep your original behavior: log a short message and re-raise.
        logger.error("%s - %s", e.__class__.__name__, name)
        raise

    finally:
        # WORKAROUND FOR PYTHON 3.6:
        # Some 3.6/older asyncio implementations can keep transports open.
        if proc is not None and hasattr(proc, "_transport"):  # type: ignore
            transport = getattr(proc, "_transport", None)  # type: ignore
            if transport:
                try:
                    transport.close()
                    setattr(proc, "_transport", None)  # type: ignore
                except Exception:
                    pass

async def run_cmd(
    program: str,
    args: List[str],
    timeout: float = 10.0,
    name: Optional[str] = None,
) -> CommandResult:
    """
    Run an external command asynchronously with a timeout and return a
    structured result.

    This coroutine wraps `_run_cmd()` and adds:
      - Timeout handling via `asyncio.wait_for`
      - Consistent logging
      - Conversion of failures into a `CommandResult` instance

    Args:
        program: Executable name or path.
        args: Argument vector (excluding the program itself).
        timeout: Maximum execution time in seconds before the command is
            cancelled.
        name: Optional label used for logging and propagated into the
            returned `CommandResult`.

    Returns:
        CommandResult:
            - stdout: Captured standard output (string).
            - stderr: Captured standard error (string).
            - returncode: Process return code, or None on failure/timeout.
            - name: The optional command name.
            - error_type: Set when an error or timeout occurred.

    Raises:
        asyncio.CancelledError:
            Propagated if the coroutine itself is cancelled.
    """
    try:
        logger.info("Starting '%s' - %s", program, name)

        stdout, stderr, returncode = await asyncio.wait_for(
            _run_cmd(program, args, name),
            timeout=timeout,
        )

        logger.info(
            "Completed '%s' with rc %s - %s",
            program,
            returncode,
            name,
        )

        return CommandResult(
            stdout,
            stderr,
            returncode=returncode,
            name=name,
        )

    except asyncio.TimeoutError:
        logger.error(
            "TimeoutError after %.1f secs - %s",
            timeout,
            name,
        )
        return CommandResult(
            "",
            "",
            returncode=None,
            error_type="Timeout",
            name=name,
        )

    except asyncio.CancelledError:
        # Let task cancellation propagate normally
        raise

    except Exception as e:
        error_name = e.__class__.__name__
        error_msg = f"{error_name} - {name}"

        logger.error("%s", error_msg)

        return CommandResult(
            "",
            "",
            returncode=None,
            error_type=error_msg,
            name=name,
        )

async def process_queue(
    queue: "asyncio.Queue[Any]",
    storage: "AbstractRepository[str, RTPDetails]",
    callback: Optional[Callable[[], None]] = None,
    nok_rtp_only: bool = False
) -> None:
    """Continuously consume items from an asyncio queue and process them.

    This coroutine blocks on ``queue.get()`` and forwards each received item to
    ``process_item(...)`` to update BGW state and the RTP session storage.

    Args:
        queue: An asyncio queue yielding items to be processed (often a
            subprocess result / message containing JSON in ``item.stdout``).
        storage: Mutable mapping that will be updated by ``process_item``.
            Typically a ``MemoryStorage[str, RTPDetails]`` or similar.
        callback: Optional callable invoked by ``process_item`` after updates.

    Returns:
        None.
    """
    while True:
        item = await queue.get()
        try:
            logger.debug("Got item from process queue: %r", item)
            process_item(
                item,
                storage=storage,
                callback=callback,
                nok_rtp_only=nok_rtp_only
            )
        finally:
            try:
                queue.task_done()
            except Exception:
                pass

def process_item(
    item: Any,
    bgw: Optional["BGW"] = None,
    storage: "AbstractRepository[str, RTPDetails]" = RTPs,
    callback: Optional[Callable[[], None]] = None,
    nok_rtp_only: bool = False
) -> None:
    """Process a single queue item and update BGW + RTP session storage.

    Expects ``item.stdout`` to contain a JSON string with (at least) gateway
    identifiers and optionally a session map.

    Expected JSON keys (commonly used):
        - gw_number: str
        - lan_ip: str
        - rtp_sessions: mapping[str, Any] where values are per-session payloads
        - plus any keys accepted by ``BGW.update(**data)``

    Side effects:
        - Updates global gateway index ``GWs`` (lan_ip -> gw_number)
        - Updates BGW via ``bgw.update(**data)``
        - Parses RTP sessions and writes to ``storage[global_id]``
        - Updates ``bgw.active_session_ids``
        - Persists BGW back into ``BGWs[gw_number]``
        - Calls ``callback()`` if provided

    Args:
        item: An object with a ``stdout`` attribute containing JSON text.
        bgw: The BGW instance to update. If None, it's looked up in ``BGWs``.
        storage: Mapping to receive parsed RTPDetails by global session id.
            Typically your ``RTPs`` MemoryStorage.
        callback: Optional callable invoked after processing.
        nok_rtp_only: If True, only sessions considered "NOK" are stored
            (based on the logic below). Active sessions are tracked separately.

    Returns:
        None.
    """
    try:
        data = json.loads(getattr(item, "stdout", ""), strict=False)
    except json.JSONDecodeError:
        logger.error("JSONDecodeError: %r", item)
        return

    if not isinstance(data, dict):
        logger.debug("Unexpected JSON type %r in %r", type(data), item)
        return

    gw_number = data.get("gw_number")
    lan_ip = data.get("lan_ip")

    if not gw_number and not lan_ip:
        logger.debug("Unexpected data in %r", item)
        return

    if bgw is None:
        bgw = BGWs.get(gw_number)
        if not bgw:
            return

    # Keep a lan_ip -> gw_number index for quick reverse lookup.
    if lan_ip and lan_ip not in GWs:
        GWs.update({lan_ip: gw_number})
        logger.info("Updated GWs with %s -> %s", lan_ip, gw_number)

    active_session_ids: Set[str] = set()

    bgw.update(**data)
    logger.debug(
        "Updated BGW %s with data (%s) - %s", gw_number, len(data), lan_ip
    )

    rtp_sessions = data.get("rtp_sessions", {})  # type: Any
    if isinstance(rtp_sessions, dict):
        for global_id, rtpstat in rtp_sessions.items():
            rtpdetails = parse_rtpstat(global_id, rtpstat)
            if rtpdetails is None:
                continue

            session_id = "{:0>5}".format(rtpdetails.session_id)

            if rtpdetails.is_active:
                active_session_ids.add(session_id)
                # If nok_rtp_only is True wait for the session to complete
                if nok_rtp_only:
                    continue

            if nok_rtp_only and getattr(rtpdetails, "nok", None) == "None":
                # If nok_rtp_only is True don't store good sessions
                continue

            storage.put({global_id: rtpdetails})
            logger.info("Updated storage with %s - %s", session_id, lan_ip)
    else:
        logger.debug("rtp_sessions is not a dict (got %r)", type(rtp_sessions))

    bgw.active_session_ids = active_session_ids
    if active_session_ids:
        logger.info("%d active sessions - %s", len(active_session_ids), lan_ip)

    if gw_number:
        BGWs.put({gw_number: bgw})

    if callback:
        callback()

async def process_upload_queue(
    queue: "asyncio.Queue",
    storage: "AbstractRepository[str, Capture]",
    callback: Optional[Callable[[], None]] = None,
) -> None:
    """Continuously process items from the upload queue.

    Expected item keys:
      - "filename": str
      - "remote_ip": str

    Args:
        queue: An asyncio.Queue that yields dict-like items.
        storage: Storage passed through to process_upload_item.
        callback: Optional callable invoked by process_upload_item.

    Returns:
        None. Runs forever until cancelled.
    """
    while True:
        item = await queue.get()
        try:
            logger.info("Got %r from upload queue", item)
            filename = item.get("filename")
            remote_ip = item.get("remote_ip")

            if not filename or not isinstance(filename, str):
                logger.debug("Upload item missing/invalid filename: %r", item)
                process_upload_item(item, storage=storage, callback=callback)
                continue

            upload_dir = CONFIG.get("upload_dir", "./")
            pcapfile = os.path.join(upload_dir, filename)

            gw_number = "NA"
            if remote_ip:
                gw_number = GWs.get(remote_ip, "NA")

            if os.path.exists(pcapfile):
                try:
                    capinfos_output = await capinfos(pcapfile)
                except Exception as e:
                    logger.error("capinfos failed for %s: %s", pcapfile, e)
                    capinfos_output = f"{e}"

                try:
                    rtpinfos_output = await rtpinfos(pcapfile)
                except Exception as e:
                    logger.error("rtpinfos failed for %s: %s", pcapfile, e)
                    rtpinfos_output = f"{e}"

                item.update(
                    {
                        "capinfos": capinfos_output,
                        "rtpinfos": rtpinfos_output,
                        "gw_number": gw_number,
                    }
                )
            else:
                item.update({"gw_number": gw_number})

            process_upload_item(item, storage=storage, callback=callback)

        finally:
            try:
                queue.task_done()
            except Exception:
                pass

def process_upload_item(
    item: MutableMapping[str, Any],
    storage: "AbstractRepository[str, Capture]" = PCAPs,
    callback: Optional[Callable[[], None]] = None,
) -> None:
    """Convert an upload metadata dict into a `Capture` and store it.

    This function takes the dict produced by your upload pipeline (possibly
    enriched with `capinfos`, `rtpinfos`, and `gw_number`), instantiates a
    `Capture`, and inserts it into the capture storage keyed by filename.

    Args:
        item:
            Upload item mapping used to construct `Capture(**item)`.
        storage:
            Target capture storage. Defaults to global `PCAPs`. The object is
            expected to implement `put({key: value})`.
        callback:
            Optional callable invoked after the item is stored.
    """
    try:
        capture = Capture(**item)
    except Exception as e:
        logger.error("Capture instantiation failed for %s: %s", item, e)
        return

    storage.put({capture.filename: capture})

    logger.info("Put %s into capture storage", capture.filename)
    logger.debug("%r", capture)

    if callback is not None:
        callback()

def done_task_callback(task):
    name = task.name if hasattr(task, "name") else task._coro.__name__
    TASKs.discard(task)
    logger.debug(f"Discarded task from TASKs - {name}")

def schedule_task(
    coro: Coroutine[Any, Any, Any],
    name: Optional[str] = None,
    loop: Optional["asyncio.AbstractEventLoop"] = None,
) -> asyncio.Task:
    """Schedule a coroutine as an asyncio Task on the given event loop.

    This helper wraps `asyncio.ensure_future()` to:
      - Bind the task to a specific event loop (or the current one),
      - Assign a human-readable task name (for logging/debugging),
      - Register a completion callback,
      - Track the task in the global TASKs registry.

    Notes:
        - On Python 3.6, `asyncio.Task` does not officially expose a
          `name` attribute. Assigning `task.name` is therefore a
          best-effort, runtime-only convenience and is marked with
          `# type: ignore`.
        - The `done_task_callback` function is expected to handle cleanup
          (e.g. logging, removing the task from TASKs, error reporting).

    Args:
        coro: The coroutine object to schedule.
        name: Optional human-readable name for the task. If omitted,
            `coro.__name__` is used.
        loop: The event loop on which to schedule the task. If omitted,
            the current event loop is used.

    Returns:
        The created and scheduled asyncio.Task instance.
    """
    task_name = name if name else coro.__name__
    event_loop = loop if loop else asyncio.get_event_loop()

    task: asyncio.Task = asyncio.ensure_future(coro, loop=event_loop)
    task.name = task_name  # type: ignore[attr-defined]

    logger.debug("Scheduled '%s' as task '%s'", coro.__name__, task_name)

    task.add_done_callback(done_task_callback)
    TASKs.add(task)

    logger.debug("Added task to TASKs - %s", task_name)

    return task

async def query(
    bgw: BGW,
    semaphore: Optional[asyncio.Semaphore] = None,
    name: Optional[str] = None,
    queue: Optional[asyncio.Queue] = None,
    timeout: float = 25,
    polling_secs: float = 30,
) -> Optional[CommandResult]:

    name = name if name else bgw.lan_ip
    semaphore = semaphore if semaphore else asyncio.Semaphore(1)
    avg_sleep = 0.0
    sleep_n = 0

    while True:
        try:
            t0 = time.monotonic()
            async with semaphore:
                logger.debug(
                    f"Semaphore acquired ({semaphore._value} free) - {name}"
                )

                result = await run_cmd(
                    program="expect",
                    args=["-c", create_bgw_script(bgw)],
                    timeout=timeout,
                    name=name,
                )

                if isinstance(result, CommandResult):
                    if not queue:
                        return result
                    await queue.put(result)

            elapsed = time.monotonic() - t0
            sleep = round(max(polling_secs - elapsed, 0.0), 2)
            
            sleep_n += 1
            avg_sleep = (avg_sleep * (sleep_n - 1) + sleep) / sleep_n
            avg_sleep = round(avg_sleep, 2)
            
            logger.debug(
                f"Semaphore released ({semaphore._value} free), "
                f"Cycle elapsed {elapsed:.2f}s, sleeping {sleep:.2f}s "
                f"(avg_sleep {avg_sleep:.2f}s) - {name}"
            )

            if sleep:
                await asyncio.sleep(sleep)

        except asyncio.CancelledError:
            logger.error(f"CancelledError - {name}")
            raise

        except asyncio.TimeoutError:
            logger.error(f"TimeoutError in {name}")
            if not queue:
                raise

        except Exception as e:
            logger.error(f"{repr(e)} in {name}")
            if not queue:
                raise

        finally:
            logger.debug(
                f"Semaphore released ({semaphore._value} free) - {name}"
            )

async def discovery(
    loop: "asyncio.AbstractEventLoop",
    callback: Optional[ProgressCallback] = None,
    ip_filter: Optional[Any] = None,
    ip_input: Optional[Any] = None,
) -> None:
    """Discover connected gateways and process scheduled query results.

    Args:
        loop: Event loop used by `schedule_queries`.
        callback: Optional progress callback invoked as (ok, err, total).
        ip_filter: Optional filter passed to `connected_gws(ip_filter)`.
        ip_input: Optional filter passed to `connected_gws(ip_input)`
    Returns:
        None
    """
    # connected_gws() should return mapping: lan_ip -> proto
    gw_map: Dict[str, str] = connected_gws(ip_filter, ip_input)

    bgws = {ip: BGW(ip, proto) for ip, proto in gw_map.items()}
    if not bgws:
        return

    tasks = schedule_queries(loop, bgws)
    total = len(tasks)
    ok = 0
    err = 0

    if callback:
        callback((ok, err, total))

    for fut in asyncio.as_completed(tasks):
        try:
            result = await fut
        except Exception:
            err += 1
            if callback:
                callback((ok, err, total))
            continue

        if isinstance(result, Exception):
            err += 1
            if callback:
                callback((ok, err, total))
            continue

        # Successful command result
        if isinstance(result, CommandResult) and result.returncode == 0:
            lan_ip = getattr(result, "name", None)
            if lan_ip and lan_ip in bgws:
                process_item(result, bgw=bgws[lan_ip])
                ok += 1
            else:
                err += 1
        else:
            err += 1
            logger.error("Query failed: %r", result)

        if callback:
            callback((ok, err, total))

def schedule_queries(
    loop: "asyncio.AbstractEventLoop",
    bgws: Optional[BGWMap] = None,
    callback: Optional[Callable[[], None]] = None,
) -> List["asyncio.Future[Any]"]:
    """Schedule polling/query tasks for BGWs.

      - Creates a shared semaphore limiting concurrent polling.
      - Optionally creates a work queue (when polling).
      - Schedules one `query(...)` task per BGW and returns the task list.

    Args:
        loop: Event loop to schedule tasks on.
        bgws: Optional mapping BGWs. If omitted, uses global `BGWs`.
        callback: Optional progress callback passed to `process_queue`.

    Returns:
        A list of scheduled task objects (Tasks/Futures), one per BGW query.
        (The queue consumer task is scheduled but not included in this list.)
    """
    queue = asyncio.Queue(loop=loop) if GWs else None  # type: ignore

    bgw_map = bgws if bgws is not None else BGWs  # expects .items()

    semaphore = Semaphore(int(CONFIG.get("max_polling", 20)))
    timeout = int(CONFIG.get("timeout", 25))
    polling_secs = int(CONFIG.get("polling_secs", 15))

    # Storage is passed into process_queue
    storage: AbstractRepository[str, RTPDetails] = CONFIG.get("storage", RTPs)

    if queue is not None:
        nok_rtp_only = bool(CONFIG.get("nok_rtp_only", False))
        schedule_task(
            process_queue(
                queue,
                storage=storage,
                callback=callback,
                nok_rtp_only=nok_rtp_only
            ),
            loop=loop,
        )

    tasks: List["asyncio.Future[Any]"] = []

    for lan_ip, bgw in bgw_map.items():
        task = schedule_task(
            query(
                bgw,
                semaphore=semaphore,
                name=lan_ip,
                queue=queue,
                timeout=timeout,
                polling_secs=polling_secs,
            ),
            name=lan_ip,
            loop=loop,
        )
        tasks.append(task)

    return tasks

def schedule_http_server(
    loop: "asyncio.AbstractEventLoop",
) -> None:
    """Schedule the HTTP upload server and its processing task.

    This function conditionally starts an HTTP server used for receiving
    uploaded capture files and a background task that processes uploaded
    items from a queue.

    Behaviour:
        - If no HTTP server host is CONFIGured, nothing is scheduled.
        - An asyncio.Queue is created for uploaded items.
        - The HTTP server coroutine is scheduled on the given event loop.
        - A consumer coroutine (`process_upload_queue`) is scheduled to
          process items placed onto the upload queue.

    Args:
        loop: The asyncio event loop on which to schedule tasks.

    Returns:
        None
    """
    http_server: Optional[str] = CONFIG.get("http_server")

    if not http_server:
        logger.warning(f"HTTP server will not be started")
        return

    upload_queue: "asyncio.Queue" = asyncio.Queue(loop=loop)  # type: ignore

    schedule_task(
        start_http_server(
            host=http_server,
            port=int(CONFIG.get("http_port", 8080)),
            upload_dir=CONFIG.get("upload_dir", "./"),
            upload_queue=upload_queue,
        ),
        name="http_server",
        loop=loop,
    )

    schedule_task(
        process_upload_queue(upload_queue, storage=PCAPs),
        name="process_upload_queue",
        loop=loop,
    )

async def rtpinfos(pcapfile):
    """
    Extract RTP stream statistics from a pcap file using tshark.

    This coroutine invokes `tshark` with RTP analysis options enabled and
    returns the textual output of the RTP stream summary.

    Args:
        pcapfile: Path to the pcap file to analyse.

    Returns:
        A string containing the RTP stream information produced by tshark.
        If the command fails (non-zero return code), an empty string is
        returned.
    """
    program = "tshark"
    args = ["-n", "-q", "-o", "rtp.heuristic_rtp:TRUE",
            "-z", "rtp,streams", "-r", pcapfile]

    result = await run_cmd(program, args)
    logger.debug(f"rtpinfos {result}")

    return "" if result.returncode else result.stdout.strip()

async def capinfos(pcapfile):
    """
    Extract capture metadata from a pcap file using capinfos.

    This coroutine runs the `capinfos` utility against the given pcap file
    and returns its textual output, which typically includes capture
    duration, packet counts, file size, and timestamps.

    Args:
        pcapfile: Path to the pcap file to analyse.

    Returns:
        A string containing the capinfos output.
        If the command fails (non-zero return code), an empty string is
        returned.
    """
    program = "capinfos"
    args = [pcapfile]

    result = await run_cmd(program, args)
    logger.debug(f"capinfos {result}")

    return "" if result.returncode else result.stdout.strip()

def startup_async_loop():
    """Sets up the non-blocking event loop and child watcher."""
    loop = asyncio.new_event_loop()
    
    # Create and attach NEW watcher BEFORE setting the loop
    watcher = asyncio.SafeChildWatcher()
    watcher.attach_loop(loop)
    asyncio.set_child_watcher(watcher)

    # Now set the event loop
    asyncio.set_event_loop(loop)
    logger.debug("Loop started")

    return loop

def tick_async_loop(loop):
    """Run one iteration of the asyncio loop."""
    if loop is None or loop.is_closed():
        return

    # Run ready callbacks/I/O once, then stop.
    loop.call_soon(loop.stop)
    loop.run_forever()

def request_shutdown(loop):
    """Schedule shutdown on the loop; do not block."""
    if loop is None or loop.is_closed():
        return

    logger.debug("Async loop shutdown requested")
    # Create a task inside the loop
    loop.create_task(_shutdown_async(loop))

    # Ensure the loop runs at least one more tick
    loop.call_soon(loop.stop)

async def _shutdown_async(loop):
    """Helper coroutine to prepare shutting down the loop"""
    await _cancel_all_tasks(loop)
    try:
        await loop.shutdown_asyncgens()
    except Exception:
        pass

async def _cancel_all_tasks(loop):
    logger.debug("Cancelling all tasks except current task")
    current = asyncio.Task.current_task(loop=loop)
    tasks = [
        t for t in asyncio.Task.all_tasks(loop=loop)
        if t is not current and not t.done()
    ]

    for t in tasks:
        t.cancel()

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

def finalize_loop_if_idle(loop):
    """Close loop once all tasks are done/cancelled."""
    if loop is None or loop.is_closed():
        return True

    logger.debug("Closing async loop")
    
    pending = [t for t in asyncio.Task.all_tasks(loop) if not t.done()]
    if pending:
        return False

    loop.close()
    return True

############################## END ALOOP ######################################

from asyncio import coroutines
from asyncio import events
from typing import Coroutine
from asyncio import tasks

def asyncio_run(
    main: Callable[..., Coroutine[Any, Any, Any]],
    *,
    debug: Optional[bool] = None
) -> Any:
    """Execute the coroutine and return the result.

    This function runs the passed coroutine, taking care of
    managing the asyncio event loop and finalizing asynchronous
    generators.

    This function cannot be called when another asyncio event loop is
    running in the same thread.

    If debug is True, the event loop will be run in debug mode.

    This function always creates a new event loop and closes it at the end.
    It should be used as a main entry point for asyncio programs, and should
    ideally only be called once.
    """
    if events._get_running_loop() is not None:
        raise RuntimeError(
            "asyncio.run() cannot be called from a running event loop")

    if not coroutines.iscoroutine(main):
        raise ValueError("a coroutine was expected, got {!r}".format(main))

    loop = events.new_event_loop()
    loop.set_exception_handler(custom_exception_handler)
    
    try:
        events.set_event_loop(loop)
        if debug is not None:
            loop.set_debug(debug)
        return loop.run_until_complete(main)
    
    except KeyboardInterrupt:
        print("Got signal: SIGINT, shutting down.")
    
    finally:
        try:
            _cancel_tasks(loop)
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            events.set_event_loop(None)
            loop.close()

def _cancel_tasks(loop):
    to_cancel = asyncio.Task.all_tasks()
    if not to_cancel:
        return

    for task in to_cancel:
        task.cancel()

    loop.run_until_complete(tasks.gather(*to_cancel, return_exceptions=True))

    for task in to_cancel:
        if task.cancelled():
            continue
        if task.exception() is not None:
            loop.call_exception_handler({
                'message': 'unhandled exception during asyncio.run() shutdown',
                'exception': task.exception(),
                'task': task,
            })

def custom_exception_handler(loop, context):
    exc = context.get('exception')
    # Suppress the spurious TimeoutError reported at shutdown.
    if isinstance(exc, asyncio.CancelledError) or isinstance(exc, asyncio.TimeoutError):
        logger.error(f"{repr(exc)} silenced")
        return
    loop.default_exception_handler(context)

if __name__ == "__main__":
    import time
    loop = startup_async_loop()
    task = schedule_task(
        discovery(loop=loop),
        name="discovery",
        loop=loop
    )
    tick_async_loop(loop=loop)
    time.sleep(1)
    tick_async_loop(loop=loop)
    time.sleep(1)
    tick_async_loop(loop=loop)
    time.sleep(25)
    tick_async_loop(loop=loop)
    print(BGWs)
    request_shutdown(loop=loop)