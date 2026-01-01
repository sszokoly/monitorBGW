#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS ##################################

############################## END IMPORTS ####################################
import asyncio
import time
from utils import *
from bgw import BGW
from typing import Optional
from asyncio import Queue, Semaphore
import json
from storage import MemoryStorage
from rtpparser import parse_rtpstat
from ahttp import start_http_server
from capture import Capture,  rtpinfos, capinfos

############################## BEGIN VARIABLES ################################

GWs = {}
BGWs = MemoryStorage(name="BGWs")
PCAPs = MemoryStorage(name="PCAPs")
RTPs = MemoryStorage(maxlen=36, name="RTPs")

############################## END VARIABLES ##################################
############################## BEGIN FUNCTIONS ################################

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

def process_item(item, bgw=None, storage=RTPs, callback=None) -> None:
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
        bgw_number = data.get("bgw_number")
        bgw_ip = data.get("bgw_ip")

        if not bgw_number and not bgw_ip:
            return
        
        if bgw and bgw_number not in BGWs:
            BGWs.put({bgw_number: bgw})
            GWs.update({bgw_ip: bgw_number})
            logger.info(f"Added BGW {bgw_number} to storage - {bgw_ip}")

        act_sess_ids = set()
        BGWs[bgw_number].update(**data)
        logger.info(f"Updated BGW {bgw_number} with {data} - {bgw_ip}")

        rtp_sessions = data.get("rtp_sessions", {})

        for global_id, rtpstat in rtp_sessions.items():
            rtpdetails = parse_rtpstat(global_id, rtpstat)

            if rtpdetails:
                storage[global_id] = rtpdetails
                session_id = f"{rtpdetails.session_id:0>5}"
                logger.info(f"Added {session_id} to storage - {bgw_ip}")

                if rtpdetails.is_active:
                    act_sess_ids.add(f"{session_id}")

        BGWs[bgw_number].active_session_ids = act_sess_ids
        if len(act_sess_ids) > 0:
            logger.info(f"Found {len(act_sess_ids)} active sessions - {bgw_ip}")

        if callback:
            callback()

async def process_upload_queue(queue, storage, callback=None) -> None:
    c = 0
    while True:
        item = await queue.get()
        c += 1
        logger.info(f"Got item ({c}) from upload queue")
        
        upload_dir = config.get("upload_dir", "./")
        pcapfile = os.path.join(upload_dir, item["filename"])
        bgw_number = GWs.get(item["remote_ip"], "NA")
        
        if os.path.exists(pcapfile):
            
            capinfos_output = await capinfos(pcapfile)
            rtpinfos_output = await rtpinfos(pcapfile)
            item.update({
                "capinfos": capinfos_output,
                "rtpinfos": rtpinfos_output,
                "bgw_number": bgw_number
            })
        
        logger.debug(f"{item}")
        process_upload_item(item, storage=storage, callback=callback)

def process_upload_item(item, storage=PCAPs, callback=None):
    capture = Capture(**item)
    storage.put({capture.filename: capture})
    logger.info(f"Put {capture.filename} into capture storage")
    if callback:
        callback()

async def query(
    bgw: BGW,
    semaphore: Optional[asyncio.Semaphore] = None,
    name: Optional[str] = None,
    queue: Optional[asyncio.Queue] = None,
    timeout: float = 25,
    polling_secs: float = 30,
) -> Optional[CommandResult]:

    name = name if name else bgw.bgw_ip
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

async def discovery(loop, callback=None, ip_filter=None):
    bgws = {
        ip: BGW(ip, proto) for ip, proto in connected_gws(ip_filter).items()
    }
    if not bgws:
        return

    tasks = schedule_queries(loop, bgws)
    ok, err, total = 0, 0, len(tasks)
    
    if callback:
        callback((ok, err, total))
    
    for fut in asyncio.as_completed(tasks):
        result = await fut

        if isinstance(result, Exception):
            err += 1

        elif isinstance(result, CommandResult) and result.returncode == 0:
            if result.name is not None:    
                bgw_ip = result.name
                if bgw_ip in bgws:
                    bgw = bgws[bgw_ip]
                    process_item(result, bgw)
                    ok += 1
            else:
                err += 1

        if callback:
            callback((ok, err, total))

def schedule_queries(loop, bgws=None, callback=None):
    queue = Queue(loop=loop) if GWs else None
    bgws = bgws if bgws else BGWs
    semaphore = Semaphore(config.get("max_polling", 20))
    timeout = config.get("timeout", 25)
    polling_secs = config.get("polling_secs", 15)
    storage = config.get("storage", RTPs)

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

def schedule_http_server(loop):
    http_server = config.get("http_server")  
    
    if not http_server:
        return

    upload_queue = Queue(loop=loop)
    
    schedule_task(
        start_http_server(
            host=http_server,
            port=config.get("http_port", 8080),
            upload_dir=config.get("upload_dir", "./"),
            upload_queue=upload_queue
        ),
        name="http_server", loop=loop
    )

    schedule_task(
        process_upload_queue(upload_queue, storage=PCAPs),
        name="process_upload_queue", loop=loop
    )

def start_discovery(loop, discovery_done_callback=None):
    schedule_task(
        discovery(loop=loop, callback=discovery_done_callback),
        name="discovery",
        loop=loop,
    )

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

############################## BEGIN FUNCTIONS ################################

if __name__ == "__main__":
    def main():
        loop = startup_async_loop()
        start_discovery(loop)
        start = time.time()
        discovery_done = False
        query_done = False

        while True:
            if loop:
                tick_async_loop(loop)
            time.sleep(0.05)
            end = time.time()
            c = end - start
            if c > 20 and not discovery_done:
                discovery_done = True
                request_shutdown(loop)
                loop = None
            elif c > 25 and not query_done:
                print("============= STARTING QUEUERIES =============")
                loop = startup_async_loop()
                BGWs["001"].queue.put("capture start")
                schedule_queries(loop)
                query_done = True
            elif c > 120:
                request_shutdown(loop)
                loop = None
                break
    main()
