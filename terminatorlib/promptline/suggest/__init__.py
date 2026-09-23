# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""suggest - fast, local inline suggestions

Suggester.suggest() returns the text to show after the cursor, or None.
Everything here is local and synchronous; it runs on every keystroke.

>>> from .history import HistoryStore
>>> store = HistoryStore()
>>> store.add('git checkout main', '/src', 0, persist=False)
>>> suggester = Suggester(store)
>>> suggester.suggest('git che', '/src')
'ckout main'
>>> suggester.suggest('git checkout main', '/src') is None
True
>>> suggester.suggest('   ', '/src') is None
True
"""

from . import paths


class Suggester(object):
    """Combines history and path completion"""
    def __init__(self, store):
        self.store = store

    def suggest(self, line, cwd):
        """Return the suffix to suggest after line, or None"""
        if not line.strip():
            return None
        candidate = self.store.best(line, cwd)
        if candidate is None:
            candidate = paths.complete(line, cwd)
        if candidate is None or not candidate.startswith(line):
            return None
        return candidate[len(line):] or None
