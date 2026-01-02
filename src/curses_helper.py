#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS #################################

import _curses, curses
import os
from contextlib import contextmanager
from typing import List

############################## END IMPORTS ####################################

from config import logger

############################## BEGIN FUNCTIONS ################################

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

############################## END FUNCTIONS ##################################

def init_colors():    
    curses.start_color()
    curses.use_default_colors()

    max_pairs = min(curses.COLORS, curses.COLOR_PAIRS - 1)
    for i in range(max_pairs):
        curses.init_pair(i + 1, i, -1)

    special_pair = min(1, curses.COLOR_PAIRS - 1)
    fg = 21 if curses.COLORS > 21 else curses.COLOR_CYAN
    bg = 246 if curses.COLORS > 246 else -1
    curses.init_pair(special_pair, fg, bg)

def show_curses_colors(stdscr):
    init_colors()
    
    maxy, _ = stdscr.getmaxyx()
    attrs = (curses.A_NORMAL, curses.A_DIM, curses.A_BOLD, curses.A_STANDOUT)
    c = 0

    while c < len(attrs):
        for columns, block in enumerate(range(0, curses.COLORS, maxy)):
            for ypos in range(0, maxy):

                xpos = columns * 13
                color_pair = block + ypos
                color = curses.color_pair(color_pair)|attrs[c]
                text = f"{color_pair}({str(color)})"

                try:
                    stdscr.addstr(ypos, xpos, text, color)
                except _curses.error:
                    pass

        stdscr.refresh()
        stdscr.getch()
        stdscr.clear()
        stdscr.refresh()
        c += 1

if __name__ == "__main__":
    with terminal_context("xterm-256color"):
        curses.wrapper(show_curses_colors)
