#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS ##################################

import os
os.environ["NCURSES_NO_UTF8_ACS"] = "1"
os.environ["ESCDELAY"] = "25"
os.nice(19)

import argparse
import asyncio
import base64
import _curses, curses, curses.ascii, curses.panel, curses.textpad
import json
import logging
import re
import sys
import termios
import time
import zlib

from abc import ABC, abstractmethod
from asyncio import Queue, Semaphore
from bisect import insort_left
from contextlib import contextmanager
from collections.abc import MutableMapping, ItemsView
from datetime import datetime
from functools import partial
from urllib.parse import unquote
from typing_extensions import Protocol
from typing import AbstractSet, Any, Callable, Coroutine, Dict, FrozenSet
from typing import Generator, Generic, Iterable, Iterator, ItemsView
from typing import List, Mapping, MutableMapping, Optional, Set, Sequence
from typing import Tuple, TypeVar, Union
from typing import TYPE_CHECKING

############################## END IMPORTS ###################################

from config import CONFIG
from storage import GWs, BGWs, RTPs, PCAPs
from aloop import *
from bgw import BGW
from rtpparser import *
from workspace import MyDisplay, Button, FilterPanel, ProgressBar, Confirmation, TextPanel, ObjectPanel, Workspace
from filter import *
from utils import *
from layout import LAYOUTS, Layout, RTP_LAYOUT, COLORS, iter_attrs

############################## BEGIN VARIABLES ###############################

LOG_FORMAT = "%(asctime)s - %(levelname)8s - %(message)s [%(funcName)s:%(lineno)s]"

############################## END VARIABLES ##################################


############################## BEGIN UI FUNCTIONS #############################
def hide_panel(ws):
    ws.active_panel.panel.hide()
    del ws.active_panel
    ws.panel.top()
    ws.active_panel = ws.panel
    ws.draw(dim=False)
    curses.panel.update_panels()
    curses.doupdate()
    ws.display.active_handle_char = ws.handle_char

    return 1

def make_filterpanel(ws, group):
    
    if not group or FILTER_MENUs.get(group) is None:
        return

    logger.info("Make filterpanel requested")
    
    storage = FILTER_MENUs[group].splitlines()
    current = FILTER_GROUPs[ws.filter_group]["current_filter"]

    def filter_callback(filter):
        update_filter(group, filter)

    panel = FilterPanel(
        ws.display,
        storage = storage,
        current_filter = current,
        validator = filter_validator,
        callback = filter_callback,
        name = f"FilterPanel({group})"
    )
    panel.draw()
    is_canceled = panel.handle_char()
    return is_canceled

def discovery_start(ws):
    logger.info("Discovery start requested")

    ws.bodywin.erase()
    ws.draw(dim=True)

    is_canceled = make_filterpanel(ws, "bgw")
    if is_canceled:
        ws.draw()
        return

    GWs.clear()
    BGWs.clear()

    ip_filter = FILTER_GROUPs["bgw"]["groups"]["ip_filter"]
    loop = startup_async_loop()
    progress_queue = Queue(loop=loop)
    
    panel = ProgressBar(
        ws.display,
        queue=progress_queue,
        workspace_chars = [ord("s"), ord("S")]
    )

    def progress_callback(progress_update: Tuple[int, int, int]) -> None:
        """
        Handle progress updates from discovery tasks.

        Args:
            progress_update: A tuple of (ok, err, total) counts.
        """
        nonlocal progress_queue, panel, ws

        progress_queue.put_nowait(progress_update)
        ws.menubar.draw()
        panel.draw()

    task = schedule_task(
        discovery(
            loop=loop,
            callback=progress_callback,
            ip_filter=ip_filter
        ),
        name="discovery",
        loop=loop,
    )

    def discovery_done_callback(fut: asyncio.Future, ws: Any) -> None:
        if fut.cancelled() or ws.display.loop_shutdown_requested:
            return
        curses.flushinp()
        curses.ungetch(ord("s"))

    task.add_done_callback(partial(discovery_done_callback, ws=ws))

    ws.draw()
    ws.panel.hide()
    ws.active_panel = panel
    ws.active_panel.draw()
    curses.panel.update_panels()
    curses.doupdate()

    ws.display.loop = loop
    ws.display.active_handle_char = panel.handle_char

    return panel

