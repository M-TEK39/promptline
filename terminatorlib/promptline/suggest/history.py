# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""history.py - command history for inline suggestions

Commands come from the user's existing shell history files (read-only) and
from Promptline's own log, which also remembers where each command ran and
whether it worked. Suggestions favour commands that are frequent, recent,
were run in the current directory, and succeeded.

>>> store = HistoryStore(path=None)
>>> for cmd, cwd, status in [('git status', '/a', 0), ('git stash', '/b', 0),
...                          ('git status', '/a', 0), ('git stsh', '/a', 1)]:
...     store.add(cmd, cwd, status, persist=False)
>>> store.best('git st', cwd='/a')
'git status'
>>> store.best('git sta', cwd='/b')
'git stash'
>>> store.best('git status') is None
True
>>> store.best('') is None
True
>>> list(parse_zsh_history(b': 1700000000:0;ls -la\\n: 1700000001:0;echo a\\\\\\nb\\nplain\\n'))
[('ls -la', 1700000000.0), ('echo a\\nb', 1700000001.0), ('plain', None)]
>>> list(parse_bash_history('#1700000000\\nls\\ncd /tmp\\n'))
[('ls', 1700000000.0), ('cd /tmp', None)]
"""

import bisect
import json
import math
import os
import threading
import time

from gi.repository import GLib

from ...util import dbg, err

MAX_ENTRIES = 20000
MAX_CWDS = 8


class Entry(object):
    """What we know about one distinct command line"""
    __slots__ = ('count', 'last', 'cwds', 'last_status')

    def __init__(self):
        self.count = 0
        self.last = 0.0
        self.cwds = []
        self.last_status = None

    def score(self, cwd, now):
        age_days = max(0.0, now - self.last) / 86400.0
        score = (1.0 + math.log(self.count)) * (0.3 + 1.0 / (1.0 + age_days))
        if cwd is not None and cwd in self.cwds:
            score *= 2.0
        if self.last_status not in (None, 0):
            score *= 0.3
        return score


class HistoryStore(object):
    """Distinct commands, kept sorted for fast prefix lookup"""
    def __init__(self, path=None):
        self.path = path
        self.entries = {}
        self.sorted = []
        self.lock = threading.Lock()

    def add(self, command, cwd=None, status=None, when=None, persist=True):
        """Record that command ran"""
        if not command or '\n' in command:
            return
        when = time.time() if when is None else when
        with self.lock:
            entry = self.entries.get(command)
            if entry is None:
                entry = self.entries[command] = Entry()
                bisect.insort(self.sorted, command)
            entry.count += 1
            if when >= entry.last:
                entry.last = when
                if status is not None:
                    entry.last_status = status
            if cwd and cwd not in entry.cwds:
                entry.cwds.append(cwd)
                del entry.cwds[:-MAX_CWDS]
        if persist and self.path:
            self._append(command, cwd, status, when)

    def best(self, prefix, cwd=None, now=None):
        """Return the best command that extends prefix, or None"""
        if not prefix:
            return None
        now = time.time() if now is None else now
        best, best_score = None, 0.0
        with self.lock:
            start = bisect.bisect_right(self.sorted, prefix)
            for command in self.sorted[start:]:
                if not command.startswith(prefix):
                    break
                score = self.entries[command].score(cwd, now)
                if score > best_score:
                    best, best_score = command, score
        return best

    def load(self, shell_histories=True):
        """Read shell history files, then our own log (which wins on
        metadata because it is read last)"""
        if shell_histories:
            for command, when in read_shell_histories():
                self.add(command, when=when, persist=False)
        if self.path and os.path.exists(self.path):
            try:
                with open(self.path, encoding='utf-8',
                          errors='replace') as handle:
                    for line in handle:
                        try:
                            item = json.loads(line)
                        except ValueError:
                            continue
                        self.add(item.get('command'), item.get('cwd'),
                                 item.get('status'), item.get('time'),
                                 persist=False)
            except OSError as ex:
                err('promptline: unable to read %s: %s' % (self.path, ex))
        dbg('promptline history: %d distinct commands' % len(self.sorted))

    def _append(self, command, cwd, status, when):
        line = json.dumps({'command': command, 'cwd': cwd, 'status': status,
                           'time': when}) + '\n'
        try:
            os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT,
                         0o600)
            with os.fdopen(fd, 'a', encoding='utf-8') as handle:
                handle.write(line)
        except OSError as ex:
            err('promptline: unable to write %s: %s' % (self.path, ex))


def parse_bash_history(text):
    """Yield (command, time or None) from ~/.bash_history contents"""
    when = None
    for line in text.splitlines():
        if line.startswith('#') and line[1:].isdigit():
            when = float(line[1:])
            continue
        if line:
            yield line, when
        when = None


def _unmetafy(data):
    """zsh stores bytes >= 0x83 as 0x83 followed by the byte XOR 32"""
    if b'\x83' not in data:
        return data
    out = bytearray()
    meta = False
    for byte in data:
        if meta:
            out.append(byte ^ 32)
            meta = False
        elif byte == 0x83:
            meta = True
        else:
            out.append(byte)
    return bytes(out)


def parse_zsh_history(data):
    """Yield (command, time or None) from ~/.zsh_history bytes"""
    lines = _unmetafy(data).decode('utf-8', 'replace').split('\n')
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        # A trailing backslash continues a multi-line command
        while line.endswith('\\') and index < len(lines):
            line = line[:-1] + '\n' + lines[index]
            index += 1
        if not line:
            continue
        when = None
        if line.startswith(': ') and ';' in line:
            meta, line = line[2:].split(';', 1)
            try:
                when = float(meta.split(':')[0])
            except ValueError:
                pass
        yield line, when


def read_shell_histories():
    """Yield (command, time) from the user's bash and zsh history files, in
    file order, oldest first. Undated entries get a time just before the
    file's modification time so that file order still means recency."""
    home = os.path.expanduser('~')
    sources = [(os.path.join(home, '.bash_history'), False),
               (os.path.join(home, '.zsh_history'), True)]
    for path, is_zsh in sources:
        try:
            with open(path, 'rb') as handle:
                data = handle.read()
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        items = list(parse_zsh_history(data) if is_zsh else
                     parse_bash_history(data.decode('utf-8', 'replace')))
        items = items[-MAX_ENTRIES:]
        total = len(items)
        for index, (command, when) in enumerate(items):
            yield command, when if when else mtime - (total - index)


_SHARED = None


def shared_store():
    """The HistoryStore shared by all terminals, loaded in the background"""
    global _SHARED
    if _SHARED is None:
        path = os.path.join(GLib.get_user_data_dir(), 'promptline',
                            'history.jsonl')
        _SHARED = HistoryStore(path)
        threading.Thread(target=_SHARED.load, name='promptline-history',
                         daemon=True).start()
    return _SHARED
