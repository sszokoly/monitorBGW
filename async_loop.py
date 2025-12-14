import asyncio
import time
from utils import *
from bgw import BGW
from typing import Optional
from asyncio import Queue, Semaphore
import json
from storage import MemoryStorage
from rtpparser import parse_rtpstat

BGWs = {}
STORAGE = MemoryStorage()
TASKS = set()


def callback(ok, err, total):
    print(f"Callback ok:{ok}/err:{err}/total:{total}")
    print(BGWs["10.10.48.58"].fw)


async def process_queue(queue, storage, callback=None) -> None:
    """
    Asynchronously processes items from a queue.

    Args:
        queue (asyncio.Queue): The queue to process.
        callback (Optional[Callable[[BGW], None]], optional): A callback.
        name (str, optional): The name of the task for logging.

    Returns:
        None
    """
    c = 0
    while True:
        item = await queue.get()
        process_item(item, storage=storage, callback=callback)
        c += 1
        logger.info(f"Got item ({c}) from process queue")
        logger.debug(f"{item}")


def process_item(item, storage=STORAGE, callback=None) -> None:
    """
    Updates a BGW instance and RTP Storage with item from a JSON string.

    Args:
        item (str): The JSON string containing the data.
        callback (Optional[Callable[[BGW], None]], optional): A callback.
        name (str, optional): The name of the function for logging.

    Returns:
        None
    """
    try:
        data = json.loads(item.stdout, strict=False)
    except json.JSONDecodeError:
        logger.error(f"JSONDecodeError: {item}")
    else:
        bgw_ip = data.get("bgw_ip")
        if bgw_ip in BGWs:
            act_sess_ids = set()
            BGWs[bgw_ip].update(**data)
            logger.info(f"Updated BGW - {bgw_ip}")

            rtp_sessions = data.get("rtp_sessions")
            for global_id, rtpstat in rtp_sessions.items():
                rtpdetailed = parse_rtpstat(global_id, rtpstat)

                if rtpdetailed:
                    storage[global_id] = rtpdetailed
                    session_id = f"{rtpdetailed.session_id:0>5}"
                    logger.info(f"Added {session_id} to storage - {bgw_ip}")

                    if rtpdetailed.is_active:
                        act_sess_ids.add(f"{session_id}")

            BGWs[bgw_ip].active_session_ids = act_sess_ids
            logger.info(f"Found {len(act_sess_ids)} active sessions - {bgw_ip}")

            if callback:
                callback()


async def query(
    bgw: BGW,
    semaphore: Optional[asyncio.Semaphore] = None,
    name: Optional[str] = None,
    queue: Optional[asyncio.Queue] = None,
    timeout: float = 25,
    polling_secs: float = 30,
) -> Optional[str]:
    """
    Asynchronously queries a BGW and returns the command output.

    If a queue is provided, the output is placed onto the queue and the
    function does not return a value.
    Otherwise, the output is returned directly.

    Args:
        bgw (BGW): The BGW instance to query.
        timeout (float, optional): The timeout for the command execution.
        queue (Optional[asyncio.Queue], optional): A queue to place the output.
        polling_secs (float, optional): The interval between polling attempts.
        semaphore (Optional[asyncio.Semaphore], optional): A semaphore.
        name (Optional[str], optional): The name of the task for logging.

    Returns:
        Optional[str]: The output of the command if no queue is provided.
    """

    name = name if name else bgw.bgw_ip
    semaphore = semaphore if semaphore else asyncio.Semaphore(1)
    avg_sleep = polling_secs

    while True:
        try:
            start = time.monotonic()
            async with semaphore:
                logger.debug(
                    f"Semaphore acquired ({semaphore._value} free) - {name}"
                )

                diff = time.monotonic() - start
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

                sleep = round(max(polling_secs - diff, 0), 2)
                avg_sleep = round((avg_sleep + sleep) / 2, 2)
                logger.debug(f"Sleeping {sleep}s (avg {avg_sleep}s) in {name}")
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


async def discovery(loop, callback=None):
    BGWs.clear()
    bgws = {ip: BGW(ip, proto) for ip, proto in connected_bgws().items()}
    tasks = schedule_queries(bgws=bgws, loop=loop)
    ok, err, total = 0, 0, len(tasks)

    for fut in asyncio.as_completed(tasks):
        result = await fut

        if isinstance(result, Exception):
            err += 1

        elif isinstance(result, CommandResult) and result.returncode == 0:
            bgw_ip = result.name
            BGWs.update({bgw_ip: bgws[bgw_ip]})
            logger.info(f"Updated BGWs - {bgw_ip}")
            process_item(result)
            ok += 1

        if callback:
            callback(ok, err, total)


def schedule_queries(loop, bgws=None, callback=None):
    queue = Queue(loop=loop) if bgws is None else None
    bgws = bgws if bgws else BGWs
    semaphore = Semaphore(config.get("max_polling", 20))
    timeout = config.get("timeout", 25)
    polling_secs = config.get("polling_secs", 15)
    storage = config.get("storage", STORAGE)

    if queue:
        schedule_task(process_queue(queue, storage, callback), loop=loop)

    tasks = []
    for bgw_ip, bgw in bgws.items():
        task = schedule_task(
            query(
                bgw,
                semaphore=semaphore,
                name=bgw_ip,
                queue=queue,
                timeout=timeout,
                polling_secs=polling_secs,
            ),
            name=bgw_ip,
            loop=loop,
        )
        tasks.append(task)

    return tasks


def start_discovery(loop, discovery_done_callback=None):
    schedule_task(
        discovery(loop=loop, callback=discovery_done_callback),
        name="discovery",
        loop=loop,
    )


def stop_discovery(loop):
    shutdown_async_loop(loop)


def start_queries(loop):
    schedule_queries(bgws=None, loop=loop)


def stop_queries(loop):
    shutdown_async_loop(loop)


def main():
    loop = startup_async_loop()
    start_discovery(loop)
    start = time.time()
    discovery_done = False
    query_done = False

    try:
        while True:
            if loop:
                tick_async_loop(loop)
            time.sleep(0.05)
            end = time.time()
            c = end - start
            if c > 20 and not discovery_done:
                discovery_done = True
                stop_discovery(loop)
                loop = None
            elif c > 25 and not query_done:
                loop = startup_async_loop()
                BGWs["10.10.48.58"].queue.put("capture start")
                start_queries(loop)
                query_done = True
            elif c > 300:
                stop_queries(loop)
                loop = None
                break
    finally:
        if loop is not None:
            shutdown_async_loop(loop)


if __name__ == "__main__":
    main()