def discovery_stop(ws):
    logger.info("Discovery stop requested")
    
    loop = ws.display.loop

    if loop:
        ws.display.loop_shutdown_requested = True
        request_shutdown(loop)

    hide_panel(ws)

    return 1

def polling_start(ws):
    logger.info("Polling start requested")
    
    def process_item_callback():
        nonlocal ws
        aws = ws.display.active_workspace
        polling_workspace = any(x.name == "button_polling" for x in aws.buttons)

        if polling_workspace:
            if aws.panel != aws.active_panel:
                rtpdetails = aws.storage.select(aws.storage_cursor + aws.body_posy)
                aws.active_panel.draw(rtpdetails)
            else:
                aws.draw()
            curses.doupdate()
            aws.menubar.draw()

    loop = ws.display.loop

    if loop or not BGWs:
        return

    for bgw in BGWs.values():
        bgw.last_seen_dt = None

    loop = startup_async_loop()
    schedule_http_server(loop=loop)
    schedule_queries(loop=loop, bgws=BGWs, callback=process_item_callback)
    ws.display.loop = loop

    return 1

def polling_stop(ws):
    logger.info("Polling stop requested")
    loop = ws.display.loop
    if loop:
        ws.display.loop_shutdown_requested = True
        request_shutdown(loop)

    return 1

def capture_toggle(ws):
    if not ws.display.loop:
        return

    bgw = ws.storage.select(ws.storage_cursor + ws.body_posy)

    if "running" in bgw.capture_status:
        command = "capture stop"
        status = "stopping"
    elif "stopped" in bgw.capture_status:
        command = "capture start"
        status = "starting"
    else:
        return

    bgw.queue.put_nowait(command)
    bgw.packet_capture = status
    logger.info(f"PCAP {status} requested")

    if ws.active_panel == ws.panel:
        if not ws.display.active_workspace.panel.hidden():
            ws.display.active_workspace.draw_bodywin()

    return 1

def capture_upload(ws):
    if not ws.display.loop:
        return

    bgw = ws.storage.select(ws.storage_cursor + ws.body_posy)

    if bgw.pcap_upload == "requested":
        return

    http_server = CONFIG.get("http_server")
    http_port = CONFIG.get("http_port")
    upload_dir = CONFIG.get("upload_dir")
    dest = f"{http_server}:{http_port}/{upload_dir}"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{bgw.gw_number}.cap"

    command = f"copy capture-file https http://{dest}/{filename}"
    bgw.queue.put_nowait(command)
    bgw.pcap_upload = "requested"
    logger.info(f"PCAP upload '{command}' requested")

    if ws.active_panel == ws.panel:
        if not ws.display.active_workspace.panel.hidden():
            ws.display.active_workspace.draw_bodywin()

    return 1

def clear_storage(ws):

    if not ws.storage:
        return

    def clear_storage_callback(char: int) -> None:
        nonlocal ws
        if char in (ord("y"), ord("Y")):
            ws.storage.clear()
            if ws.storage.name == "BGWs":
                GWs.clear()
        hide_panel(ws)

    logger.info("Clear storage requested")
    panel = Confirmation(ws.display, callback=clear_storage_callback)

    ws.draw(dim=True)    
    ws.active_panel = panel
    panel.panel.show()
    panel.panel.top()
    panel.draw()
    curses.panel.update_panels()
    curses.doupdate()
    ws.display.active_handle_char = panel.handle_char

    return panel

def make_textpanel(ws, *attr_names):
    bgw = ws.storage.select(ws.storage_cursor + ws.body_posy)

    if bgw is None:
        return

    logger.info("Make textpanel requested")

    storage = []
    for attr_name in attr_names:
        if not hasattr(bgw, attr_name):
            continue
        attr = str(getattr(bgw, attr_name)).strip()
        storage.extend([x.rstrip() for x in attr.splitlines()])

    if not storage:
        return

    panel = TextPanel(
        display = ws.display,
        storage = storage,
        name = f"TextPanel({attr})",
    )

    ws.draw(dim=True)    
    ws.active_panel = panel
    panel.panel.show()
    panel.panel.top()
    panel.draw()
    curses.panel.update_panels()
    curses.doupdate()
    ws.display.active_handle_char = panel.handle_char

    return panel

