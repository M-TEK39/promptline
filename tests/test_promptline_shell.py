#!/usr/bin/env python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""End-to-end tests for Promptline's shell integration: a real shell in a
real VTE, reporting marks that a Controller turns into a command log."""

import os
import shutil
import time

import pytest
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import GLib, Gtk, Vte

from terminatorlib.promptline import marks, shellint
from terminatorlib.promptline.controller import Controller

pytestmark = pytest.mark.skipif(not marks.INSTALLED,
                                reason='VTE too old for termprops')


class FakeTerminal(object):
    """Just enough of terminatorlib.terminal.Terminal for a Controller"""
    def __init__(self):
        self.vte = Vte.Terminal()
        self.window = Gtk.Window()
        self.window.add(self.vte)
        self.window.show_all()

    def get_cwd(self):
        uri = self.vte.ref_termprop_uri(Vte.TERMPROP_CURRENT_DIRECTORY_URI)
        return GLib.filename_from_uri(uri.to_string())[0] if uri else None


def wait_for(predicate, timeout=10):
    """Run the main loop until predicate() is true"""
    deadline = time.monotonic() + timeout
    context = GLib.MainContext.default()
    while not predicate():
        if time.monotonic() > deadline:
            return False
        context.iteration(False)
        time.sleep(0.005)
    return True


def start_shell(shell, home, environ):
    terminal = FakeTerminal()
    controller = Controller(terminal)
    argv, envv = shellint.inject(shell, [shell], ['HOME=%s' % home,
                                                  'TERM=xterm-256color'],
                                 environ=environ)
    terminal.vte.spawn_sync(Vte.PtyFlags.DEFAULT, home, [shell] + argv,
                            envv, GLib.SpawnFlags.FILE_AND_ARGV_ZERO,
                            None, None, None)
    session = controller.session
    assert wait_for(lambda: session.state == session.PROMPT), \
        'shell never reported a prompt'
    return terminal, session


def run(terminal, session, command):
    count = len(session.log)
    terminal.vte.feed_child((command + '\n').encode())
    assert wait_for(lambda: len(session.log) > count and
                    session.state == session.PROMPT), \
        'no record for %r' % command
    return session.log[-1]


@pytest.fixture
def home(tmp_path):
    (tmp_path / 'sub dir').mkdir()
    (tmp_path / 'zdot').mkdir()
    (tmp_path / 'zdot' / '.zshrc').write_text("PS1='%~ %# '\n")
    (tmp_path / '.bashrc').write_text("PS1='\\w \\$ '\n")
    return tmp_path


SHELLS = [s for s in ('bash', 'zsh') if shutil.which(s)]


@pytest.mark.parametrize('name', SHELLS)
def test_command_log(name, home):
    environ = {'ZDOTDIR': str(home / 'zdot')}
    terminal, session = start_shell(shutil.which(name), str(home), environ)

    record = run(terminal, session, "echo \"it's; fine\"")
    assert record.command == "echo \"it's; fine\""
    assert record.exit_status == 0
    assert record.output == "it's; fine"
    assert record.cwd == str(home)

    record = run(terminal, session, 'printf "a\\nb\\n"; false')
    assert record.exit_status == 1
    assert record.output == 'a\nb'

    record = run(terminal, session, "cd 'sub dir'")
    record = run(terminal, session, 'pwd')
    assert record.cwd == str(home / 'sub dir')
    assert record.output == str(home / 'sub dir')


@pytest.mark.parametrize('name', SHELLS)
def test_current_input(name, home):
    environ = {'ZDOTDIR': str(home / 'zdot')}
    terminal, session = start_shell(shutil.which(name), str(home), environ)

    terminal.vte.feed_child(b'git che')
    assert wait_for(lambda: session.current_input() is not None and
                    session.current_input().text == 'git che')
    assert session.current_input().at_end

    # Cursor moved left: input is known but we're no longer at its end
    terminal.vte.feed_child(b'\x1b[D')
    assert wait_for(lambda: not session.current_input().at_end)
