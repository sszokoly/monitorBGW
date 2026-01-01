#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS #################################

import os
os.environ["ESCDELAY"] = "25"

import curses, curses.ascii, curses.panel, curses.textpad

############################## END IMPORTS ###################################

from utils import logger
from filter_parser import filter_parser, filter_validator
import time

############################## BEGIN VARIABLES ###############################

############################## END VARIABLES #################################

FILTER_HELP = """
Filter Usage:
    -i <IP>    <IP> address of Branch Gateway(s) separated by | or ,
    -n         no filter, clear current filter

Filter examples:
  To discover only gateway 10.10.10.1 and 10.10.10.2
    -i 10.10.10.1|10.10.10.2  OR  -i 10.10.10.1,10.10.10.2
"""

FILTER = "-i 192.168.11.1|10.10.48.58|10.10.48.59|10.44.244.242"

############################## BEGIN CLASSES #################################

class FilterPanel:
    def __init__(
        self,
        stdscr,
        storage,
        current_filter="",
        validator=None,
        callback=None,
        yoffset=1,
        margin=1,
        name=None,
        color_border=0,
        color_text=0,
    ):
        self.stdscr = stdscr
        self.storage = list(storage)
        self.current_filter = current_filter
        self.validator = validator
        self.callback = callback

        self.yoffset = yoffset
        self.margin = margin
        self.name = name
        self.color_border = color_border
        self.color_text = color_text
        self.cur_filter_label = "Current Filter: "
        self.new_filter_label = "    New Filter: "
        self._init_attrs()

    def _init_attrs(self):
        maxy, maxx = self.stdscr.getmaxyx()
        nlines = maxy - self.yoffset - (2 * self.margin)
        ncols = maxx - (2 * self.margin)
        begin_y = self.yoffset + self.margin
        begin_x = self.margin
        self.win = curses.newwin(nlines, ncols, begin_y, begin_x)
        self.panel = curses.panel.new_panel(self.win)
        self.maxy, self.maxx = self.win.getmaxyx()
        self.err = ""

        # Current Filter Window
        cf_y = self.cf_y = min(len(self.storage) + 3, nlines - 5)
        cf_x = self.cf_x = len(self.cur_filter_label) + 1
        cf_width = self.cf_width = ncols - cf_x - 1
        cf_height = 2
        self.cfwin = self.win.derwin(cf_height, cf_width, cf_y, cf_x)

        # New Filter Textbox
        tb_y = self.tb_y = min(len(self.storage) + 5, nlines - 3)
        tb_x = len(self.new_filter_label) + 1
        tb_width = ncols - tb_x - 1
        tb_height = 2
        self.tbwin = self.win.derwin(tb_height, tb_width, tb_y, tb_x)
        self.textbox = curses.textpad.Textbox(self.tbwin, insert_mode=True)

    def draw(self):
        self.win.attron(self.color_border)
        self.win.box()
        self.win.attroff(self.color_border)

        self.draw_help()
        self.draw_error()
        self.draw_current_filter()
        self.draw_new_filter()

        self.win.noutrefresh()
        self.cfwin.noutrefresh()
        self.tbwin.noutrefresh()
        curses.doupdate()

    def draw_help(self):
        for r, line in enumerate(self.storage, 1):
            try:
                self.win.addstr(r, 1, line, self.color_text | curses.A_DIM)
            except curses.error:
                pass

        ypos = self.maxy - 2
        xpos = self.maxx // 2 - 4
        color = self.color_text | curses.A_REVERSE
        self.win.addstr(ypos, xpos, " ENTER ", color)

    def draw_error(self):
        try:
            err = f"{self.err[:self.cf_width]:{self.cf_width}}"
            self.win.addstr(self.cf_y - 1, self.cf_x , err, 2560)
        except curses.error:
            pass

    def draw_current_filter(self):
        try:
            text = f"{self.cur_filter_label[:self.cf_width]:<{self.cf_width}}"
            self.win.addstr(self.cf_y, 1, text, self.color_text)
            self.cfwin.addstr(0, 0, f"{self.current_filter}", 12288)
        except curses.error:
            pass

    def draw_new_filter(self):
        try:
            self.win.addstr(self.tb_y, 1, self.new_filter_label, self.color_text)
        except curses.error:
            pass

    def handle_char(self):
        """Handle keyboard input for the textbox"""
        try:
            curses.curs_set(1)
        except curses.error:
            pass

        while True:
            char = self.stdscr.getch()

            if char == curses.ERR:
                time.sleep(0.1)

            # ESC to cancel
            if char == 27:
                curses.curs_set(0)
                self.win.erase()
                self.win.noutrefresh()
                self.panel.hide()
                curses.panel.update_panels()
                curses.doupdate()
                return 1

            # Enter to submit
            elif char in (10, 13):
                saved_y, saved_x = self.tbwin.getyx()
                curses.curs_set(0)
                result = self.textbox.gather()
                
                # Remove newlines and ENTER
                result = result.replace("\n", "").replace("ENTER", "").strip()

                if self.validator:
                    err = self.validator(result)
                    
                    if err:
                        self.err = err
                        self.tbwin.move(saved_y, saved_x)
                        curses.curs_set(1)
                        self.draw()
                        continue

                if self.callback:
                    self.callback(result)


                curses.curs_set(0)
                self.win.erase()
                self.win.noutrefresh()
                self.panel.hide()
                curses.panel.update_panels()
                curses.doupdate()
                return

            if char in (curses.KEY_BACKSPACE, 127, 8):
                char = curses.ascii.BS

            elif char == curses.KEY_DC:
                char = curses.ascii.EOT

            try:
                self.textbox.do_command(char)
                self.draw()
            except:
                pass

############################## END CLASSES ###################################

def create_panel(stdscr):
    panel = FilterPanel(
        stdscr,
        storage = [x for x in FILTER_HELP.splitlines() if x],
        current_filter = FILTER,
        validator = filter_validator,
        callback = update_filter
    )
    curses.curs_set(1)
    panel.draw()
    return panel

def update_filter(filter_text):
    global FILTER
    args = vars(filter_parser.parse_args(filter_text.split()))

    if args.get("no_filter"):
        FILTER = ""
    
    elif filter_text:
        FILTER = filter_text

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
    
def main(stdscr):
    init_colors()

    stdscr.box()
    stdscr.refresh()
    stdscr.nodelay(1)
    stdscr.keypad(True)
    
    char = curses.ERR
    panel = None
    
    while True:
        char = stdscr.getch()
        if char == curses.ERR:
            time.sleep(0.1)
        
        elif char in (ord('q'),ord('Q')):
            break
            
        elif char in (ord('f'),ord('F')):
            panel = create_panel(stdscr)
            rv = panel.handle_char()
            if rv:
                panel = None
        
                stdscr.clear()
                stdscr.box()
                stdscr.addstr(0, 0, f"Filter updated to: {FILTER}")
                stdscr.refresh()
                curses.panel.update_panels()
                curses.doupdate()

############################## END FUNCTIONS #################################

if __name__ == "__main__":
    curses.wrapper(main)