def show_system(ws):
    panel = make_textpanel(ws, "show_system")
    return panel if panel else None

def show_mg_list(ws):
    panel = make_textpanel(ws, "show_mg_list")
    return panel if panel else None

def show_port(ws):
    panel = make_textpanel(ws, "show_port")
    return panel if panel else None

def show_config(ws):
    panel = make_textpanel(ws, "show_running_config")
    return panel if panel else None

def show_status(ws):
    panel = make_textpanel(ws,
        "show_rtp_stat_summary",
        "show_voip_dsp",
        "show_utilization"
    )
    return panel if panel else None

def show_misc(ws):
    panel = make_textpanel(ws,
        "show_temp",
        "show_faults",
        "show_announcements_files"
    )
    return panel if panel else None

def show_rtp(ws):
    rtpdetails = ws.storage.select(ws.storage_cursor + ws.body_posy)

    if not rtpdetails:
        return

    logger.info("Show RTP objectpanel requested")

    rtp_attr_iter = partial(
        iter_attrs,
        spec=RTP_LAYOUT,
        colors=COLORS,
        xoffset=0,
        yoffset=0,
        default_y=0,
        header=False,
    )

    panel = ObjectPanel(
        display=ws.display,
        obj=rtpdetails,
        attr_iterator=rtp_attr_iter,
        name = "ObjectPanel(RTP)"
    )

    ws.draw(dim=True)    
    ws.active_panel = panel
    panel.panel.show()
    panel.panel.top()
    panel.draw()
    curses.panel.update_panels()
    curses.doupdate()
    ws.display.active_handle_char = panel.handle_char

    return panel

def show_pcap(ws):
    capture = ws.storage.select(ws.storage_cursor + ws.body_posy)

    if not capture:
        return

    logger.info("Show PCAP textpanel requested")

    panel = TextPanel(
        display = ws.display,
        storage = capture.rtpinfos.splitlines(),
        name = "TextPanel(PCAP)",
    )

    ws.draw(dim=True)    
    ws.active_panel = panel
    panel.panel.show()
    panel.panel.top()
    panel.draw()
    curses.panel.update_panels()
    curses.doupdate()
    ws.display.active_handle_char = panel.handle_char

    return panel

############################## END UI FUNCTIONS ###############################
############################## BEGIN MAIN #####################################

