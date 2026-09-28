# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""marks.py - the shell-to-terminal protocol used by Promptline

The shell integration scripts in shell/ report shell state through VTE
terminal properties, set with the escape sequence

    ESC ] 666 ; vte.ext.promptline.<name>=<value> ESC \\

VTE only delivers these if they end with ST (not BEL), and cuts values at
';', so command text is base64 encoded. Several marks can arrive in one
'termprops-changed' batch, so they are handled in ORDER.

>>> decode_command('Z2l0IHN0YXR1cw==')
'git status'
>>> decode_command('-') is None
True
>>> decode_command('%%%') is None
True
>>> parse_int('3'), parse_int(''), parse_int('x', 1)
(3, None, 1)
"""

import base64
import binascii

import gi
gi.require_version('Vte', '2.91')
from gi.repository import Vte

PREFIX = 'vte.ext.promptline.'

# A command is about to run. Value: base64 command text, or '-' when the
# shell can't tell us (the terminal then reads it off the screen).
EXEC = PREFIX + 'exec'
# The last command finished. Value: its exit status.
DONE = PREFIX + 'done'
# A prompt is being drawn. Value: how many rows the prompt occupies.
PROMPT = PREFIX + 'prompt'
# The prompt is drawn; the cursor is where the user's input starts.
INPUT = PREFIX + 'input'
# How many characters of the line being edited follow the cursor (zsh, on
# every redraw). Text on screen past those isn't input: plugins such as
# zsh-autosuggestions draw their suggestion there.
AFTER = PREFIX + 'after'

ORDER = (EXEC, DONE, PROMPT, INPUT, AFTER)


def _install():
    """Register our termprops with VTE. Must run before any Vte.Terminal
    exists, which is why it happens at import time."""
    if not hasattr(Vte, 'install_termprop'):
        return False
    for name in ORDER:
        if Vte.install_termprop(name, Vte.PropertyType.STRING,
                                Vte.PropertyFlags.EPHEMERAL) < 0:
            return False
    return True


INSTALLED = _install()


def decode_command(value):
    """Decode an EXEC value, or return None if the shell didn't send one"""
    if not value or value == '-':
        return None
    try:
        return base64.b64decode(value, validate=True).decode('utf-8',
                                                             'replace')
    except (binascii.Error, ValueError):
        return None


def parse_int(value, default=None):
    """Parse an integer mark value"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
