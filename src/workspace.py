#!/usr/bin/env python
# -*- encoding: utf-8 -*-

############################## BEGIN IMPORTS #################################

import _curses, curses, curses.ascii, curses.panel, curses.textpad
import resource
import sys
import time
from abc import ABC, abstractmethod
from asyncio import Queue
from datetime import datetime
from functools import partial
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence
from typing import Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio

############################## END IMPORTS ####################################

from storage import MemoryStorage, BGWs, RTPs
from bgw import BGW
from aloop import tick_async_loop, finalize_loop_if_idle, Capture
from rtpparser import parse_rtpstat
import logging
logger = logging.getLogger(__name__)

############################## BEGIN WORKSPACE ################################

WorkspaceT = Any
ActionFunc = Callable[..., Any]
AttrCell = Tuple[int, int, str, int]
AttrIterator = Callable[[Any], Iterable[AttrCell]]
DoneCallback = Callable[[], None]
ProgressTuple = Tuple[int, int, int]
ToggleFunc = Callable[[Optional[WorkspaceT]], Any]

class Display(ABC):
    """Base class for a curses-driven UI.

    This class owns the main curses loop. It supports:
      - non-blocking keyboard input (`nodelay(True)`)
      - screen resize handling
      - optional integration with an asyncio loop via `tick_async_loop()`

    Subclasses implement:
      - `make_display()` to draw/rebuild the UI (also a good place to recompute
        layout, create windows/panels, etc.)
      - `handle_char()` to react to keystrokes

    Attributes:
        stdscr: The root curses screen from `curses.wrapper`.
        miny/minx: Minimum terminal size required for the UI.
        workspaces: List of workspace objects (may be empty).
        tab: Optional tab UI object (implementation-specific).
        loop: Optional asyncio event loop used by the application.
        loop_shutdown_requested: Flag set by caller when a shutdown is requested.
        done: When True the main loop exits.
        active_ws_idx: Index of current workspace in `workspaces`.
        special_pair: A curses color-pair number reserved for "special" UI text.
    """

    def __init__(
        self,
        stdscr: "_curses._CursesWindow",
        miny: int = 24,
        minx: int = 80,
        workspaces: Optional[List[Any]] = None,
        tab: Optional[Any] = None,
    ) -> None:
        self.stdscr = stdscr
        self.miny = miny
        self.minx = minx
        self._workspaces = [] if workspaces is None else workspaces
        self._tab = tab

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Initialize runtime state. Safe to call once at startup."""
        self.done = False  # type: bool
        self.active_ws_idx = 0  # type: int
        self.loop = None  # type: Optional["asyncio.AbstractEventLoop"]
        self.loop_shutdown_requested = False

        # Cache current size (subclasses may use it).
        self.maxy, self.maxx = self.stdscr.getmaxyx()
        
        self.init_colors()

    def init_colors(self) -> None:
        """Initialize curses color pairs.

        Notes:
            - Creates a grayscale-like mapping of (pair=i+1 -> fg=i, bg=-1)
              for as many colors as the terminal supports.
            - Also reserves `self.special_pair` for UI messages/highlights.
        """
        curses.start_color()
        curses.use_default_colors()

        max_pairs = min(curses.COLORS, curses.COLOR_PAIRS - 1)
        for i in range(max_pairs):
            curses.init_pair(i + 1, i, -1)

        # Reserve a dedicated pair number that is not 0.
        self.special_pair = min(1, curses.COLOR_PAIRS - 1)

        fg = 21 if curses.COLORS > 21 else curses.COLOR_CYAN
        bg = 246 if curses.COLORS > 246 else -1
        curses.init_pair(self.special_pair, fg, bg)

    def set_exit(self) -> None:
        """Request clean exit from the curses main loop."""
        self.done = True

    def run(self) -> None:
        """Main curses loop.

        The loop is non-blocking:
          - When no key is pressed, we optionally tick the asyncio loop and
            sleep briefly to reduce CPU usage.
          - On resize, we re-check minimum size and call `make_display()`.
          - All other keys are forwarded to `handle_char()`.
        """
        self.stdscr.nodelay(True)
        self.stdscr.keypad(True)

        try:
            curses.curs_set(0)
        except curses.error:
            pass

        self.make_display()

        while not self.done:
            curses.panel.update_panels()
            ch = self.stdscr.getch()

            if ch == curses.ERR:
                # No input. Tick asyncio if present.
                if self.loop is not None:
                    tick_async_loop(self.loop)

                    if self.loop_shutdown_requested:
                        if finalize_loop_if_idle(self.loop):
                            self.loop = None
                            self.loop_shutdown_requested = False

                time.sleep(0.05)
                continue

            if ch == curses.KEY_RESIZE:
                self.maxy, self.maxx = self.stdscr.getmaxyx()

                if self.maxy >= self.miny and self.maxx >= self.minx:
                    self.make_display()
                    curses.panel.update_panels()
                    curses.doupdate()
                    if self.active_workspace is not None:
                        self.active_workspace.menubar.draw()
                else:
                    self.stdscr.erase()
                    self.stdscr.refresh()
                    break
                continue

            # Forward all other keys to subclass handler.
            try:
                ch_repr = repr(chr(ch)) if 0 <= ch <= 0x10FFFF else repr(ch)
            except Exception:
                ch_repr = repr(ch)
            
            logger.debug("Detected char %r (%s)", ch, ch_repr)
            self.handle_char(ch)

    @property
    def active_workspace(self) -> Optional[Any]:
        """Return the currently active workspace, or None."""
        if not self.workspaces:
            return None
        if self.active_ws_idx >= len(self.workspaces):
            self.active_ws_idx = 0
        return self.workspaces[self.active_ws_idx]

    @property
    def workspaces(self):
        return self._workspaces

    @workspaces.setter
    def workspaces(self, value):
        self._workspaces = value
        # Auto-create tab when workspaces are set
        if value and not self._tab:
            self._tab = Tab(self, tab_names=[ws.name for ws in value])

    @property
    def tab(self):
        return self._tab

    @tab.setter
    def tab(self, value):
        self._tab = value

    @abstractmethod
    def make_display(self) -> None:
        """(Re)build and draw the UI."""
        raise NotImplementedError

    @abstractmethod
    def handle_char(self, char: int) -> None:
        """Handle a keystroke from the main loop."""
        raise NotImplementedError

    def update_title(self, title: str = None) -> None:
        """Updates terminal window title using curses."""
        if title is None:
            return
        try:
            curses.putp(curses.tigetstr("tsl"))  # Enter title mode
            sys.stderr.write(title)
            curses.putp(curses.tigetstr("fsl"))  # Exit title mode
            sys.stderr.flush()
        except:
            # Fallback to escape sequence
            sys.stderr.write(f"\x1b]2;{title}\x07")
            sys.stderr.flush()

class MyDisplay(Display):
    """Concrete Display implementation.

    Responsibilities:
      - Delegates most keystrokes to the active workspace's `handle_char`.
      - Draws the tab bar (if present) and the active workspace.
      - Handles global keys (e.g., quit).

    Notes:
      - `active_handle_char` is a callable that routes input to the currently
        focused component (typically the active workspace, but may be swapped
        temporarily to a panel/textbox handler).
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super(MyDisplay, self).__init__(*args, **kwargs)
        # Default handler: safe no-op until make_display sets a real one.
        self.active_handle_char = self._noop_handle_char

    def _noop_handle_char(self, char: int) -> None:
        """Fallback handler used before UI components are ready."""
        return

    def make_display(self) -> None:
        """(Re)build and draw the UI.

        Sets the active input handler to the active workspace handler,
        clears the screen, draws the tab bar (if any), then draws the active
        workspace.
        """
        ws = self.active_workspace
        if ws is None:
            return

        self.active_handle_char = ws.handle_char
        self.maxy, self.maxx = self.stdscr.getmaxyx()
        self.stdscr.erase()

        if self.tab is not None:
            self.tab.draw()

        ws.draw()

    def handle_char(self, char: int) -> None:
        """Handle a keystroke from the main loop.

        Global shortcuts:
          - 'q' or 'Q': exit the application

        All other keys are forwarded to `active_handle_char`.
        """
        # Quit on 'q' or 'Q'
        if char in (ord("q"), ord("Q")):
            self.set_exit()
            return

        # Forward to currently active handler (workspace/panel/etc).
        try:
            self.active_handle_char(char)
        except Exception as e:
            logger.exception(f"{e} in active_handle_char")
            pass

    @property
    def title(self) -> str:
        """Return current memory usage in MB."""
        mem = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024)
        bgws = len(BGWs)
        rtps = len(RTPs)
        return f"MemUsage: {mem}MB  |  BGWs: {bgws}  |  RTPs: {rtps}"