def main(stdscr, miny: int=24, minx: int=80):
        curses.start_color()
        curses.use_default_colors()

        def must_resize(stdscr, miny, minx):
            maxy, maxx = stdscr.getmaxyx()

            if maxy >= miny and maxx >= minx:
                return False

            lines = (
                f"Resize screen to  {miny}x{minx}",
                f"Current size      {maxy}x{maxx}",
                "Press 'q' to exit",
            )

            yoffset = max(0, maxy // 2 - 2)
            try:
                for i, line in enumerate(lines):
                    xoffset = max(0, (maxx - len(line)) // 2)
                    stdscr.addstr(yoffset + 2*i, xoffset, line)
            except curses.error:
                pass

            stdscr.box()
            stdscr.refresh()
            return True

        while must_resize(stdscr, miny, minx):
            char = stdscr.getch()
            if char == curses.ERR:
                time.sleep(0.1)
            elif char == curses.KEY_RESIZE:
                stdscr.erase()
            elif chr(char) in ("q", "Q"):
                return

        stdscr.erase()
        stdscr.refresh()
        stdscr.resize(miny, minx)

        mydisplay = MyDisplay(stdscr, miny=miny, minx=minx)

        button_discovery = Button(
            char_int = ord("s"),
            func_on = discovery_start,
            label_on = "Stop  Disc",
            label_off = "Start Disc",
            func_off = discovery_stop,
            status_label = "Discovery",
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_polling = Button(
            char_int = ord("s"),
            func_on = polling_start,
            label_on = "Stop Poll",
            label_off = "Start Poll",
            func_off = polling_stop,
            status_label = " Polling ",
            status_color_on = 66304,
            status_color_off = 68096,
            name = "button_polling"
        )

        button_clear_storage = Button(
            char_int = ord("c"),
            func_on = clear_storage,
            label_on = "Clear RTP",
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_system = Button(
            char_int = ord("\n"),
            func_on = show_system,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_misc = Button(
            char_int = ord("\n"),
            func_on = show_misc,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_mg_list = Button(
            char_int = ord("\n"),
            func_on = show_mg_list,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_port = Button(
            char_int = ord("\n"),
            func_on = show_port,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_config = Button(
            char_int = ord("\n"),
            func_on = show_config,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_pcap = Button(
            char_int = ord("\n"),
            func_on = show_pcap,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_status = Button(
            char_int = ord("\n"),
            func_on = show_status,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_show_rtp = Button(
            char_int = ord("\n"),
            func_on = show_rtp,
            label_on = "Hide Panel",
            label_off = "Show More",
            func_off = hide_panel,
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_capture = Button(
            char_int = ord("t"),
            func_on = capture_toggle,
            label_on = "Toggle PCAP",
            status_color_on = 66304,
            status_color_off = 68096
        )

        button_upload = Button(
            char_int = ord("u"),
            func_on = capture_upload,
            label_on = "Upload PCAP",
            status_color_on = 66304,
            status_color_off = 68096
        )
        
        workspaces = [
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["SYSTEM"]),
                buttons=[
                    button_discovery,
                    button_show_system
                ],
                storage=BGWs,
                name="SYSTEM",
                filter_group="bgw"
            ),
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["MISC"]),
                buttons=[
                    button_discovery,
                    button_show_misc
                ],
                storage=BGWs,
                name="MISC",
                filter_group="bgw"
            ),
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["MODULE"]),
                buttons=[
                    button_discovery,
                    button_show_mg_list
                ],
                storage=BGWs,
                name="MODULE",
                filter_group="bgw"
            ),
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["PORT"]),
                buttons=[
                    button_discovery,
                    button_show_port
                ],
                storage=BGWs,
                name="PORT",
                filter_group="bgw"
            ),
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["CONFIG"]),
                buttons=[
                    button_discovery,
                    button_show_config
                ],
                storage=BGWs,
                name="CONFIG",
                filter_group="bgw"
            ),
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["STATUS"]),
                buttons=[
                    button_polling,
                    button_show_status,
                    button_capture,
                    button_upload
                ],
                storage=BGWs,
                name="STATUS",
                filter_group="bgw"
            ),
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["RTPSTATS"]),
                buttons=[
                    button_polling,
                    button_show_rtp,
                    button_clear_storage
                ],
                storage=RTPs,
                name="RTPSTATS",
            ),
            Workspace(
                mydisplay,
                layout=Layout(LAYOUTS["PCAP"]),
                buttons=[
                    button_show_pcap
                ],
                storage=PCAPs,
                name="PCAP",
                filter_group=None
            )
        ]

        mydisplay.workspaces = workspaces
        mydisplay.run()

############################## END MAIN ######################################

@contextmanager
def terminal_context(term_type="xterm-256color"):
    """
    Context manager to temporarily change terminal type.
    
    Args:
        term_type: The terminal type to change to
    """
    old_term = change_terminal(term_type)
    try:
        yield
    finally:
        if term_type != old_term:
            os.environ["TERM"] = old_term
            logger.info(f"Changed terminal to '{old_term}'")

@contextmanager
def application_context(CONFIG):
    """
    Context manager to handle application startup and shutdown.
    
    Sets up logging, configures terminal, and ensures proper cleanup.
    """   
    # Set up logging
    logging.basicConfig(
        format=LOG_FORMAT,
        filename=CONFIG["logfile"],
        level=CONFIG["loglevel"].upper()
    )
    
    # Save terminal state for restoration
    fd = sys.stdin.fileno()
    orig_term = termios.tcgetattr(fd)

    try:
        yield
    finally:
        print("Shutting down")
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, orig_term)
            curses.endwin()
        except:
            pass

if __name__ == "__main__":

    with application_context(CONFIG):
        with terminal_context("xterm-256color"):
            curses.wrapper(main)