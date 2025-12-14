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

config = {
    "bgw_user": "root",
    "bgw_passwd": "cmb@Dm1n",
    "max_polling": 20,
    "timeout": 25,
    "polling_secs": 15,
    "loglevel": "DEBUG",
    "logfile": "bgw.log",
    "discovery_commands": [
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
    ],
    "query_commands": [
        "show voip-dsp",
        "show capture",
    ],
}

logger = logging.getLogger(__name__)
FORMAT = "%(asctime)s - %(levelname)8s - %(message)s [%(funcName)s:%(lineno)s]"
logging.basicConfig(format=FORMAT)
logger.setLevel(config["loglevel"])

TASKS = set()

COMPRESSED_EXPECT_SCRIPT = """\
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
"""


def compress_and_wrap(input_string, column_width=78):
    compressed_bytes = zlib.compress(input_string.encode("utf-8"))
    base64_bytes = base64.b64encode(compressed_bytes)
    wrapped = textwrap.fill(base64_bytes.decode("utf-8"), width=column_width)
    return wrapped


def unwrap_and_decompress(wrapped_text):
    base64_str = wrapped_text.replace("\n", "")
    compressed_bytes = base64.b64decode(base64_str)
    original_string = zlib.decompress(compressed_bytes).decode("utf-8")
    return original_string


EXPECT_SCRIPT = unwrap_and_decompress(COMPRESSED_EXPECT_SCRIPT)


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
            commands.extend(queued_commands)

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


def connected_bgws(ip_filter: Optional[Set[str]] = None) -> Dict[str, str]:
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
        logging.debug(f"Found BGW using {proto} - {ip}")

        if not ip_filter or ip in ip_filter:
            result[ip] = proto
            logging.info(f"Added BGW to results - {ip}")

    if not result:
        # For testing purposes, return a dummy dictionary
        return {"10.10.48.58": "ptls"}

    return {ip: result[ip] for ip in sorted(result)}


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


async def _run_cmd(
    program: str, args: List[str], name: Optional[str] = None
) -> Tuple[str, str, Optional[int]]:
    proc: Optional[asyncio.subprocess.Process] = None

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
    TASKS.discard(task)
    logger.debug(f"Discarded task from TASKS - {name}")


def startup_async_loop():
    """Sets up the non-blocking event loop and child watcher."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    watcher = asyncio.SafeChildWatcher()
    asyncio.set_child_watcher(watcher)
    watcher.attach_loop(loop)
    return loop


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
    TASKS.add(task)
    logger.debug(f"Added task to TASKS - {name}")

    return task


async def _cancel_async_tasks(loop=None):
    """
    Cancels all active tasks gracefully (runs inside the loop).
    """
    loop = loop if loop else asyncio.get_event_loop()
    current_task = asyncio.Task.current_task(loop)

    tasks_to_cancel = [
        task
        for task in asyncio.Task.all_tasks(loop)
        if not task.done() and task is not current_task
    ]

    if not tasks_to_cancel:
        return

    for task in tasks_to_cancel:
        task.cancel()

    await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
    for _ in range(5):
        await asyncio.sleep(0.01)


def shutdown_async_loop(loop=None):
    """Stops the event loop and cleans up all resources."""
    loop = loop if loop else asyncio.get_event_loop()

    try:
        loop.run_until_complete(_cancel_async_tasks(loop))
    except Exception as e:
        print(f"Async shutdown warning: {e}")

    gc.collect()

    watcher = asyncio.get_child_watcher()
    if hasattr(watcher, "detach_loop"):
        watcher.detach_loop()

    if not loop.is_closed():
        loop.close()


def tick_async_loop(loop=None):
    """
    Runs the event loop for a brief, non-blocking period.
    This processes all pending I/O and callbacks.
    """
    loop = loop if loop else asyncio.get_event_loop()

    ready_future = loop.create_future()
    ready_future.set_result(None)
    loop.run_until_complete(ready_future)


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


def asyncio_run(
    main: Callable[..., Coroutine[Any, Any, Any]],
    *,
    debug: Optional[bool] = None,
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
            "asyncio.run() cannot be called from a running event loop"
        )

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
            _cancel_all_tasks(loop)
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            events.set_event_loop(None)
            loop.close()


def _cancel_all_tasks(loop):
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
            loop.call_exception_handler(
                {
                    "message": "unhandled exception during asyncio.run() shutdown",
                    "exception": task.exception(),
                    "task": task,
                }
            )


if __name__ == "__main__":

    async def main():

        async def canceltask(task):
            await asyncio.sleep(1)
            task.cancel()
            await task

        asyncio.new_event_loop()
        task1 = schedule_task(
            run_cmd("echo", ["help"], timeout=3, name="task1")
        )
        task2 = schedule_task(
            run_cmd("/usr/bin/sleep", ["4"], timeout=3, name="task2")
        )
        task3 = schedule_task(
            run_cmd("/usr/bin/sleep", ["2"], timeout=3, name="task3")
        )
        task4 = schedule_task(canceltask(task3))
        results = await asyncio.gather(
            task1, task2, task3, task4, return_exceptions=True
        )
        for result in results:
            print(repr(result))

    asyncio_run(main(), debug=False)
