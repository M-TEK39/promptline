# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""promptline - inline intelligence for Terminator terminals

Everything Promptline adds lives in this package. The rest of Terminator
only calls the small entry points below, so with Promptline disabled (or on
a VTE too old to support it) the terminal behaves exactly like upstream.
"""

from ..config import Config


def available():
    """Return True if this VTE can deliver Promptline's shell marks"""
    # Imported here so the agent CLI can use this package without VTE
    from . import marks
    return marks.INSTALLED


def enabled(feature=None):
    """Return True if Promptline (and optionally one feature of it) is on

    feature is the suffix of a promptline_* config key, e.g.
    'shell_integration' or 'autocomplete'.
    """
    if not available():
        return False
    config = Config()
    if not config['promptline_enabled']:
        return False
    if feature is not None:
        return bool(config['promptline_' + feature])
    return True


def attach(terminal):
    """Return a Controller for a new Terminal, or None if Promptline is off"""
    if not enabled():
        return None
    from .controller import Controller
    return Controller(terminal)