class Tab(object):
    """Simple top tab bar widget for curses.

    Draws a row (or two lines) of tabs using box-drawing characters.
    The active tab is drawn normally; inactive tabs are dimmed.

    The widget owns a curses subwindow and draws within it.
    """

    def __init__(
        self,
        display: Any,
        tab_names: Sequence[str],
        nlines: int = 2,
        yoffset: int = 0,
        xoffset: int = 0,
        color_text: int = 0,
        color_border: int = 65024,
    ) -> None:
        """
        Args:
            display: Object that provides `stdscr`.
            tab_names: Names/labels for each tab.
            nlines: Height of the tab bar in rows.
            yoffset: Y position relative to stdscr.
            xoffset: X position relative to stdscr.
            color_text: curses attribute for tab text.
            color_border: curses attribute for tab border.
        """
        self.display = display
        self.tab_names = list(tab_names)
        self.nlines = int(nlines)
        self.yoffset = int(yoffset)
        self.xoffset = int(xoffset)
        self.color_text = int(color_text)
        self.color_border = int(color_border)

        self.stdscr = None          # type: Any
        self.win = None             # type: Optional[Any]
        self.maxy = 0
        self.maxx = 0
        self.active_tab_idx = 0
        self.tab_width = 0

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Compute geometry and create the subwindow."""
        self.stdscr = self.display.stdscr
        self.active_tab_idx = 0

        maxy, maxx = self.stdscr.getmaxyx()
        self.maxy = min(self.nlines, maxy)
        self.maxx = maxx

        width = self.maxx - self.xoffset
        if self.maxy <= 0 or width <= 0:
            self.win = None
            self.tab_width = 0
            return

        try:
            self.win = self.stdscr.subwin(
                self.maxy,
                width,
                self.yoffset,
                self.xoffset,
            )
        except curses.error:
            self.win = None
            self.tab_width = 0
            return

        if not self.tab_names:
            self.tab_width = 0
            return

        computed = (
            width - (len(self.tab_names) * 2)
        ) // len(self.tab_names)
        self.tab_width = max(3, computed)

    def draw(self) -> None:
        """Draw the tab bar."""
        if (
            self.win is None
            or not self.tab_names
            or self.tab_width <= 0
        ):
            return

        xpos = 0
        for idx, name in enumerate(self.tab_names):
            active = idx == self.active_tab_idx
            self._draw_tab(name, xpos, active)
            xpos += self.tab_width + 2

        try:
            self.win.noutrefresh()
        except curses.error:
            pass

    def _draw_tab(
        self,
        name: str,
        xpos: int,
        active: bool,
    ) -> None:
        """Draw a single tab."""
        if self.win is None:
            return

        top = u"┌" + (u"─" * self.tab_width) + u"┐"
        mid = u"│" + (u" " * self.tab_width) + u"│"

        if active:
            border_attr = self.color_border
            text_attr = self.color_text
        else:
            border_attr = self.color_border | curses.A_DIM
            text_attr = self.color_text | curses.A_DIM

        try:
            self.win.addstr(0, xpos, top, border_attr)
            for line in range(1, self.maxy):
                self.win.addstr(line, xpos, mid, border_attr)
        except curses.error:
            pass

        if self.maxy > 1:
            try:
                label = "{:^{w}}".format(
                    name[: self.tab_width],
                    w=self.tab_width,
                )
                self.win.addstr(
                    1,
                    xpos + 1,
                    label,
                    text_attr,
                )
            except curses.error:
                pass

    def next_tab(self) -> None:
        """Activate the next tab."""
        if not self.tab_names:
            return

        self.active_tab_idx = (
            self.active_tab_idx + 1
        ) % len(self.tab_names)
        self.draw()

    def prev_tab(self) -> None:
        """Activate the previous tab."""
        if not self.tab_names:
            return

        self.active_tab_idx = (
            self.active_tab_idx - 1
        ) % len(self.tab_names)
        self.draw()

class Button(object):
    """
    UI button bound to a keyboard key (char_int) with optional on/off actions.

    The button has two states:
      - state == 0: "off"
      - state == 1: "on"

    When toggled:
      - If state is off, func_on(workspace) is called (if provided). If it
        returns a truthy value and func_off exists, state becomes 1; otherwise 0.
      - If state is on, func_off(workspace) is called (if provided). If it
        returns a truthy value, state becomes 0; otherwise stays 1.

    Notes:
      - If func_off is not provided, this button cannot deactivate (state stays 1)
        once activated.
      - done_callback_on/off (if provided) are called after a successful
        activate/deactivate transition.
    """

    def __init__(
        self,
        char_int: int,
        label_on: Optional[str] = None,
        func_on: Optional[ToggleFunc] = None,
        char_uni: Optional[str] = None,
        label_off: Optional[str] = None,
        func_off: Optional[ToggleFunc] = None,
        done_callback_on: Optional[DoneCallback] = None,
        done_callback_off: Optional[DoneCallback] = None,
        status_label: str = "",
        status_color_on: int = 0,
        status_color_off: int = 0,
        name: str = "",
    ) -> None:
        self.char_int = char_int
        self.char_str = chr(char_int)
        self.char_uni = char_uni

        # Use explicit None checks so empty-string labels are allowed.
        self.label_on = label_on if label_on is not None else str(self)
        self.label_off = label_off if label_off is not None else self.label_on

        self.func_on = func_on
        self.func_off = func_off

        self.done_callback_on = done_callback_on
        self.done_callback_off = done_callback_off

        self.status_label = status_label
        self.status_color_on = status_color_on
        self.status_color_off = status_color_off

        self.name = name if name else str(self)

        self.state = 0  # 0=off, 1=on

    @property
    def char(self) -> str:
        """Human-friendly key label for display."""
        if self.char_uni:
            return self.char_uni
        if self.char_str == "\n":
            return "Enter"
        return self.char_str

    @property
    def label(self) -> str:
        """Current button label based on state."""
        return self.label_on if self.state else self.label_off

    @property
    def status_color(self) -> int:
        """Status color based on state."""
        return self.status_color_on if self.state else self.status_color_off

    def toggle(self, *args: Any, **kwargs: Any) -> None:
        """
        Toggle the button state by calling the on/off function(s).

        workspace is passed through to func_on/func_off when provided.
        """
        # Activating
        if not self.state:
            result = self.func_on(*args, **kwargs) if self.func_on else 1

            new_state = 1 if result and self.func_off else 0
            self.state = new_state
            logger.info("%s activation in state %s", self.name, self.state)

            if self.state and self.done_callback_on:
                self.done_callback_on()

            return

        # Deactivating
        if self.func_off:
            result = self.func_off(*args, **kwargs)
            self.state = 0 if result else 1
        else:
            self.state = 1  # this is for fire-and-forget buttons

        logger.info("%s deactivation in state %s", self.name, self.state)

        if not self.state and self.done_callback_off:
            self.done_callback_off()

    def status_attrs(self) -> Tuple[str, int]:
        """Return (status_label, status_color) for UI rendering."""
        return self.status_label, self.status_color

    def __str__(self) -> str:
        return "Button({})".format(repr(chr(self.char_int)))

    def __repr__(self) -> str:
        return "Button(char_int={}, label_on={!r})".format(
            self.char_int, self.label_on
        )

class Menubar(object):
    """
    Single-line menubar rendered at the bottom of the screen.

    Layout:
      [status labels ... │]     <spacing>     [buttons: key=label ...]

    - Status labels come from Button.status_label/status_color.
    - Button labels come from Button.char and Button.label.
    """

    def __init__(
        self,
        display: Any,
        xoffset: int = 2,
        bar_color: int = 0,
        buttons: Optional[Sequence[Any]] = None,
        button_width: int = 10,
        button_gap: int = 3,
        max_status_width: int = 15,
        status_button_spacing: int = 5,
    ) -> None:
        self.display = display
        self.xoffset = xoffset
        self.bar_color = bar_color
        self.buttons = list(buttons) if buttons else []  # type: List[Any]
        self.button_width = button_width
        self.button_gap = button_gap
        self.max_status_width = max_status_width
        self.status_button_spacing = status_button_spacing

        self._init_attrs()

    def _init_attrs(self) -> None:
        """
        Initialize or refresh window geometry.
        """
        self.stdscr = self.display.stdscr
        maxy, maxx = self.stdscr.getmaxyx()

        height = 1
        width = max(1, maxx)
        begin_y = max(0, maxy - 1)
        begin_x = 0

        self.win = curses.newwin(height, width, begin_y, begin_x)
        self.maxy, self.maxx = self.win.getmaxyx()
        self.color = self.bar_color | curses.A_REVERSE

    def draw(self) -> None:
        """
        Redraw the entire menubar line.
        """
        try:
            sy, sx = self.stdscr.getmaxyx()
            win_y, _ = self.win.getbegyx()
            if sx != self.maxx or (sy - 1) != win_y:
                self._init_attrs()
        except Exception:
            pass

        try:
            self.win.addstr(0, 0, " " * self.maxx, self.color)
        except _curses.error:
            pass

        status_end = self._draw_status_labels()
        self._draw_button_labels(status_end)

        try:
            self.win.refresh()
        except _curses.error:
            pass

    def _truncate_status_labels(
        self,
        status_buttons: Sequence[Any],
    ) -> List[str]:
        """
        Truncate status labels so they fit within max_status_width.
        """
        if not status_buttons:
            return []

        num_separators = len(status_buttons)
        available = self.max_status_width - num_separators
        if available <= 0:
            return [""] * len(status_buttons)

        labels = [b.status_attrs()[0] for b in status_buttons]
        total = sum(len(label) for label in labels)

        if total <= available:
            return labels

        width_per = available // len(labels)
        remainder = available % len(labels)

        truncated = []
        for idx, label in enumerate(labels):
            extra = 1 if idx < remainder else 0
            target = width_per + extra
            truncated.append(label[:max(0, target)])

        return truncated

    def _draw_status_labels(self) -> int:
        """
        Draw status labels on the left side.

        Returns:
            int: x position immediately after the status area.
        """
        status_buttons = [
            b for b in self.buttons
            if getattr(b, "status_label", "")
        ]

        if not status_buttons:
            return 0

        labels = self._truncate_status_labels(status_buttons)
        x = 0

        for button, label in zip(status_buttons, labels):
            if not label or x >= self.maxx:
                break

            try:
                _, status_color = button.status_attrs()
            except Exception:
                status_color = 0

            remaining = self.maxx - x
            chunk = label[:remaining]

            try:
                self.win.addstr(0, x, chunk, status_color)
            except _curses.error:
                pass

            x += len(chunk)

            if x < self.maxx:
                try:
                    self.win.addstr(0, x, u"│", self.color)
                except _curses.error:
                    pass
                x += 1

        return x

    def _draw_button_labels(self, status_end_x: int) -> None:
        """
        Draw button labels to the right of the status area.
        """
        x = max(
            self.xoffset,
            status_end_x + self.status_button_spacing,
        )

        for idx, button in enumerate(self.buttons):
            if x >= self.maxx:
                break

            try:
                key = button.char
                label = button.label
            except Exception:
                continue

            text = "{}={:<{w}}".format(
                key,
                label,
                w=self.button_width,
            )

            remaining = self.maxx - x
            if remaining <= 0:
                break

            chunk = text[:remaining]

            try:
                self.win.addstr(0, x, chunk, self.color)
            except _curses.error:
                pass

            x += len(chunk)

            if idx < len(self.buttons) - 1:
                x += self.button_gap

class TextPanel(object):
    """
    Scrollable text viewer shown as a curses panel.

    This panel renders `storage` (a sequence of text lines) inside a boxed window
    and supports vertical/horizontal scrolling.

    Notes:
        - This class does *not* own the event loop. It assumes the caller routes
          keystrokes to `handle_char()`.
        - `workspace_chars` contains key codes that should be forwarded to the
          active workspace handler (e.g. Enter).
    """

    def __init__(
        self,
        display: Any,
        storage: Sequence[str],
        yoffset: int = 2,
        margin: int = 1,
        color_text: int = 0,
        color_border: int = 63488,
        name: Optional[str] = None,
        workspace_chars: Optional[Iterable[int]] = None,
    ) -> None:
        # Keep all original init attributes (do not remove / rename).
        self.display = display
        self.stdscr = display.stdscr
        self.storage = storage
        self.yoffset = yoffset
        self.margin = margin
        self.color_text = color_text
        self.color_border = color_border
        self.name = name
        self.workspace_chars = (
            list(workspace_chars) if workspace_chars else [10]
        )

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Initialize geometry, window and panel objects."""
        self.posy = 0
        self.posx = 0
        self.max_width = 0

        scr_h, scr_w = self.stdscr.getmaxyx()
        usable_h = scr_h - self.yoffset - 1
        usable_w = scr_w

        # Max window size inside margins (and never below 2 for borders)
        max_h = max(2, usable_h - (2 * self.margin))
        max_w = max(2, usable_w - (2 * self.margin))

        # Desired height: storage lines + 2 border lines
        desired_h = len(self.storage) + 2

        self.nlines = min(max_h, desired_h)
        self.ncols = max_w

        begin_x = self.margin

        # Center within usable area, then clamp
        center_off = (usable_h - self.nlines) // 2
        begin_y = self.yoffset + max(0, center_off)
        begin_y = min(begin_y, self.yoffset + max(0, usable_h - self.nlines))

        self.win = curses.newwin(self.nlines, self.ncols, begin_y, begin_x)
        self.panel = curses.panel.new_panel(self.win)
        self.panel.hide()

    def draw(self, storage: Optional[Sequence[str]] = None) -> None:
        """Render current viewport and show the panel."""
        page_h = max(0, self.nlines - 2)
        view_w = max(0, self.ncols - 2)

        if storage is not None:
            self.storage = storage
            self.posy = 0
            self.posx = 0

        data = self.storage
        it = data[self.posy : self.posy + page_h]
        self.max_width = max((len(x) for x in it), default=0)

        self.win.erase()

        for row, line in enumerate(it, start=1):
            try:
                slice_ = line[self.posx : self.posx + view_w]
                text = "{:<{w}}".format(slice_, w=view_w)
                self.win.addstr(row, 1, text, self.color_text)
            except curses.error:
                pass

        try:
            self.win.attron(self.color_border)
            self.win.box()
            self.win.attroff(self.color_border)
        except curses.error:
            pass

        self.panel.show()
        self.panel.top()
        curses.panel.update_panels()
        try:
            self.win.refresh()
        except curses.error:
            pass

    def erase(self) -> None:
        """Hide the panel and refresh the underlying screen."""
        self.panel.hide()
        curses.panel.update_panels()
        try:
            self.stdscr.refresh()
        except curses.error:
            pass

    def handle_char(self, char: int) -> None:
        """
        Handle navigation keys and forward selected keys to active workspace.

        Args:
            char: The key code from `getch()`.
        """
        page_y = self.nlines - 2
        view_x = self.ncols - 2

        max_y = max(0, len(self.storage) - page_y)
        max_x = max(0, self.max_width - view_x)

        # Forward selected keys to the workspace (e.g. Enter).
        if char in self.workspace_chars:
            ws = self.display.active_workspace
            if ws is not None:
                ws.handle_char(char)
            return

        if char == curses.KEY_DOWN:
            if self.posy < max_y:
                self.posy += 1

        elif char == curses.KEY_UP:
            if self.posy > 0:
                self.posy -= 1

        elif char == curses.KEY_HOME:
            self.posy = 0
            self.posx = 0

        elif char == curses.KEY_END:
            self.posy = max_y
            self.posx = max_x

        elif char == curses.KEY_NPAGE:
            self.posy = min(self.posy + page_y, max_y)

        elif char == curses.KEY_PPAGE:
            self.posy = max(self.posy - page_y, 0)

        elif char == curses.KEY_RIGHT:
            if self.posx < max_x:
                self.posx += 1

        elif char == curses.KEY_LEFT:
            if self.posx > 0:
                self.posx -= 1

        self.draw()

