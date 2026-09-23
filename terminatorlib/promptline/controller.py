# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""controller.py - per-terminal glue between VTE and Promptline

One Controller is attached to each Terminal. It feeds shell marks from VTE
into a ShellSession; later phases hang autocomplete and the agent off it.
"""

import gi
gi.require_version('Vte', '2.91')
from gi.repository import Vte

from ..signalman import Signalman
from ..util import dbg
from . import marks
from .session import ShellSession


class VteScreen(object):
    """The screen interface ShellSession expects, backed by a Vte.Terminal"""
    def __init__(self, vte):
        self.vte = vte

    def cursor(self):
        column, row = self.vte.get_cursor_position()
        return (row, column)

    def columns(self):
        return self.vte.get_column_count()

    def text(self, row0, col0, row1, col1):
        text = self.vte.get_text_range_format(Vte.Format.TEXT, row0, col0,
                                              row1, col1)[0]
        return text or ''


class Controller(object):
    """Promptline state for one Terminal"""
    def __init__(self, terminal):
        self.terminal = terminal
        self.vte = terminal.vte
        self.session = ShellSession(VteScreen(self.vte))
        self.cnxids = Signalman()
        self.cnxids.new(self.vte, 'termprops-changed',
                        self.on_termprops_changed)
        self.cnxids.new(self.vte, 'cursor-moved', self.on_cursor_moved)

    def destroy(self):
        """Disconnect from the VTE"""
        self.cnxids.remove_all()

    def on_termprops_changed(self, vte, props, _count):
        """Collect our marks from this batch and apply them in order"""
        values = {}
        for prop in props:
            name = Vte.query_termprop_by_id(prop)[1]
            if name.startswith(marks.PREFIX):
                values[name] = vte.get_termprop_string_by_id(prop)[0]
        for name in marks.ORDER:
            if name in values:
                self.handle_mark(name, values[name])
        return False

    def handle_mark(self, name, value):
        """Apply one shell mark to the session"""
        dbg('promptline mark %s=%r' % (name[len(marks.PREFIX):], value))
        session = self.session
        if name == marks.EXEC:
            session.on_exec(marks.decode_command(value),
                            self.terminal.get_cwd())
        elif name == marks.DONE:
            session.on_done(marks.parse_int(value))
        elif name == marks.PROMPT:
            session.on_prompt(marks.parse_int(value, 1))
        elif name == marks.INPUT:
            session.on_input()
            if session.log and session.log[-1].finished:
                record = session.log[-1]
                dbg('promptline command %r exited %s with %d chars output' %
                    (record.command, record.exit_status,
                     len(record.output or '')))

    def on_cursor_moved(self, _vte):
        self.session.note_cursor()
