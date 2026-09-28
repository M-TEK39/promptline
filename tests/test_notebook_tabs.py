# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""Tests for closing and splitting terminals that live in tabs"""

import pytest
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gtk

from promptlinelib.factory import Factory
from promptlinelib.terminator import Terminator


def pump():
    while Gtk.events_pending():
        Gtk.main_iteration()


@pytest.fixture
def notebook():
    """A window with two tabs, each holding one terminal"""
    terminator = Terminator()
    # Terminator is a Borg: other tests may have left fake terminals in it
    saved = terminator.terminals, terminator.windows
    terminator.terminals, terminator.windows = [], []
    maker = Factory()
    window = maker.make('Window')
    terminal = maker.make('Terminal')
    window.add(terminal)
    terminal.spawn_child()
    window.show_all()
    pump()
    terminal.key_new_tab()
    pump()
    notebook = window.get_child()
    assert maker.isinstance(notebook, 'Notebook')
    assert notebook.get_n_pages() == 2
    yield notebook
    window.destroy()
    pump()
    terminator.terminals, terminator.windows = saved


def test_shell_exit_in_a_tab_closes_the_tab(notebook):
    window = notebook.get_toplevel()
    notebook.get_nth_page(1).close()
    pump()
    assert Factory().isinstance(window.get_child(), 'Terminal')


def test_split_inside_a_tab(notebook):
    notebook.get_nth_page(1).key_split_vert()
    pump()
    assert Factory().isinstance(notebook.get_nth_page(1), 'Paned')


def test_tab_close_button_without_last_active_entry(notebook):
    window = notebook.get_toplevel()
    page = notebook.get_nth_page(1)
    notebook.last_active_term.pop(page, None)
    label = notebook.get_tab_label(page)
    notebook.closetab(label, label)
    pump()
    assert Factory().isinstance(window.get_child(), 'Terminal')