class ObjectPanel(object):
    """
    A bordered panel that renders an object's attributes using an iterator.

    The iterator (`attr_iterator`) is responsible for converting `obj` into an
    iterable of cells: (ypos, xpos, text, color_attr).

    Keys listed in `workspace_chars` are forwarded to the active workspace
    handler (so you can keep ENTER etc. working consistently).
    """

    def __init__(
        self,
        display: Any,
        obj: Any,
        attr_iterator: AttrIterator,
        callback: Optional[Callable[[int], None]] = None,
        yoffset: int = 2,
        margin: int = 1,
        color_border: int = 63488,
        name: Optional[str] = None,
        workspace_chars: Optional[Sequence[int]] = None,
    ) -> None:
        self.display = display
        self.obj = obj
        self.attr_iterator = attr_iterator
        self.callback = callback
        self.yoffset = yoffset
        self.margin = margin
        self.color_border = color_border
        self.name = name
        self.workspace_chars = (
            list(workspace_chars) if workspace_chars is not None else [10]
        )

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Create the underlying curses window and panel."""
        self.stdscr = self.display.stdscr
        scr_h, scr_w = self.stdscr.getmaxyx()

        usable_h = max(2, scr_h - self.yoffset - 1)
        usable_w = max(2, scr_w - (2 * self.margin))

        self.nlines = usable_h
        self.ncols = usable_w

        begin_y = max(0, self.yoffset)
        begin_x = max(0, self.margin)

        # Clamp start so window fits.
        begin_y = min(begin_y, max(0, scr_h - self.nlines))
        begin_x = min(begin_x, max(0, scr_w - self.ncols))

        self.win = curses.newwin(self.nlines, self.ncols, begin_y, begin_x)
        self.panel = curses.panel.new_panel(self.win)
        self.panel.hide()

    def draw(self, obj: Optional[Any] = None) -> None:
        """
        Draw the panel contents.

        Args:
            obj: Optional override object to render; defaults to `self.obj`.
        """
        self.win.erase()

        try:
            self.win.attron(self.color_border)
            self.win.box()
            self.win.attroff(self.color_border)
        except curses.error:
            pass

        target = self.obj if obj is None else obj

        maxy, maxx = self.win.getmaxyx()
        for ypos, xpos, text, color in self.attr_iterator(target):
            # Basic bounds guard; still keep try/except for safety.
            if ypos < 0 or xpos < 0 or ypos >= maxy or xpos >= maxx:
                continue
            try:
                self.win.addstr(ypos, xpos, text[: max(0, maxx - xpos)], color)
            except curses.error:
                pass

        self.panel.show()
        self.panel.top()
        curses.panel.update_panels()
        curses.doupdate()

    def handle_char(self, char: int) -> None:
        """
        Handle a keypress.

        - Keys in `workspace_chars` are forwarded to the active workspace.
        - Otherwise `callback(char)` is called if provided.
        """
        if char in self.workspace_chars:
            ws = getattr(self.display, "active_workspace", None)
            if ws is not None:
                ws.handle_char(char)
            return

        if self.callback is not None:
            self.callback(char)

    def erase(self) -> None:
        """Hide and clear the panel."""
        try:
            self.win.erase()
            self.win.noutrefresh()
        except curses.error:
            pass

        self.panel.hide()
        curses.panel.update_panels()
        curses.doupdate()

class Confirmation(object):
    """
    Simple modal confirmation panel.

    Displays a small centered box with a message (e.g. "Do you confirm (Y/N)?")
    and forwards keystrokes to an optional callback.

    Typical usage:
        panel = Confirmation(display, callback=on_key)
        panel.draw()
        display.active_handle_char = panel.handle_char

    Notes:
        - This class does not interpret Y/N itself; it just forwards `char`
          to `callback(char)`.
        - Coordinates are clamped so the window always stays on-screen.
    """

    def __init__(
        self,
        display: Any,
        text: str = "Do you confirm (Y/N)?",
        callback: Optional[Callable[[int], None]] = None,
        yoffset: int = -1,
        margin: int = 1,
        color_border: int = 13312,
        color_text: int = 0,
    ) -> None:
        self.display = display
        self.text = text
        self.callback = callback
        self.yoffset = yoffset
        self.margin = margin
        self.color_border = color_border
        self.color_text = color_text

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Create the underlying curses window and panel."""
        self.stdscr = self.display.stdscr
        maxy, maxx = self.stdscr.getmaxyx()

        nlines = 3 + (2 * self.margin)
        ncols = len(self.text) + (2 * self.margin) + 2

        # Clamp to screen size so curses.newwin doesn't raise.
        nlines = max(2, min(nlines, maxy))
        ncols = max(2, min(ncols, maxx))

        begin_y = max(0, maxy // 2 + self.yoffset - (self.margin + 1))
        begin_x = max(0, maxx // 2 - (len(self.text) // 2) - (self.margin + 1))

        # Also clamp start so the window fits on-screen.
        begin_y = min(begin_y, max(0, maxy - nlines))
        begin_x = min(begin_x, max(0, maxx - ncols))

        self.win = curses.newwin(nlines, ncols, begin_y, begin_x)
        self.panel = curses.panel.new_panel(self.win)

        self.draw()

    def handle_char(self, char: int) -> None:
        """
        Forward a keystroke to the callback (if provided).

        Args:
            char: Key code returned by `getch()`.
        """
        if self.callback is not None:
            self.callback(char)

    def draw(self) -> None:
        """Render the confirmation box and update panels."""
        self.panel.top()
        self.panel.show()

        try:
            self.win.erase()
            self.win.attron(self.color_border)
            self.win.box()
            self.win.attroff(self.color_border)

            y = self.margin + 1
            x = self.margin + 1

            # Avoid writing outside window if terminal is tiny.
            maxy, maxx = self.win.getmaxyx()
            if 0 <= y < maxy and 0 <= x < maxx:
                self.win.addstr(y, x, self.text[: maxx - x - 1],
                                self.color_text)
        except curses.error:
            pass

        curses.panel.update_panels()
        curses.doupdate()

    def erase(self) -> None:
        """Hide the panel and refresh the underlying screen."""
        try:
            self.win.erase()
            self.win.noutrefresh()
        except curses.error:
            pass

        self.panel.hide()
        curses.panel.update_panels()
        curses.doupdate()

class ProgressBar(object):
    """
    A 1-line progress bar panel driven by a queue.

    The queue is expected to provide tuples: (ok, err, total). The bar displays
    progress as (ok + err) / total and overlays the "filled" portion in a
    different color.

    Typical usage:
        - Create the ProgressBar once (it creates/shows its panel).
        - Call draw() repeatedly from your main loop.
        - Optionally provide a callback that is called once when progress hits
          100% (fraction >= 1.0).
    """

    def __init__(
        self,
        display: Any,
        queue: Any,
        callback: Optional[Callable[[], None]] = None,
        text: str = "In Progress",
        yoffset: int = 0,
        color_forground: int = 122112,
        color_background: int = 126720,
        width: int = 33,
        workspace_chars: Optional[Sequence[int]] = None,
    ) -> None:
        self.display = display
        self.queue = queue
        self.callback = callback
        self.text = text
        self.yoffset = yoffset
        self.color_forground = color_forground
        self.color_background = color_background
        self.width = width
        self.workspace_chars = (
            list(workspace_chars) if workspace_chars is not None else [10]
        )

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Create the curses window and panel."""
        self.stdscr = self.display.stdscr
        self.fraction = 0.0
        self._done = False

        maxy, maxx = self.stdscr.getmaxyx()

        nlines = 1
        ncols = self.width if self.width else max(1, maxx - 4)
        ncols = max(1, min(ncols, maxx))  # clamp to screen width

        begin_y = maxy // 2 + self.yoffset
        begin_x = (maxx - ncols) // 2

        # Clamp to keep the window on-screen
        begin_y = max(0, min(begin_y, maxy - nlines))
        begin_x = max(0, min(begin_x, maxx - ncols))

        self.win = curses.newwin(nlines, ncols, begin_y, begin_x)
        self.panel = curses.panel.new_panel(self.win)
        self.panel.show()
        self.panel.top()

    def handle_char(self, char: int) -> None:
        """
        Forward specific keys back to the active workspace.

        This lets ENTER (etc.) behave consistently while the progress bar is up.
        """
        if char in self.workspace_chars:
            ws = getattr(self.display, "active_workspace", None)
            if ws is not None:
                ws.handle_char(char)

    def draw(self) -> None:
        """
        Render the current progress state.

        If the queue contains a progress tuple, it is consumed and used to
        update the bar; otherwise the bar is redrawn with the current fraction.
        """
        # Use the actual window width for formatting/drawing
        _, w = self.win.getmaxyx()

        # Pull latest progress update if available
        try:
            if not self.queue.empty():
                ok, err, total = self.queue.get_nowait()  # type: ignore[misc]
                try:
                    self.queue.task_done()  # type: ignore[attr-defined]
                except Exception:
                    pass

                done = ok + err
                if total and total > 0:
                    self.fraction = float(done) / float(total)
                else:
                    self.fraction = 0.0

                # Clamp
                if self.fraction < 0.0:
                    self.fraction = 0.0
                elif self.fraction > 1.0:
                    self.fraction = 1.0

                label = "{} {}/{}".format(self.text, done, total)
            else:
                label = self.text
        except Exception:
            # If the queue isn't the shape you expect, keep drawing safely.
            label = self.text

        filled_width = int(self.fraction * w)

        # Center label; keep at most w chars
        text = "{:^{width}}".format(label, width=w)[:w]

        self.win.erase()
        try:
            self.win.addstr(0, 0, text, self.color_background)
        except curses.error:
            pass
        try:
            self.win.addstr(0, 0, text[:filled_width], self.color_forground)
        except curses.error:
            pass

        curses.panel.update_panels()
        curses.doupdate()

        # Fire completion callback once
        if not self._done and self.fraction >= 1.0 and self.callback is not None:
            self._done = True
            self.callback()

    def erase(self) -> None:
        """Hide and clear the progress bar panel."""
        try:
            self.win.erase()
            self.win.noutrefresh()
        except curses.error:
            pass

        self.panel.hide()
        curses.panel.update_panels()
        curses.doupdate()

class FilterPanel(object):
    """
    A simple modal panel to show filter help, display the current filter,
    and let the user type a new filter (1–2 lines) via curses.textpad.Textbox.

    The panel reads keys directly from display.stdscr in a small internal
    loop (handle_char()). On ENTER it validates (optional) and calls the
    callback (optional). ESC cancels.
    It is blocking and should be run prior to running async coros. 
    """

    def __init__(
        self,
        display: Any,
        storage: Sequence[str],
        current_filter: str = "",
        validator: Optional[Callable[[str], Optional[str]]] = None,
        callback: Optional[Callable[[str], Any]] = None,
        yoffset: int = 1,
        margin: int = 1,
        name: Optional[str] = None,
        color_border: int = 0,
        color_text: int = 0,
        color_err: int = 2560,
        color_filter: int = 12288
    ) -> None:
        self.display = display
        self.storage = list(storage)
        self.current_filter = current_filter
        self.validator = validator
        self.callback = callback

        self.yoffset = yoffset
        self.margin = margin
        self.name = name
        self.color_border = color_border
        self.color_text = color_text
        self.color_err = color_err
        self.color_filter = color_filter

        self.cur_filter_label = "Current Filter: "
        self.new_filter_label = "    New Filter: "

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Create the panel windows and textbox."""
        self.stdscr = self.display.stdscr
        maxy, maxx = self.stdscr.getmaxyx()

        nlines = maxy - self.yoffset - (2 * self.margin)
        ncols = maxx - (2 * self.margin)
        begin_y = self.yoffset + self.margin
        begin_x = self.margin

        # Clamp to avoid invalid sizes (can happen on tiny terminals)
        nlines = max(3, nlines)
        ncols = max(10, ncols)

        self.win = curses.newwin(nlines, ncols, begin_y, begin_x)
        self.panel = curses.panel.new_panel(self.win)
        self.maxy, self.maxx = self.win.getmaxyx()
        self.err = ""

        # Current Filter Window
        cf_y = self.cf_y = min(len(self.storage) + 3, nlines - 5)
        cf_x = self.cf_x = len(self.cur_filter_label) + 1
        cf_width = self.cf_width = max(1, ncols - cf_x - 1)
        cf_height = 2
        self.cfwin = self.win.derwin(cf_height, cf_width, cf_y, cf_x)

        # New Filter Textbox (2 lines)
        tb_y = self.tb_y = min(len(self.storage) + 5, nlines - 3)
        tb_x = len(self.new_filter_label) + 1
        tb_width = max(1, ncols - tb_x - 1)
        tb_height = 2
        self.tbwin = self.win.derwin(tb_height, tb_width, tb_y, tb_x)
        self.textbox = curses.textpad.Textbox(self.tbwin, insert_mode=True)

    def draw(self) -> None:
        """Redraw the full panel."""
        try:
            self.win.attron(self.color_border)
            self.win.box()
            self.win.attroff(self.color_border)
        except curses.error:
            pass

        self.draw_help()
        self.draw_error()
        self.draw_current_filter()
        self.draw_new_filter()

        self.win.noutrefresh()
        self.cfwin.noutrefresh()
        self.tbwin.noutrefresh()
        curses.doupdate()

    def draw_help(self) -> None:
        """Draw the help text (storage) and the ENTER hint."""
        for r, line in enumerate(self.storage, 1):
            try:
                self.win.addstr(r, 1, line, self.color_text | curses.A_DIM)
            except curses.error:
                pass

        ypos = self.maxy - 2
        xpos = self.maxx // 2 - 4
        color = self.color_text | curses.A_REVERSE
        try:
            self.win.addstr(ypos, xpos, " ENTER ", color)
        except curses.error:
            pass

    def draw_error(self) -> None:
        """Draw the current validation error line (if any)."""
        try:
            err = "{:{w}}".format(self.err[: self.cf_width], w=self.cf_width)
            self.win.addstr(self.cf_y - 1, self.cf_x, err, self.color_err)
        except curses.error:
            pass

    def draw_current_filter(self) -> None:
        """Draw the 'Current Filter' label and the current filter value."""
        try:
            label = "{:<{w}}".format(self.cur_filter_label[: self.cf_width],
                                    w=self.cf_width)
            filter = "{}".format(self.current_filter)
            self.win.addstr(self.cf_y, 1, label, self.color_text)
            self.cfwin.addstr(0, 0, filter, self.color_filter)
        except curses.error:
            pass

    def draw_new_filter(self) -> None:
        """Draw the 'New Filter' label."""
        try:
            self.win.addstr(
                self.tb_y, 1, self.new_filter_label, self.color_text
            )
        except curses.error:
            pass

    def _close(self) -> None:
        """Hide and clear the panel."""
        try:
            curses.curs_set(0)
        except curses.error:
            pass

        try:
            self.win.erase()
            self.win.noutrefresh()
        except curses.error:
            pass

        self.panel.hide()
        curses.panel.update_panels()
        curses.doupdate()

    def handle_char(self) -> Optional[int]:
        """
        Run the modal input loop.

        Returns:
            Optional[int]:
              - 1 when cancelled (ESC)
              - None on submit (ENTER) or normal exit
        """
        try:
            curses.curs_set(1)
        except curses.error:
            pass

        self.draw()

        while True:
            char = self.stdscr.getch()

            if char == curses.ERR:
                time.sleep(0.1)
                continue

            # ESC to cancel
            if char == 27:
                self._close()
                return 1

            # Enter to submit
            if char in (10, 13):
                saved_y, saved_x = self.tbwin.getyx()

                try:
                    curses.curs_set(0)
                except curses.error:
                    pass

                result = self.textbox.gather()

                # Textbox uses newlines for multi-line input; join and strip.
                result = result.replace("\n", "").strip()

                if self.validator is not None:
                    err = self.validator(result)
                    if err:
                        self.err = err
                        self.tbwin.move(saved_y, saved_x)
                        try:
                            curses.curs_set(1)
                        except curses.error:
                            pass
                        self.draw()
                        continue

                if self.callback is not None:
                    self.callback(result)

                self._close()
                return None

            # Normal editing keys
            if char in (curses.KEY_BACKSPACE, 127, 8):
                char = curses.ascii.BS
            elif char == curses.KEY_DC:
                char = curses.ascii.EOT

            try:
                self.textbox.do_command(char)
                self.draw()
            except curses.error:
                # Ignore curses drawing/editing errors on edge conditions
                pass
            except Exception:
                # Keep your original behavior: don't let exceptions kill UI
                pass

class Workspace(object):
    """
    A single workspace (tab) containing:

    - A bordered frame window
    - A header window for column headers
    - A body window for storage rows
    - A curses panel attached to the body
    - A Menubar instance
    - Cursor and scrolling state

    Responsibilities:
    - Drawing itself
    - Handling navigation keys
    - Triggering buttons
    - Switching workspaces
    """

    def __init__(
        self,
        display: Any,
        layout: Any,
        buttons: Sequence[Any],
        storage: MemoryStorage,
        name: str,
        attr_iterator: Optional[
            Callable[..., Iterable[Any]]
        ] = None,
        yoffset: int = 2,
        menubar_height: int = 1,
        header_height: int = 3,
        filter_group: Optional[Any] = None,
        color_border: int = 63488,
        autoscroll: bool = True
    ) -> None:
        self.display = display
        self.layout = layout
        self.storage = storage
        self.buttons = list(buttons)
        self.name = name
        self.attr_iterator = attr_iterator
        self.yoffset = yoffset # This accounts for the Tab areas
        self.menubar_height = menubar_height
        self.header_height = header_height
        self.filter_group = filter_group
        self.color_border = color_border
        self.autoscroll = autoscroll

        self._init_attrs()

    def _init_attrs(self) -> None:
        """Initialize curses windows, panels, and state."""
        self.stdscr = self.display.stdscr
        self.maxy, self.maxx = self.stdscr.getmaxyx()
        self.loop = None

        self.body_posy = 0
        self.body_posx = 0
        self.storage_cursor = 0

        self.menubar = Menubar(self.display, buttons=self.buttons)

        # Whole workspace area win and panel
        workspace_h = self.maxy - self.yoffset - self.menubar_height
        self.win = curses.newwin(workspace_h, self.maxx, self.yoffset, 0)
        self.panel = curses.panel.new_panel(self.win)
        self.active_panel = self.panel
        self.panel.show()

        # Workspace header area for column names
        self.headerwin = self.win.derwin(self.header_height, self.maxx, 0, 0)

        # Workspace body area for rows
        body_h = workspace_h - self.header_height - 1 # 1 for border
        body_w = self.maxx - 2 # 2 for border
        self.bodywin = self.win.derwin(body_h, body_w, self.header_height, 1)

        self.button_map: Dict[int, Any] = {}
        for button in self.buttons:
            self.button_map[button.char_int] = button
            try:
                upper = ord(chr(button.char_int).upper())
                self.button_map[upper] = button
            except Exception:
                pass
        
        self.draw()

    def draw(self, dim: bool=False) -> None:
        """Redraw frame, header, body, and menubar."""
        self.draw_bodywin(dim)
        self.draw_box(dim)
        self.draw_headerwin(dim)
        self.menubar.draw()

    def _layout_iter(self, obj: Optional[Any] = None) -> Iterable[Any]:
        """
        Return an iterator yielding:
        (ypos, xpos, text, color)
        """
        if self.attr_iterator is not None:
            return (
                self.attr_iterator()
                if obj is None
                else self.attr_iterator(obj)
            )

        if hasattr(self.layout, "iter_attrs"):
            return self.layout.iter_attrs(obj)

        return []

    def draw_box(self, dim: bool=False) -> None:
        """Draw box"""
        colorb = self.color_border | curses.A_DIM if dim else self.color_border
        try:
            self.win.erase()
            self.win.attron(colorb)
            self.win.box()
            self.win.attroff(colorb)
        except curses.error:
            pass
        
        self.win.noutrefresh()

    def draw_headerwin(self, dim: bool=False) -> None:
        """Draw column headers and separators."""
        colorb = self.color_border | curses.A_DIM if dim else self.color_border
        
        try:
            self.headerwin.erase()
            self.headerwin.attron(colorb)
            self.headerwin.box()
            self.headerwin.attroff(colorb)
        except curses.error:
            pass

        for idx, cell in enumerate(self._layout_iter()):
            try:
                _, xpos, text, color = cell
            except Exception:
                continue

            color = color | curses.A_DIM if dim else color

            try:
                if idx > 0:
                    self.headerwin.addstr(0, xpos - 1, u"┬", colorb)
                    self.headerwin.addstr(1, xpos - 1, u"│", colorb)
                    self.headerwin.addstr(2, xpos - 1, u"┼", colorb)

                self.headerwin.addstr(1, xpos, text, color)
                self.headerwin.addstr(2, 0, u"├", colorb)
                self.headerwin.addstr(2, self.maxx - 1, u"┤", colorb)
            except curses.error:
                pass

        self.headerwin.refresh()

    def draw_bodywin(self, dim: bool=False, xoffset: int=1) -> None:
        """Draw visible rows from storage. The xoffset compensates for
           the left border and is subtracted from xpos.
        """
        if self.panel.hidden():
           return
 
        try:
            self.bodywin.erase()
        except curses.error:
            pass

        body_h, _ = self.bodywin.getmaxyx()
        n = len(self.storage)

        if self.autoscroll and n > 0:
            # Keep the selection pinned to the last item.
            self.storage_cursor = max(0, n - body_h)
            self.body_posy = min(body_h - 1, n - 1 - self.storage_cursor)
        else:
            # Clamp state if storage shrank or cursor went out of range.
            max_cursor = max(0, n - body_h)
            self.storage_cursor = min(self.storage_cursor, max_cursor)
            if n == 0:
                self.body_posy = 0
            else:
                self.body_posy = min(self.body_posy, min(body_h - 1, n - 1))

        end_idx = min(self.storage_cursor + body_h, len(self.storage))
        visible = self.storage.select((self.storage_cursor, end_idx))
        colorb = self.color_border | curses.A_DIM if dim else self.color_border

        for row, obj in enumerate(visible):
            for cell in self._layout_iter(obj):
                try:
                    _, xpos, text, color = cell
                except Exception:
                    continue

                if row != self.body_posy:
                    color |= curses.A_DIM
                    
                xpos = max(0, xpos - xoffset)
                color = color | curses.A_DIM if dim else color

                try:
                    self.bodywin.addstr(row, xpos, text, color)
                    self.bodywin.addstr(row, xpos + len(text), u"│", colorb)
                except curses.error:
                    pass

        if not self.panel.hidden():
            self.bodywin.noutrefresh()
            #self.draw_box(dim)
        self.menubar.draw()

    def cursor_handler(self, char: int) -> None:
        """Update cursor/scroll state and control autoscroll."""
        body_h, _ = self.bodywin.getmaxyx()
        n = len(self.storage)

        last_visible = max(0, body_h - 1)
        max_cursor = max(0, n - body_h)

        def at_last_item() -> bool:
            if n == 0:
                return True
            return (self.storage_cursor + self.body_posy) >= (n - 1)

        if char == curses.KEY_DOWN:
            if n == 0:
                return

            if (
                self.body_posy == last_visible and
                self.storage_cursor < max_cursor
            ):
                self.storage_cursor += 1
            
            elif (
                    self.body_posy < last_visible and
                    self.body_posy < n - 1
            ):
                self.body_posy += 1

            if at_last_item():
                self.autoscroll = True

        elif char == curses.KEY_UP:
            if n == 0:
                return

            self.autoscroll = False
            if self.body_posy == 0 and self.storage_cursor > 0:
                self.storage_cursor -= 1
            elif self.body_posy > 0:
                self.body_posy -= 1

        elif char == curses.KEY_HOME:
            self.autoscroll = False
            self.storage_cursor = 0
            self.body_posy = 0

        elif char == curses.KEY_END:
            self.autoscroll = True
            if n == 0:
                self.storage_cursor = 0
                self.body_posy = 0
            else:
                self.storage_cursor = max_cursor
                self.body_posy = min(last_visible, n - 1 - self.storage_cursor)

        elif char == curses.KEY_NPAGE:
            if n == 0:
                return

            self.autoscroll = False

            # If already at/beyond last visible item, jump to END
            if at_last_item():
                self.autoscroll = True
                self.storage_cursor = max_cursor
                self.body_posy = min(last_visible, n - 1 - self.storage_cursor)
                return

            # Otherwise, move down by one page.
            new_abs = min(n - 1, self.storage_cursor + self.body_posy + body_h)
            self.storage_cursor = min(new_abs, max_cursor)
            self.body_posy = body_h #new_abs - self.storage_cursor

            if at_last_item():
                self.autoscroll = True

        elif char == curses.KEY_PPAGE:
            if n == 0:
                return

            self.autoscroll = False

            new_abs = max(0, self.storage_cursor + self.body_posy - body_h)
            self.storage_cursor = min(new_abs, max_cursor)
            self.body_posy = new_abs - self.storage_cursor

    def handle_char(self, char: int) -> None:
        """Handle navigation, workspace switching, and buttons."""
        if char in (9, curses.KEY_BTAB, 8, curses.KEY_BACKSPACE):
            if self.panel.hidden():
                self.display.active_handle_char(char)

            self.stdscr.erase()
            ws_len = max(1, len(self.display.workspaces))

            if char in (9, curses.KEY_BTAB):
                self.display.active_ws_idx = (
                    self.display.active_ws_idx + 1
                ) % ws_len
                if getattr(self.display, "tab", None):
                    self.display.tab.next_tab()

            elif char in (8, curses.KEY_BACKSPACE):
                self.display.active_ws_idx = (
                    self.display.active_ws_idx - 1
                ) % ws_len
                if getattr(self.display, "tab", None):
                    self.display.tab.prev_tab()

            aws = self.display.active_workspace
            if aws:
                try:
                    aws.bodywin.erase()
                except curses.error:
                    pass

                aws.draw()
                aws.panel.top()
                aws.panel.show()
                self.display.active_handle_char = aws.handle_char

            curses.panel.update_panels()
            return

        if char in (
            curses.KEY_UP,
            curses.KEY_DOWN,
            curses.KEY_LEFT,
            curses.KEY_RIGHT,
            curses.KEY_HOME,
            curses.KEY_END,
            curses.KEY_NPAGE,
            curses.KEY_PPAGE,
        ):
            self.cursor_handler(char)
            self.draw_bodywin()
            return

        if char in self.button_map:
            self.button_map[char].toggle(self)
            if self.panel == self.active_panel:
                self.draw()

############################## END WORKSPACE ##################################

if __name__ == "__main__":       
    def setup_dummy():
        global BGWs, GWs, RTPs, PCAPs
        bgw1 = BGW(**{'bgw_ip': '10.10.48.58', 'proto': 'ptls', 'polling_secs': 10, 'gw_name': 'AvayaG450A', 'gw_number': '001', 'polls': 1, 'avg_poll_secs': 10, 'active_session_ids': set(), 'last_seen': datetime(2025, 12, 16, 14, 33, 39), 'last_session_id': '', 'show_announcements_files': '\r\n ID      File               Description    Size (Bytes)      Date\r\n---- ------------------ ------------------ ------------ -------------------\r\n101   moh.wav            announcement file      239798    2022-08-23,8:45:26  \r\n102   emergency.wav      announcement file       26618    2023-03-24,11:36:10 \r\n103   public_announceme  announcement file      201914    2024-10-24,7:37:52  \r\n104   mohtest.wav        announcement file     9648106    2025-07-15,14:50:16 \r\n\r\nNv-Ram:\r\nTotal bytes used             : 10119680  \r\nTotal bytes free             : 12672000  \r\nTotal bytes capacity (fixed) : 22791680', 'show_capture': '\r\n\r\nCapture service is enabled and active\r\nCapture start time 09/12/2025-09:25:13\r\nCapture stop time not-stopped\r\nCurrent buffer size is 1024 KB\r\nBuffer mode is non-cyclic\r\nMaximum number of bytes captured from each frame: 4096\r\nCapture list 501 on all interfaces\r\nCapture IPSec decrypted\r\nNumber of captured frames in file: 604 (out of 145200 total captured frames)\r\nMemory buffer occupancy: 4.62% (including overheads)', 'show_faults': '\r\n\r\nCURRENTLY ACTIVE FAULTS\r\n--------------------------------------------------------------------------\r\n\r\n-- Media Module Faults --\r\n\t+ Insertion failure, mmid = v5, 11/24-07:37:04.00\r\n\r\nCurrent Alarm Indications, ALM LED is off\r\n--------------------------------------------------------------------------\r\nNone', 'show_lldp_config': '\r\n\r\nLldp Configuration \r\n-------------------\r\nApplication status: enable \r\nTx interval: 30 seconds\r\nTx hold multiplier: 4 seconds\r\nTx delay: 2 seconds\r\nReinit delay: 2 seconds', 'show_mg_list': '\r\nSLOT   TYPE         CODE        SUFFIX  HW VINTAGE  FW VINTAGE \r\n----   --------     ----------  ------  ----------  -----------\r\nv1     S8300        ICC         E       1           255\r\nv2     -- Not Installed --\r\nv3     E1T1         MM710       B       16          52\r\nv4     -- Not Installed --\r\nv5     -- Initializing --\r\nv6     Analog       MM714       B       23          94\r\nv7     -- Not Installed --\r\nv8     -- Not Installed --\r\nv10    Mainboard    G450        B       2           42.36.0(A)', 'show_port': '\r\nPort   Name             Status    Vlan Level  Neg     Dup. Spd. Type\r\n------ ---------------- --------- ---- ------ ------- ---- ---- ----------------\r\n10/5   NO NAME          connected 1     0     enable  half 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/5\r\n\r\n10/6   NO NAME          no link   1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/6', 'show_rtp_stat_summary': '', 'show_running_config': '\r\n\r\n! version 42.36.0\r\nConfig info release 42.36.0 time "13:33:51 16 DEC 2025 " serial_number 10IS41452851\r\n !\r\nencrypted-username +ikJzwEP/t+XkAlH3l+zsw== password G6uSyomIZMSDb0NnT4RwvSb4IrSGUtuQ9ypCGFikR4w= access-type fe/kaDE5GWBC9Nfj6bNkgA==\r\n!\r\nencrypted-username mJ6sF5BOZeIUWsyCb3C1bw== password 8tMk4PMmywAU0cVXzSERF/aaj9WF0EAq4dB4c0qOLbU= access-type gf0PKwZMZRJ4zRba06ZC3w==\r\nhostname "AvayaG450A"\r\nset system location "Ontario Lab" \r\nno ip telnet \r\nip tftp-server file-system-size 2288\r\nset port mirror source-port 10/5 mirror-port 10/6 sampling always direction both\r\n!\r\nip capture-list 501\r\n name "udp"\r\n!\r\n ip-rule 1\r\n  ip-protocol udp\r\n exit\r\n ip-rule default\r\n  composite-operation "No-Capture"\r\n exit\r\n!\r\nexit\r\n!\r\nds-mode t1\r\n!\r\ninterface Vlan 1\r\n icc-vlan\r\n server-blade-vlan 5\r\n ip address 10.10.48.58     255.255.255.0  \r\n pmi\r\n exit\r\n!\r\ninterface FastEthernet 10/3\r\n exit\r\n!\r\ninterface FastEthernet 10/4\r\n exit\r\n!\r\ninterface Console\r\n speed 9600\r\n exit\r\n!\r\ninterface USB-Modem\r\n description "Default Modem Setup"\r\n timeout absolute 10\r\n ppp authentication ras\r\n no shutdown\r\n ip address 10.3.248.253    255.255.255.252\r\n exit\r\n!\r\ncapture max-frame-size 4096\r\ncapture buffer-mode non-cyclic\r\ncapture filter-group 501\r\nlogin authentication min-password-length 8\r\n!\r\nlogin authentication lockout 0 attempt 0\r\n! Avaya Login Confirmation Received.\r\nEASGManage enableEASG\r\nproduct-id 8c2ae2eead3e6cca800be892bb6e3411\r\n!\r\nset logging file enable \r\nset logging file condition all Error \r\nset logging file condition BOOT Debug \r\n!\r\nno snmp-server community \r\nencrypted-snmp-server user JSXE8Ccs0N0TnuoQek8jwLmaP391mjHjbt9glvbZ2M0= gAAa6QMAG08/c+A= v3ReadISO v3 auth sha 1FCIRMijXV+77fer97/S9O3FlfqIPrTOC5uTFcklYM8=  priv aes128 yyv5YmpCoEn5xZ24B7MR4Y03gnnqwygOY3eQTGRZZB0= \r\nencrypted-snmp-server user 0Ce9aP8Q25tEoXTe0YGwKmt2qLFQJ+UOpG6SMzseQdg= gAAa6QMAG08/c+A= v3TrapISO v3 auth sha TgX0mUpViHn56rSWounTurOYUdreS7rWWY7KssAnYj4=  priv aes128 p5Rdzsia/+4+Uc7f9oeJOj38gI6qX+2Fy1WDL5PTkh8= \r\nsnmp-server group v3ReadISO v3 priv read iso  \r\nsnmp-server group v3TrapISO v3 priv notify iso  \r\nsnmp-server host 10.10.48.92 traps v3 priv bbysnmpv3trap \r\n!\r\nip default-gateway 10.10.48.254    1 low  \r\n!\r\nset sync interface primary v3\r\nset sync source primary\r\nrtp-stat-service\r\nrtp-stat fault\r\nanalog-test\r\nexit\r\n!\r\nset sla-monitor enable\r\nset sla-server-ip-address 10.10.48.198\r\nudp keepalive 10\r\nset mgc list 10.10.48.240\r\nset mediaserver 10.10.48.240 10.10.48.240 23 telnet\r\nset mediaserver 10.10.48.240 10.10.48.240 5023 sat\r\n!#\r\n!# End of configuration file. Press Enter to continue.', 'show_sla_monitor': '\r\n\r\nSLA Monitor:                  Enabled\r\nRegistered Server IP Address: 192.111.111.111\r\nRegistered Server IP Port:    0\r\nConfigured Server IP Address: 10.10.48.198\r\nConfigured Server IP Port:    50011\r\nCapture Mode:                 None\r\nVersion:                      2.7.0', 'show_system': '\r\nSystem Name             : AvayaG450A\r\nSystem Location         : Ontario Lab\r\nSystem Contact          : \r\nUptime (d,h:m:s)        : 422,06:00:13\r\nCall Controller Time    : 13:33:56 16 DEC 2025 \r\nSerial No               : 13TG01116522\r\nModel                   : G430v3\r\nChassis HW Vintage      : 3\r\nChassis HW Suffix       : A\r\nMainboard HW Vintage    : 2\r\nMainboard HW Suffix     : B\r\nMainboard HW CS         : 2.1.7\r\nMainboard FW Vintage    : 42.36.0\r\nLAN MAC Address         : 00:1b:4f:3f:73:e0\r\nWAN1 MAC Address        : 00:1b:4f:3f:73:e1\r\nWAN2 MAC Address        : 00:1b:4f:3f:73:e2\r\nSERVICES MAC address    : 00:1b:4f:3f:73:e3\r\nMemory #1               : 256MB\r\nMemory #2               : Not present\r\nCompact Flash Memory    : 1GB Compact Flash card is installed\r\nPSU #1                  : AC 400W\r\nPSU #2                  : Not present\r\nMedia Socket #1         : MP160 VoIP DSP Module\r\nMedia Socket #2         : Not present\r\nMedia Socket #3         : Not present\r\nMedia Socket #4         : Not present\r\nFAN Tray                : Present', 'show_temp': '\r\nAmbient\r\n-------\r\nTemperature : -5C (23F)\r\nHigh Warning: 42C (108F)\r\nLow Warning : -5C (23F)', 'show_utilization': '\r\n\r\nMod   CPU      CPU     RAM      RAM\r\n      5sec     60sec   used(%)  Total(Kb)\r\n---   ------   -----  -------  ----------\r\n10    Appl. Disabled    48%     190838 Kb', 'show_voip_dsp': '\r\nDSP #1 PARAMETERS\r\n--------------------------------------------------------------\r\nBoard type     : MP160\r\nHw Vintage     : 0 B\r\nFw Vintage     : 182\r\n\r\nDSP#1 CURRENT STATE\r\n--------------------------------------------------------------\r\nIn Use         : 0 of 160 channels, 0 of 4800 points (0.0% used)\r\nState          : Idle\r\nAdmin State    : Release\r\n\r\nCore# Channels Admin     State\r\n      In Use   State\r\n----- -------- --------- -------\r\n    1  0 of 40   Release Idle\r\n    2  0 of 40   Release Idle\r\n    3  0 of 40   Release Idle\r\n    4  0 of 40   Release Idle\r\n\r\n\r\nDSP #2 Not Present\r\n\r\n\r\nDSP #3 Not Present\r\n\r\n\r\nDSP #4 Not Present', 'queue': Queue(), '_active_session': None, '_announcements': None, '_capture_service': None, '_chassis_hw': None, '_comp_flash': None, '_cpu_util': None, '_dsp': None, '_faults': None, '_fw': None, '_hw': None, '_inuse_dsp': None, '_last_seen_time': None, '_lldp': None, '_location': None, '_mac': None, '_mainboard_hw': None, '_memory': None, '_mm_groupdict': None, '_mm_v1': None, '_mm_v2': None, '_mm_v3': None, '_mm_v4': None, '_mm_v5': None, '_mm_v6': None, '_mm_v7': None, '_mm_v8': None, '_mm_v10': None, '_model': None, '_port1': None, '_port1_status': None, '_port1_neg': None, '_port1_duplex': None, '_port1_speed': None, '_port2': None, '_port2_status': None, '_port2_neg': None, '_port2_duplex': None, '_port2_speed': None, '_port_redu': None, '_psu1': None, '_psu2': None, '_ram_util': None, '_rtp_stat_service': None, '_serial': None, '_slamon_service': None, '_sla_server': None, '_snmp': None, '_snmp_trap': None, '_temp': None, '_total_session': None, '_uptime': None})
        bgw2 = BGW(**{'bgw_ip': '10.10.48.59', 'proto': 'ptls', 'polling_secs': 10, 'gw_name': 'AvayaG450B', 'gw_number': '002', 'polls': 1, 'avg_poll_secs': 10, 'active_session_ids': set(), 'last_seen': datetime(2025, 12, 16, 14, 33, 39), 'last_session_id': '', 'show_announcements_files': '\r\n ID      File               Description    Size (Bytes)      Date\r\n---- ------------------ ------------------ ------------ -------------------\r\n101   moh.wav            announcement file      239798    2022-08-23,8:45:26  \r\n102   emergency.wav      announcement file       26618    2023-03-24,11:36:10 \r\n103   public_announceme  announcement file      201914    2024-10-24,7:37:52  \r\n104   mohtest.wav        announcement file     9648106    2025-07-15,14:50:16 \r\n\r\nNv-Ram:\r\nTotal bytes used             : 10119680  \r\nTotal bytes free             : 12672000  \r\nTotal bytes capacity (fixed) : 22791680', 'show_capture': '\r\n\r\nCapture service is enabled and active\r\nCapture start time 09/12/2025-09:25:13\r\nCapture stop time not-stopped\r\nCurrent buffer size is 1024 KB\r\nBuffer mode is non-cyclic\r\nMaximum number of bytes captured from each frame: 4096\r\nCapture list 501 on all interfaces\r\nCapture IPSec decrypted\r\nNumber of captured frames in file: 604 (out of 145200 total captured frames)\r\nMemory buffer occupancy: 4.62% (including overheads)', 'show_faults': '\r\n\r\nCURRENTLY ACTIVE FAULTS\r\n--------------------------------------------------------------------------\r\n\r\n-- Media Module Faults --\r\n\t+ Insertion failure, mmid = v5, 11/24-07:37:04.00\r\n\r\nCurrent Alarm Indications, ALM LED is off\r\n--------------------------------------------------------------------------\r\nNone', 'show_lldp_config': '\r\n\r\nLldp Configuration \r\n-------------------\r\nApplication status: disable \r\nTx interval: 30 seconds\r\nTx hold multiplier: 4 seconds\r\nTx delay: 2 seconds\r\nReinit delay: 2 seconds', 'show_mg_list': '\r\nSLOT   TYPE         CODE        SUFFIX  HW VINTAGE  FW VINTAGE \r\n----   --------     ----------  ------  ----------  -----------\r\nv1     -- Not Installed --\r\nv2     -- Not Installed --\r\nv3     E1T1         MM710       B       16          52\r\nv4     -- Not Installed --\r\nv5     -- Initializing --\r\nv6     Analog       MM714       B       23          94\r\nv7     -- Not Installed --\r\nv8     -- Not Installed --\r\nv10    Mainboard    G450        B       2           42.36.0(A)', 'show_port': '\r\nPort   Name             Status    Vlan Level  Neg     Dup. Spd. Type\r\n------ ---------------- --------- ---- ------ ------- ---- ---- ----------------\r\n10/5   NO NAME          connected 1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/5\r\n\r\n10/6   NO NAME          connected   1     0     enable  half 10M   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/6', 'show_rtp_stat_summary': '', 'show_running_config': '\r\n\r\n! version 42.36.0\r\nConfig info release 42.36.0 time "13:33:51 16 DEC 2025 " serial_number 10IS41452851\r\n !\r\nencrypted-username +ikJzwEP/t+XkAlH3l+zsw== password G6uSyomIZMSDb0NnT4RwvSb4IrSGUtuQ9ypCGFikR4w= access-type fe/kaDE5GWBC9Nfj6bNkgA==\r\n!\r\nencrypted-username mJ6sF5BOZeIUWsyCb3C1bw== password 8tMk4PMmywAU0cVXzSERF/aaj9WF0EAq4dB4c0qOLbU= access-type gf0PKwZMZRJ4zRba06ZC3w==\r\nhostname "AvayaG450A"\r\nset system location "Calgary" \r\nno ip telnet \r\nip tftp-server file-system-size 2288\r\nset port mirror source-port 10/5 mirror-port 10/6 sampling always direction both\r\n!\r\nip capture-list 501\r\n name "udp"\r\n!\r\n ip-rule 1\r\n  ip-protocol udp\r\n exit\r\n ip-rule default\r\n  composite-operation "No-Capture"\r\n exit\r\n!\r\nexit\r\n!\r\nds-mode t1\r\n!\r\ninterface Vlan 1\r\n icc-vlan\r\n server-blade-vlan 5\r\n ip address 10.10.48.59     255.255.255.0  \r\n pmi\r\n exit\r\n!\r\ninterface FastEthernet 10/3\r\n exit\r\n!\r\ninterface FastEthernet 10/4\r\n exit\r\n!\r\ninterface Console\r\n speed 9600\r\n exit\r\n!\r\ninterface USB-Modem\r\n description "Default Modem Setup"\r\n timeout absolute 10\r\n ppp authentication ras\r\n no shutdown\r\n ip address 10.3.248.253    255.255.255.252\r\n exit\r\n!\r\ncapture max-frame-size 4096\r\ncapture buffer-mode non-cyclic\r\ncapture filter-group 501\r\nlogin authentication min-password-length 8\r\n!\r\nlogin authentication lockout 0 attempt 0\r\n! Avaya Login Confirmation Received.\r\nEASGManage enableEASG\r\nproduct-id 8c2ae2eead3e6cca800be892bb6e3411\r\n!\r\nset logging file enable \r\nset logging file condition all Error \r\nset logging file condition BOOT Debug \r\n!\r\nno snmp-server community \r\nencrypted-snmp-server user JSXE8Ccs0N0TnuoQek8jwLmaP391mjHjbt9glvbZ2M0= gAAa6QMAG08/c+A= v3ReadISO v3 auth sha 1FCIRMijXV+77fer97/S9O3FlfqIPrTOC5uTFcklYM8=  priv aes128 yyv5YmpCoEn5xZ24B7MR4Y03gnnqwygOY3eQTGRZZB0= \r\nencrypted-snmp-server user 0Ce9aP8Q25tEoXTe0YGwKmt2qLFQJ+UOpG6SMzseQdg= gAAa6QMAG08/c+A= v3TrapISO v3 auth sha TgX0mUpViHn56rSWounTurOYUdreS7rWWY7KssAnYj4=  priv aes128 p5Rdzsia/+4+Uc7f9oeJOj38gI6qX+2Fy1WDL5PTkh8= \r\nsnmp-server group v3ReadISO v3 priv read iso  \r\nsnmp-server group v3TrapISO v3 priv notify iso  \r\nsnmp-server host 10.10.48.92 traps v3 priv bbysnmpv3trap \r\n!\r\nip default-gateway 10.10.48.254    1 low  \r\n!\r\nset sync interface primary v3\r\nset sync source primary\r\nrtp-stat-service\r\nrtp-stat fault\r\nanalog-test\r\nexit\r\n!\r\nset sla-monitor enable\r\nset sla-server-ip-address 10.10.48.198\r\nudp keepalive 10\r\nset mgc list 10.10.48.240\r\nset mediaserver 10.10.48.240 10.10.48.240 23 telnet\r\nset mediaserver 10.10.48.240 10.10.48.240 5023 sat\r\n!#\r\n!# End of configuration file. Press Enter to continue.', 'show_sla_monitor': '\r\n\r\nSLA Monitor:                  Enabled\r\nRegistered Server IP Address: 0.0.0.0\r\nRegistered Server IP Port:    0\r\nConfigured Server IP Address: 10.10.48.198\r\nConfigured Server IP Port:    50011\r\nCapture Mode:                 None\r\nVersion:                      2.7.0', 'show_system': '\r\nSystem Name             : AvayaG450B\r\nSystem Location         : Calgary\r\nSystem Contact          : \r\nUptime (d,h:m:s)        : 22,06:00:13\r\nCall Controller Time    : 13:33:56 16 DEC 2025 \r\nSerial No               : 13TG01116522\r\nModel                   : G450\r\nChassis HW Vintage      : 1\r\nChassis HW Suffix       : A\r\nMainboard HW Vintage    : 2\r\nMainboard HW Suffix     : B\r\nMainboard HW CS         : 2.1.7\r\nMainboard FW Vintage    : 42.36.0\r\nLAN MAC Address         : 00:1b:4f:3f:73:e8\r\nWAN1 MAC Address        : 00:1b:4f:3f:73:e1\r\nWAN2 MAC Address        : 00:1b:4f:3f:73:e2\r\nSERVICES MAC address    : 00:1b:4f:3f:73:e3\r\nMemory #1               : 256MB\r\nMemory #2               : Not present\r\nCompact Flash Memory    : No CompactFlash card is installed\r\nPSU #1                  : AC 400W\r\nPSU #2                  : AC 400W\r\nMedia Socket #1         : MP160 VoIP DSP Module\r\nMedia Socket #2         : Not present\r\nMedia Socket #3         : Not present\r\nMedia Socket #4         : Not present\r\nFAN Tray                : Present', 'show_temp': '\r\nAmbient\r\n-------\r\nTemperature : 42C (108F)\r\nHigh Warning: 42C (108F)\r\nLow Warning : -5C (23F)', 'show_utilization': '\r\n\r\nMod   CPU      CPU     RAM      RAM\r\n      5sec     60sec   used(%)  Total(Kb)\r\n---   ------   -----  -------  ----------\r\n10    Appl. Disabled    48%     190838 Kb', 'show_voip_dsp': '\r\nDSP #1 PARAMETERS\r\n--------------------------------------------------------------\r\nBoard type     : MP160\r\nHw Vintage     : 0 B\r\nFw Vintage     : 182\r\n\r\nDSP#1 CURRENT STATE\r\n--------------------------------------------------------------\r\nIn Use         : 0 of 160 channels, 0 of 4800 points (0.0% used)\r\nState          : Idle\r\nAdmin State    : Release\r\n\r\nCore# Channels Admin     State\r\n      In Use   State\r\n----- -------- --------- -------\r\n    1  0 of 40   Release Idle\r\n    2  0 of 40   Release Idle\r\n    3  0 of 40   Release Idle\r\n    4  0 of 40   Release Idle\r\n\r\n\r\nDSP #2 Not Present\r\n\r\n\r\nDSP #3 Not Present\r\n\r\n\r\nDSP #4 Not Present', 'queue': Queue(), '_active_session': None, '_announcements': None, '_capture_service': None, '_chassis_hw': None, '_comp_flash': None, '_cpu_util': None, '_dsp': None, '_faults': None, '_fw': None, '_hw': None, '_inuse_dsp': None, '_last_seen_time': None, '_lldp': None, '_location': None, '_mac': None, '_mainboard_hw': None, '_memory': None, '_mm_groupdict': None, '_mm_v1': None, '_mm_v2': None, '_mm_v3': None, '_mm_v4': None, '_mm_v5': None, '_mm_v6': None, '_mm_v7': None, '_mm_v8': None, '_mm_v10': None, '_model': None, '_port1': None, '_port1_status': None, '_port1_neg': None, '_port1_duplex': None, '_port1_speed': None, '_port2': None, '_port2_status': None, '_port2_neg': None, '_port2_duplex': None, '_port2_speed': None, '_port_redu': None, '_psu1': None, '_psu2': None, '_ram_util': None, '_rtp_stat_service': None, '_serial': None, '_slamon_service': None, '_sla_server': None, '_snmp': None, '_snmp_trap': None, '_temp': None, '_total_session': None, '_uptime': None})
        bgw3 = BGW(**{'bgw_ip': '192.168.110.111', 'proto': 'ptls', 'polling_secs': 10, 'gw_name': 'AvayaG450C', 'gw_number': '003', 'polls': 1, 'avg_poll_secs': 10, 'active_session_ids': set(), 'last_seen': datetime(2025, 12, 16, 14, 33, 39), 'last_session_id': '', 'show_announcements_files': '\r\n ID      File               Description    Size (Bytes)      Date\r\n---- ------------------ ------------------ ------------ -------------------\r\n101   moh.wav            announcement file      239798    2022-08-23,8:45:26  \r\n102   emergency.wav      announcement file       26618    2023-03-24,11:36:10 \r\n103   public_announceme  announcement file      201914    2024-10-24,7:37:52  \r\n104   mohtest.wav        announcement file     9648106    2025-07-15,14:50:16 \r\n\r\nNv-Ram:\r\nTotal bytes used             : 10119680  \r\nTotal bytes free             : 12672000  \r\nTotal bytes capacity (fixed) : 22791680', 'show_capture': '\r\n\r\nCapture service is enabled and active\r\nCapture start time 09/12/2025-09:25:13\r\nCapture stop time not-stopped\r\nCurrent buffer size is 1024 KB\r\nBuffer mode is non-cyclic\r\nMaximum number of bytes captured from each frame: 4096\r\nCapture list 501 on all interfaces\r\nCapture IPSec decrypted\r\nNumber of captured frames in file: 604 (out of 145200 total captured frames)\r\nMemory buffer occupancy: 4.62% (including overheads)', 'show_faults': '\r\n\r\nNo Fault Messages\r\n--------------------------------------------------------------------------\r\nNone', 'show_lldp_config': '\r\n\r\nLldp Configuration \r\n-------------------\r\nApplication status: disable \r\nTx interval: 30 seconds\r\nTx hold multiplier: 4 seconds\r\nTx delay: 2 seconds\r\nReinit delay: 2 seconds', 'show_mg_list': '\r\nSLOT   TYPE         CODE        SUFFIX  HW VINTAGE  FW VINTAGE \r\n----   --------     ----------  ------  ----------  -----------\r\nv1     -- Not Installed --\r\nv2     -- Not Installed --\r\nv3     E1T1         MM710       B       16          52\r\nv4     -- Not Installed --\r\nv5     -- Initializing --\r\nv6     Analog       MM714       B       23          104\r\nv7     Analog       MM714       A       23          114\r\nv8     -- Not Installed --\r\nv10    Mainboard    G450        B       2           42.36.0(A)', 'show_port': '\r\nPort   Name             Status    Vlan Level  Neg     Dup. Spd. Type\r\n------ ---------------- --------- ---- ------ ------- ---- ---- ----------------\r\n10/5   NO NAME          connected 1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/5\r\n\r\n10/6   NO NAME          no link   1     0     enable  full 1G   Avaya Inc., G450 Media Gateway 10/100/1000BaseTx Port 10/6', 'show_rtp_stat_summary': '', 'show_running_config': '\r\n\r\n! version 42.36.0\r\nConfig info release 42.36.0 time "13:33:51 16 DEC 2025 " serial_number 10IS41452851\r\n !\r\nencrypted-username +ikJzwEP/t+XkAlH3l+zsw== password G6uSyomIZMSDb0NnT4RwvSb4IrSGUtuQ9ypCGFikR4w= access-type fe/kaDE5GWBC9Nfj6bNkgA==\r\n!\r\nencrypted-username mJ6sF5BOZeIUWsyCb3C1bw== password 8tMk4PMmywAU0cVXzSERF/aaj9WF0EAq4dB4c0qOLbU= access-type gf0PKwZMZRJ4zRba06ZC3w==\r\nhostname "AvayaG450A"\r\nset system location "Calgary" \r\nno ip telnet \r\nip tftp-server file-system-size 2288\r\nset port mirror source-port 10/5 mirror-port 10/6 sampling always direction both\r\n!\r\nip capture-list 501\r\n name "udp"\r\n!\r\n ip-rule 1\r\n  ip-protocol udp\r\n exit\r\n ip-rule default\r\n  composite-operation "No-Capture"\r\n exit\r\n!\r\nexit\r\n!\r\nds-mode t1\r\n!\r\ninterface Vlan 1\r\n icc-vlan\r\n server-blade-vlan 5\r\n ip address 192.168.110.111     255.255.255.0  \r\n pmi\r\n exit\r\n!\r\ninterface FastEthernet 10/3\r\n exit\r\n!\r\ninterface FastEthernet 10/4\r\n exit\r\n!\r\ninterface Console\r\n speed 9600\r\n exit\r\n!\r\ninterface USB-Modem\r\n description "Default Modem Setup"\r\n timeout absolute 10\r\n ppp authentication ras\r\n no shutdown\r\n ip address 10.3.248.253    255.255.255.252\r\n exit\r\n!\r\ncapture max-frame-size 4096\r\ncapture buffer-mode non-cyclic\r\ncapture filter-group 501\r\nlogin authentication min-password-length 8\r\n!\r\nlogin authentication lockout 0 attempt 0\r\n! Avaya Login Confirmation Received.\r\nEASGManage enableEASG\r\nproduct-id 8c2ae2eead3e6cca800be892bb6e3411\r\n!\r\nset logging file enable \r\nset logging file condition all Error \r\nset logging file condition BOOT Debug \r\n!\r\nno snmp-server community \r\nencrypted-snmp-server user JSXE8Ccs0N0TnuoQek8jwLmaP391mjHjbt9glvbZ2M0= gAAa6QMAG08/c+A= v3ReadISO v3 auth sha 1FCIRMijXV+77fer97/S9O3FlfqIPrTOC5uTFcklYM8=  priv aes128 yyv5YmpCoEn5xZ24B7MR4Y03gnnqwygOY3eQTGRZZB0= \r\nencrypted-snmp-server user 0Ce9aP8Q25tEoXTe0YGwKmt2qLFQJ+UOpG6SMzseQdg= gAAa6QMAG08/c+A= v3TrapISO v3 auth sha TgX0mUpViHn56rSWounTurOYUdreS7rWWY7KssAnYj4=  priv aes128 p5Rdzsia/+4+Uc7f9oeJOj38gI6qX+2Fy1WDL5PTkh8= \r\nsnmp-server group v3ReadISO v3 priv read iso  \r\nsnmp-server group v3TrapISO v3 priv notify iso  \r\nsnmp-server host 10.10.48.92 traps v3 priv bbysnmpv3trap \r\n!\r\nip default-gateway 10.10.48.254    1 low  \r\n!\r\nset sync interface primary v3\r\nset sync source primary\r\nrtp-stat-service\r\nrtp-stat fault\r\nanalog-test\r\nexit\r\n!\r\nset sla-monitor enable\r\nset sla-server-ip-address 10.10.48.198\r\nudp keepalive 10\r\nset mgc list 10.10.48.240\r\nset mediaserver 10.10.48.240 10.10.48.240 23 telnet\r\nset mediaserver 10.10.48.240 10.10.48.240 5023 sat\r\n!#\r\n!# End of configuration file. Press Enter to continue.', 'show_sla_monitor': '\r\n\r\nSLA Monitor:                 Disabled\r\nRegistered Server IP Address: 0.0.0.0\r\nRegistered Server IP Port:    0\r\nConfigured Server IP Address: 10.10.48.198\r\nConfigured Server IP Port:    50011\r\nCapture Mode:                 None\r\nVersion:                      2.7.0', 'show_system': '\r\nSystem Name             : AvayaG450C\r\nSystem Location         : Calgary\r\nSystem Contact          : \r\nUptime (d,h:m:s)        : 22,06:00:13\r\nCall Controller Time    : 13:33:56 16 DEC 2025 \r\nSerial No               : 13TG01116522\r\nModel                   : G450\r\nChassis HW Vintage      : 1\r\nChassis HW Suffix       : A\r\nMainboard HW Vintage    : 2\r\nMainboard HW Suffix     : B\r\nMainboard HW CS         : 2.1.7\r\nMainboard FW Vintage    : 42.36.0\r\nLAN MAC Address         : 00:1b:4f:3f:73:e4\r\nWAN1 MAC Address        : 00:1b:4f:3f:73:e1\r\nWAN2 MAC Address        : 00:1b:4f:3f:73:e2\r\nSERVICES MAC address    : 00:1b:4f:3f:73:e4\r\nMemory #1               : 256MB\r\nMemory #2               : Not present\r\nCompact Flash Memory    : No CompactFlash card is installed\r\nPSU #1                  : AC 400W\r\nPSU #2                  : Not present\r\nMedia Socket #1         : MP160 VoIP DSP Module\r\nMedia Socket #2         : Not present\r\nMedia Socket #3         : Not present\r\nMedia Socket #4         : Not present\r\nFAN Tray                : Present', 'show_temp': '\r\nAmbient\r\n-------\r\nTemperature : 36C (97F)\r\nHigh Warning: 42C (108F)\r\nLow Warning : -5C (23F)', 'show_utilization': '\r\n\r\nMod   CPU      CPU     RAM      RAM\r\n      5sec     60sec   used(%)  Total(Kb)\r\n---   ------   -----  -------  ----------\r\n10    Appl. Disabled    48%     190838 Kb', 'show_voip_dsp': '\r\nDSP #1 PARAMETERS\r\n--------------------------------------------------------------\r\nBoard type     : MP160\r\nHw Vintage     : 0 B\r\nFw Vintage     : 182\r\n\r\nDSP#1 CURRENT STATE\r\n--------------------------------------------------------------\r\nIn Use         : 0 of 160 channels, 0 of 4800 points (0.0% used)\r\nState          : Idle\r\nAdmin State    : Release\r\n\r\nCore# Channels Admin     State\r\n      In Use   State\r\n----- -------- --------- -------\r\n    1  0 of 40   Release Idle\r\n    2  0 of 40   Release Idle\r\n    3  0 of 40   Release Idle\r\n    4  0 of 40   Release Idle\r\n\r\n\r\nDSP #2 Not Present\r\n\r\n\r\nDSP #3 Not Present\r\n\r\n\r\nDSP #4 Not Present', 'queue': Queue(), '_active_session': None, '_announcements': None, '_capture_service': None, '_chassis_hw': None, '_comp_flash': None, '_cpu_util': None, '_dsp': None, '_faults': None, '_fw': None, '_hw': None, '_inuse_dsp': None, '_last_seen_time': None, '_lldp': None, '_location': None, '_mac': None, '_mainboard_hw': None, '_memory': None, '_mm_groupdict': None, '_mm_v1': None, '_mm_v2': None, '_mm_v3': None, '_mm_v4': None, '_mm_v5': None, '_mm_v6': None, '_mm_v7': None, '_mm_v8': None, '_mm_v10': None, '_model': None, '_port1': None, '_port1_status': None, '_port1_neg': None, '_port1_duplex': None, '_port1_speed': None, '_port2': None, '_port2_status': None, '_port2_neg': None, '_port2_duplex': None, '_port2_speed': None, '_port_redu': None, '_psu1': None, '_psu2': None, '_ram_util': None, '_rtp_stat_service': None, '_serial': None, '_slamon_service': None, '_sla_server': None, '_snmp': None, '_snmp_trap': None, '_temp': None, '_total_session': None, '_uptime': None})
        BGWs = MemoryStorage({'001': bgw1, '002': bgw2, '003': bgw3})
        GWs = {'10.10.48.58': "001", "10.10.48.59": "002", "192.168.110.111": "003", "10.44.244.51": "004", "10.188.244.1": "005", "10.10.48.69": "006"}

        RTPs = MemoryStorage()
        d = {
            "2024-11-04,10:06:07,001,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 21\r\nStatus: Terminated, QOS: Faulted, EngineId: 10\r\nStart-Time: 2024-11-04,10:06:07, End-Time: 2024-11-04,10:07:07\r\nDuration: 00:02:00\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.111:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG729A 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 4.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1243, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 1, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 0, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 1.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2025-12-11,10:07:27,002,00002": "\r\nshow rtp-stat detailed 00002\r\n\r\nSession-ID: 11\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:07:27, End-Time: -\r\nDuration: - \r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.112:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (2)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 123, Loss 0.3% #0, Avg-Loss 0.3%, RTT 200mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 2, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 2.0% #0, Avg-Loss 1.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2025-12-11,10:08:07,003,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 1\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:08:07, End-Time: 2025-12-14,10:08:22\r\nDuration: 00:12:20\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.113:2056 SSRC 1653399062\r\nRemote-Address: 192.168.110.111:35001 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 230B 30mS Off, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 1.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 0, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2024-11-01,10:06:07,001,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 21\r\nStatus: Terminated, QOS: Faulted, EngineId: 10\r\nStart-Time: 2024-11-04,10:06:07, End-Time: 2024-11-04,10:07:07\r\nDuration: 00:02:00\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.111:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG729A 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 4.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1243, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 1, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 0, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 1.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2025-12-11,10:07:27,002,00002": "\r\nshow rtp-stat detailed 00002\r\n\r\nSession-ID: 11\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:07:27, End-Time: -\r\nDuration: - \r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.112:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (2)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 123, Loss 0.3% #0, Avg-Loss 0.3%, RTT 200mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 2, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 2.0% #0, Avg-Loss 1.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2025-12-12,10:08:07,003,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 1\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:08:07, End-Time: 2025-12-14,10:08:22\r\nDuration: 00:12:20\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.113:2056 SSRC 1653399062\r\nRemote-Address: 192.168.110.111:35001 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 230B 30mS Off, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 1.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 0, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2024-11-12,10:06:07,001,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 21\r\nStatus: Terminated, QOS: Faulted, EngineId: 10\r\nStart-Time: 2024-11-04,10:06:07, End-Time: 2024-11-04,10:07:07\r\nDuration: 00:02:00\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.111:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG729A 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 4.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1243, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 1, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 0, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 1.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2025-12-12,10:07:27,002,00002": "\r\nshow rtp-stat detailed 00002\r\n\r\nSession-ID: 11\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:07:27, End-Time: -\r\nDuration: - \r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.112:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (2)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 123, Loss 0.3% #0, Avg-Loss 0.3%, RTT 200mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 2, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 2.0% #0, Avg-Loss 1.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2025-12-21,10:08:07,003,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 1\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:08:07, End-Time: 2025-12-14,10:08:22\r\nDuration: 00:12:20\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.113:2056 SSRC 1653399062\r\nRemote-Address: 192.168.110.111:35001 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 230B 30mS Off, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 1.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 0, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2024-11-13,10:06:07,001,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 21\r\nStatus: Terminated, QOS: Faulted, EngineId: 10\r\nStart-Time: 2024-11-04,10:06:07, End-Time: 2024-11-04,10:07:07\r\nDuration: 00:02:00\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.111:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG729A 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 4.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1243, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 1, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 0, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 1.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2025-12-13,10:07:27,002,00002": "\r\nshow rtp-stat detailed 00002\r\n\r\nSession-ID: 11\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:07:27, End-Time: -\r\nDuration: - \r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.112:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (2)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 123, Loss 0.3% #0, Avg-Loss 0.3%, RTT 200mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 2, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 2.0% #0, Avg-Loss 1.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2025-12-13,10:08:07,003,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 1\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:08:07, End-Time: 2025-12-14,10:08:22\r\nDuration: 00:12:20\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.113:2056 SSRC 1653399062\r\nRemote-Address: 192.168.110.111:35001 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 230B 30mS Off, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 1.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 0, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2024-11-13,10:06:07,001,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 21\r\nStatus: Terminated, QOS: Faulted, EngineId: 10\r\nStart-Time: 2024-11-04,10:06:07, End-Time: 2024-11-04,10:07:07\r\nDuration: 00:02:00\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.111:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG729A 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 4.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1243, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 1, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 0, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 1.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2025-12-15,10:07:27,002,00002": "\r\nshow rtp-stat detailed 00002\r\n\r\nSession-ID: 11\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:07:27, End-Time: -\r\nDuration: - \r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.112:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (2)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 123, Loss 0.3% #0, Avg-Loss 0.3%, RTT 200mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 2, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 2.0% #0, Avg-Loss 1.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2025-12-15,10:08:07,003,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 1\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:08:07, End-Time: 2025-12-14,10:08:22\r\nDuration: 00:12:20\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.113:2056 SSRC 1653399062\r\nRemote-Address: 192.168.110.111:35001 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 230B 30mS Off, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 1.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 0, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2024-11-15,10:06:07,001,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 21\r\nStatus: Terminated, QOS: Faulted, EngineId: 10\r\nStart-Time: 2024-11-04,10:06:07, End-Time: 2024-11-04,10:07:07\r\nDuration: 00:02:00\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.111:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG729A 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 4.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1243, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 1, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 0, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 1.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2025-12-30,10:07:27,002,00002": "\r\nshow rtp-stat detailed 00002\r\n\r\nSession-ID: 11\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:07:27, End-Time: -\r\nDuration: - \r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.112:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (2)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 123, Loss 0.3% #0, Avg-Loss 0.3%, RTT 200mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 2, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 2.0% #0, Avg-Loss 1.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2025-12-29,16:08:07,003,00001": "\r\nshow rtp-stat detailed 00001\r\n\r\nSession-ID: 1\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-14,10:08:07, End-Time: 2025-12-14,10:08:22\r\nDuration: 00:12:20\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.113:2056 SSRC 1653399062\r\nRemote-Address: 192.168.110.111:35001 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 230B 30mS Off, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 1.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 0, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 0.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2024-11-29,07:06:07,005,00221": "\r\nshow rtp-stat detailed 00221\r\n\r\nSession-ID: 21\r\nStatus: Terminated, QOS: Faulted, EngineId: 10\r\nStart-Time: 2024-11-04,10:06:07, End-Time: 2024-11-04,10:07:07\r\nDuration: 00:02:00\r\nCName: gwp@10.10.48.58\r\nPhone: \r\nLocal-Address: 192.168.110.111:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (0)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG729A 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 4.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 1243, Loss 0.3% #0, Avg-Loss 0.3%, RTT 0mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 0, Seq-Fall 1, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 0, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 1.0% #0, Avg-Loss 0.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",
            "2025-12-30,10:07:27,006,02332": "\r\nshow rtp-stat detailed 02332\r\n\r\nSession-ID: 11\r\nStatus: Active, QOS: Ok, EngineId: 10\r\nStart-Time: 2025-12-30,10:07:27, End-Time: 2025-12-30,10:07:37\r\nDuration: 00:00:10 \r\nCName: gwp@10.10.48.69\r\nPhone: \r\nLocal-Address: 192.168.110.112:2052 SSRC 1653399062\r\nRemote-Address: 10.10.48.192:35000 SSRC 2704961869 (2)\r\nSamples: 0 (5 sec)\r\n\r\nCodec:\r\nG711U 200B 20mS srtpAesCm128HmacSha180, Silence-suppression(Tx/Rx) Disabled/Disabled, Play-Time 334.720sec, Loss 0.8% #0, Avg-Loss 0.8%, RTT 0mS #0, Avg-RTT 0mS, JBuf-under/overruns 0.0%/0.0%, Jbuf-Delay 22mS, Max-Jbuf-Delay 22mS\r\n\r\nReceived-RTP:\r\nPackets 123, Loss 0.3% #0, Avg-Loss 0.3%, RTT 200mS #0, Avg-RTT 0mS, Jitter 2mS #0, Avg-Jitter 2mS, TTL(last/min/max) 56/56/56, Duplicates 2, Seq-Fall 0, DSCP 0, L2Pri 0, RTCP 0, Flow-Label 2\r\n\r\nTransmitted-RTP:\r\nVLAN 0, DSCP 46, L2Pri 0, RTCP 10, Flow-Label 0\r\n\r\nRemote-Statistics:\r\nLoss 2.0% #0, Avg-Loss 1.0%, Jitter 0mS #0, Avg-Jitter 0mS\r\n\r\nEcho-Cancellation:\r\nLoss 0dB #2, Len 0mS\r\n\r\nRSVP:\r\nStatus Unused, Failures 0\n",

        }
        
        for global_id, value in d.items():
                rtpdetailed = parse_rtpstat(global_id, value)
                RTPs.put({global_id: rtpdetailed})

        PCAPs = MemoryStorage({
            '2025_12_19@22_05_45_002':
            Capture(remote_ip='10.44.244.51', filename='2025_12_19@22_05_45_002', file_size=6539, received_timestamp=datetime(2025, 12, 20, 11, 9, 19, 550802), capinfos='File name:           uploads/2025_12_19@22_05_45_002\nFile type:           Wireshark/tcpdump/... - pcap\nFile encapsulation:  Ethernet\nFile timestamp precision:  microseconds (6)\nPacket size limit:   file hdr: 4096 bytes\nNumber of packets:   4,565\nFile size:           1,048 kB\nData size:           975 kB\nCapture duration:    22.065001 seconds\nFirst packet time:   2025-11-27 08:52:08.265000\nLast packet time:    2025-11-27 08:52:30.330001\nData byte rate:      44 kBps\nData bit rate:       353 kbps\nAverage packet size: 213.69 bytes\nAverage packet rate: 206 packets/s\nSHA256:              41f4feebdc3012525069ee9cf471d93e980779cfb700269dccf9568b7b8cc598\nRIPEMD160:           365e85e95f27a660e8fc616c917b59b1d7e13544\nSHA1:                21a9247795c835ed5c62aaa9cde95bffc2031908\nStrict time order:   False\nNumber of interfaces in file: 1\nInterface #0 info:\n                     Encapsulation = Ethernet (1 - ether)\n                     Capture length = 4096\n                     Time precision = microseconds (6)\n                     Time ticks per second = 1000000\n                     Number of stat entries = 0\n                     Number of packets = 4565', rtpinfos='========================= RTP Streams ========================\n    Src IP addr  Port    Dest IP addr  Port       SSRC          Payload  Pkts         Lost   Max Delta(ms)  Max Jitter(ms) Mean Jitter(ms) Problems?\n   10.188.244.1  2070    10.10.48.192 37184 0xCDE34A07 ITU-T G.711 PCMU  1103     0 (0.0%)           25.00            2.11            0.59 \n   10.10.48.192 37184    10.188.244.1  2070 0x65F27A72 ITU-T G.711 PCMU  1104     0 (0.0%)           25.00            3.65            1.98 \n  10.188.244.38  2048    10.188.244.1  2060 0xA1F5310D ITU-T G.711 PCMU  1104     0 (0.0%)           30.00            1.32            0.15 \n   10.188.244.1  2060   10.188.244.38  2048 0xEFC73AE0 ITU-T G.711 PCMU  1104     0 (0.0%)           25.00            2.08            0.63 \n==============================================================', gw_number='004'),
            '2025_12_20@13_12_33_003':
            Capture(remote_ip='10.10.48.58', filename='2025_12_20@13_12_33_003', file_size=6539, received_timestamp=datetime(2025, 12, 20, 11, 9, 19, 319314), capinfos='File name:           uploads/2025_12_20@13_12_33_003\nFile type:           Wireshark/... - pcapng\nFile encapsulation:  Ethernet\nFile timestamp precision:  nanoseconds (9)\nPacket size limit:   file hdr: (not set)\nNumber of packets:   27 k\nFile size:           7,103 kB\nData size:           6,174 kB\nCapture duration:    199.353739380 second\nFirst packet time:   2025-11-26 11:24:14.684518725\nLast packet time:    2025-11-26 11:27:34.038258105\nData byte rate:      30 kBps\nData bit rate:       247 kbps\nAverage packet size: 225.95 bytes\nAverage packet rate: 137 packets/s\nSHA256:              0e7ff09bcbe5654e3c4eac48daae5d4bc3bc76350e9550fb89e4970ee4c4d4a8\nRIPEMD160:           4e7a1d5f0ada9bcfbc9208438aea108f656ece5d\nSHA1:                f9d5aed405f9702d4d8c16fb0546a6df7fb7e357\nStrict time order:   False\nCapture oper-sys:    64-bit Windows 11 (25H2), build 26200\nCapture application: Mergecap (Wireshark) 4.6.1 (v4.6.1-0-g291c718be4fe)\nCapture comment:     File created by merging:  File1: dc1voipsbc1_03439_20251126112414  File2: dc1voipsbc1_03440_20251126112449  File3: dc1voipsbc1_03441_20251126112520  File4: dc1voipsbc1_03442_20251126112554  File5: dc1voipsbc1_03443_20251126112630  File6: dc1voipsbc1_03444_20251126112703  \nNumber of interfaces in file: 2\nInterface #0 info:\n                     Name = A1\n                     Encapsulation = Ethernet (1 - ether)\n                     Capture length = 262144\n                     Time precision = nanoseconds (9)\n                     Time ticks per second = 1000000000\n                     Time resolution = 0x09\n                     Operating system = Linux 4.18.0-553.81.1.el8_10.x86_64\n                     Number of stat entries = 0\n                     Number of packets = 13403\nInterface #1 info:\n                     Name = B2\n                     Encapsulation = Ethernet (1 - ether)\n                     Capture length = 262144\n                     Time precision = nanoseconds (9)\n                     Time ticks per second = 1000000000\n                     Time resolution = 0x09\n                     Filter string = udp portrange 10000-40000 or port 5060\n                     BPF filter length = 0\n                     Operating system = Linux 4.18.0-553.81.1.el8_10.x86_64\n                     Number of stat entries = 0\n                     Number of packets = 13922', rtpinfos='========================= RTP Streams ========================\n    Src IP addr  Port    Dest IP addr  Port       SSRC          Payload  Pkts         Lost   Max Delta(ms)  Max Jitter(ms) Mean Jitter(ms) Problems?\n   10.234.255.5 36368      10.32.34.3 46750 0x2DC9D34B ITU-T G.711 PCMU  6618     0 (0.0%)          219.75            2.56            2.01 X\n     10.32.34.3 46750    10.234.255.5 36368 0x55063698 ITU-T G.711 PCMU  6624     0 (0.0%)          219.97            6.30            0.07 X\n162.248.168.235 49360     10.234.33.5 14344 0x2DC9D34B ITU-T G.711 PCMU  6620     0 (0.0%)           38.99            2.56            2.01 X\n    10.234.33.5 14344 162.248.168.235 49360 0x55063698 ITU-T G.711 PCMU  6624     0 (0.0%)           23.86            6.30            0.07 X\n     10.32.34.3 46750    10.234.255.5 38068 0x55063698 ITU-T G.711 PCMU    65     0 (0.0%)           20.26            0.09            0.06 \n    10.234.33.5 14344 162.248.168.235 46168 0x55063698 ITU-T G.711 PCMU    65     0 (0.0%)           20.26            0.09            0.06 \n   10.234.255.5 38068      10.32.34.3 46750 0x59A25729 ITU-T G.711 PCMU    68     0 (0.0%)           23.51            2.03            1.95 \n162.248.168.235 46168     10.234.33.5 14344 0x59A25729 ITU-T G.711 PCMU    68     0 (0.0%)           23.51            2.03            1.95 \n==============================================================', gw_number='001')
            
        })