# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""controller.py - per-terminal glue between VTE and Promptline

One Controller is attached to each Terminal. It feeds shell marks from VTE
into a ShellSession, and shows and accepts inline suggestions.
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import GLib, Gdk, Gtk, Vte

from ..signalman import Signalman
from ..util import dbg
from .. import promptline
from . import marks
from .ghost import GhostText
from .session import ShellSession
from .suggest import Suggester
from .suggest.history import shared_store

# Exit status the shells use for "command not found": not worth learning
NOT_FOUND = 127


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
        self.history = shared_store()
        self.suggester = Suggester(self.history)
        self.ghost = None
        self.suggestion = None      # (input it extends, suffix)
        self.refresh_id = None
        self.last_learned = None
        self.cnxids = Signalman()
        self.cnxids.new(self.vte, 'termprops-changed',
                        self.on_termprops_changed)
        self.cnxids.new(self.vte, 'cursor-moved', self.on_cursor_moved)
        self.cnxids.new(self.vte, 'contents-changed', self.schedule_refresh)
        self.cnxids.new(self.vte, 'selection-changed', self.schedule_refresh)
        self.cnxids.new(self.vte.get_vadjustment(), 'value-changed',
                        self.schedule_refresh)

    def wrap(self, vte):
        """Return the widget to pack in place of the VTE: the VTE with the
        suggestion layer over it"""
        overlay = Gtk.Overlay()
        overlay.add(vte)
        self.ghost = GhostText(vte, lambda: self.terminal.fgcolor_active)
        overlay.add_overlay(self.ghost)
        overlay.set_overlay_pass_through(self.ghost, True)
        overlay.show_all()
        return overlay

    def destroy(self):
        """Disconnect from the VTE"""
        self.cnxids.remove_all()
        if self.refresh_id is not None:
            GLib.source_remove(self.refresh_id)
            self.refresh_id = None

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
            if session.log:
                self.learn(session.log[-1])
        self.schedule_refresh()

    def learn(self, record):
        """Add a finished command to the suggestion history"""
        if record is self.last_learned:
            return
        self.last_learned = record
        dbg('promptline command %r exited %s with %d chars output' %
            (record.command, record.exit_status, len(record.output or '')))
        if record.private or record.exit_status == NOT_FOUND:
            return
        self.history.add(record.command, record.cwd, record.exit_status)

    def on_cursor_moved(self, _vte):
        self.session.note_cursor()
        self.schedule_refresh()

    def schedule_refresh(self, *_args):
        """Recompute the suggestion once the current batch of changes is in,
        before GTK redraws"""
        if self.ghost is not None and self.refresh_id is None:
            self.refresh_id = GLib.idle_add(self.refresh,
                                            priority=GLib.PRIORITY_HIGH_IDLE)

    def scrolled_back(self):
        adjustment = self.vte.get_vadjustment()
        return adjustment.get_value() + adjustment.get_page_size() < \
            adjustment.get_upper() - 0.5

    def refresh(self):
        """Show the best suggestion for what's typed, or nothing"""
        self.refresh_id = None
        suffix = None
        line = self.session.current_input()
        if (line is not None and line.at_end and
                promptline.enabled('autocomplete') and
                not self.vte.get_has_selection() and
                not self.scrolled_back()):
            suffix = self.suggester.suggest(line.text,
                                            self.terminal.get_cwd())
        if suffix:
            suffix = suffix.split('\n')[0]
            row, column = self.session.screen.cursor()
            room = self.vte.get_column_count() - column
            if self.session.right_prompt and row == self.session.anchor[0]:
                room -= len(self.session.right_prompt) + 1
            if room > 0:
                self.suggestion = (line.text, suffix)
                self.ghost.show_text(suffix[:room], row, column)
                return False
        self.suggestion = None
        self.ghost.clear()
        return False

    def on_keypress(self, event):
        """Accept the suggestion on Right/End (all of it) or Alt+Right (the
        next word). Returns True if the key was consumed."""
        if self.suggestion is None:
            return False
        modifiers = event.state & Gtk.accelerator_get_default_mod_mask()
        right = event.keyval in (Gdk.KEY_Right, Gdk.KEY_KP_Right)
        end = event.keyval in (Gdk.KEY_End, Gdk.KEY_KP_End)
        if (right or end) and modifiers == 0:
            whole = True
        elif right and modifiers == Gdk.ModifierType.MOD1_MASK:
            whole = False
        else:
            return False

        base, suffix = self.suggestion
        line = self.session.current_input()
        if line is None or not line.at_end or line.text != base:
            return False
        if not whole:
            stripped = suffix.lstrip(' ')
            word_end = stripped.find(' ')
            if word_end != -1:
                suffix = suffix[:len(suffix) - len(stripped) + word_end]
        self.suggestion = None
        self.ghost.clear()
        self.vte.feed_child(suffix.encode('utf-8'))
        return True
