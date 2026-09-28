# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""ghost.py - dimmed suggestion text drawn after the cursor

The ghost is a transparent layer over the VTE widget. It never writes to the
terminal and never takes input; the terminal underneath is untouched.
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, PangoCairo

from ..util import err

try:
    gi.require_foreign('cairo')
    CAN_DRAW = True
except ImportError:
    CAN_DRAW = False

ALPHA = 0.45
_warned = False


class GhostText(Gtk.DrawingArea):
    """Draws a single line of text starting at a terminal cell"""
    def __init__(self, vte, color):
        Gtk.DrawingArea.__init__(self)
        self.vte = vte
        self.color = color      # callable returning a Gdk.RGBA
        self.text = None
        self.cell = None
        self.set_can_focus(False)
        self.set_has_window(False)
        if CAN_DRAW:
            self.connect('draw', self.on_draw)
        else:
            global _warned
            if not _warned:
                _warned = True
                err('promptline: suggestions cannot be drawn without '
                    'python3-gi-cairo (PyGObject cairo support)')

    def show_text(self, text, row, column):
        """Show text starting at the given absolute row and column"""
        if (text, (row, column)) != (self.text, self.cell):
            self.text, self.cell = text, (row, column)
            self.queue_draw()

    def clear(self):
        if self.text is not None:
            self.text = self.cell = None
            self.queue_draw()

    def on_draw(self, _widget, cairo):
        if not self.text:
            return False
        vte = self.vte
        char_width = vte.get_char_width()
        char_height = vte.get_char_height()
        padding = vte.get_style_context().get_padding(vte.get_state_flags())
        top = vte.get_vadjustment().get_value()
        row, column = self.cell

        font = vte.get_font().copy()
        font.set_size(int(font.get_size() * vte.get_font_scale()))
        layout = PangoCairo.create_layout(cairo)
        layout.set_font_description(font)
        layout.set_text('M', -1)
        text_height = layout.get_pixel_size()[1]

        rgba = self.color()
        cairo.set_source_rgba(rgba.red, rgba.green, rgba.blue, ALPHA)
        y = padding.top + (row - top) * char_height + \
            (char_height - text_height) / 2.0
        # One cell per character keeps us on VTE's grid whatever the
        # cell_width/cell_height settings
        for offset, char in enumerate(self.text):
            if char == ' ':
                continue
            layout.set_text(char, -1)
            cairo.move_to(padding.left + (column + offset) * char_width, y)
            PangoCairo.show_layout(cairo, layout)
        return False
