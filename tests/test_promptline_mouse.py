# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""The suggestion layer must not take the mouse from the terminal"""

import ctypes
import ctypes.util
import time

import pytest
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gdk, Gtk

from promptlinelib.factory import Factory
from promptlinelib.terminator import Terminator


def pump(seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration()
        time.sleep(0.01)


def xtest():
    """Real X pointer events, as a touchpad would send them"""
    if not type(Gdk.Display.get_default()).__name__.startswith('X11'):
        pytest.skip('needs an X11 display (run under xvfb-run)')
    if not ctypes.util.find_library('Xtst'):
        pytest.skip('needs libXtst')
    x11 = ctypes.CDLL(ctypes.util.find_library('X11'))
    xtst = ctypes.CDLL(ctypes.util.find_library('Xtst'))
    x11.XOpenDisplay.restype = ctypes.c_void_p
    display = ctypes.c_void_p(x11.XOpenDisplay(None))

    def click(x, y, button):
        xtst.XTestFakeMotionEvent(display, -1, x, y, 0)
        xtst.XTestFakeButtonEvent(display, button, 1, 0)
        xtst.XTestFakeButtonEvent(display, button, 0, 0)
        x11.XFlush(display)
    return click


@pytest.fixture
def terminal():
    terminator = Terminator()
    saved = terminator.terminals, terminator.windows
    terminator.terminals, terminator.windows = [], []
    maker = Factory()
    window = maker.make('Window')
    terminal = maker.make('Terminal')
    window.add(terminal)
    terminal.spawn_child()
    window.show_all()
    pump(1)
    yield terminal
    window.destroy()
    pump()
    terminator.terminals, terminator.windows = saved


@pytest.mark.parametrize('button', [1, 3, 5])    # select, menu, scroll
def test_mouse_reaches_the_terminal(terminal, button):
    click = xtest()
    assert terminal.promptline, 'the suggestion layer is what is tested'
    presses = []
    terminal.vte.connect('button-press-event',
                         lambda _vte, event: presses.append(event) and False)
    terminal.vte.connect('scroll-event',
                         lambda _vte, event: presses.append(event) and False)
    allocation = terminal.vte.get_allocation()
    left, top = terminal.vte.get_window().get_origin()[1:]
    click(left + allocation.width // 2, top + allocation.height // 2, button)
    pump(1)
    # Terminator takes the right-click itself and opens its menu
    menus = [window for window in Gtk.Window.list_toplevels()
             if isinstance(window.get_child(), Gtk.Menu)
             and window.get_visible()]
    for menu in menus:
        menu.get_child().popdown()
    assert presses or (button == 3 and menus)
