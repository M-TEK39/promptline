# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""paths.py - complete the path being typed as the last argument

Like the shell's own Tab completion, a suggestion only extends the path as
far as it is unambiguous, so accepting it never picks the wrong file.

>>> import tempfile
>>> root = tempfile.mkdtemp()
>>> for name in ['projects', 'photos', 'notes.txt', '.hidden', 'my file']:
...     path = os.path.join(root, name)
...     os.mkdir(path) if '.' not in name else open(path, 'w').close()
>>> complete('ls pro', root)
'ls projects/'
>>> complete('ls p', root) is None       # projects or photos: ambiguous
True
>>> complete('cat no', root)
'cat notes.txt'
>>> complete('cd n', root) is None       # cd only wants directories
True
>>> complete('ls my', root)
'ls my\\\\ file/'
>>> complete('ls .hid', root)
'ls .hidden'
>>> complete('pro', root) is None        # first word is a command
True
>>> complete('ls ' + root + '/pho', '/')[len('ls ' + root):]
'/photos/'
"""

import os
import time

DIR_ONLY_COMMANDS = ('cd', 'pushd', 'rmdir')
CACHE_SECONDS = 2.0
SPECIAL = ' \'"\\$`!&;|<>()*?[]{}#~'

_cache = {}


def _listdir(directory):
    """(name, is_dir) pairs for a directory, briefly cached"""
    now = time.monotonic()
    cached = _cache.get(directory)
    if cached and now - cached[0] < CACHE_SECONDS:
        return cached[1]
    entries = []
    try:
        with os.scandir(directory) as scan:
            for entry in scan:
                try:
                    entries.append((entry.name, entry.is_dir()))
                except OSError:
                    pass
    except OSError:
        entries = []
    if len(_cache) > 64:
        _cache.clear()
    _cache[directory] = (now, entries)
    return entries


def _escape(name):
    return ''.join('\\' + c if c in SPECIAL else c for c in name)


def _unescape(word):
    out, escaped = [], False
    for char in word:
        if escaped or char != '\\':
            out.append(char)
            escaped = False
        else:
            escaped = True
    return ''.join(out)


def _last_word(line):
    """Split off the last unquoted, space-separated word. Returns None if
    the line ends inside quotes, which we don't try to complete."""
    start, escaped = 0, False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
        elif char == '\\':
            escaped = True
        elif char in '\'"':
            return None
        elif char == ' ':
            start = index + 1
    return line[:start], line[start:]


def complete(line, cwd):
    """Return line with its last word completed as a path, or None"""
    split = _last_word(line)
    if split is None or not cwd:
        return None
    head, word = split
    if not word or not head.strip():
        return None
    first = head.split()[0]
    dirs_only = first in DIR_ONLY_COMMANDS

    path = os.path.expanduser(_unescape(word))
    directory, partial = os.path.split(path)
    search = os.path.join(cwd, directory) if directory else cwd
    matches = [(name, is_dir) for name, is_dir in _listdir(search)
               if name.startswith(partial)
               and (partial.startswith('.') or not name.startswith('.'))
               and (is_dir or not dirs_only)]
    if not matches:
        return None

    common = os.path.commonprefix([name for name, _ in matches])
    if len(matches) == 1:
        name, is_dir = matches[0]
        addition = _escape(name[len(partial):]) + ('/' if is_dir else '')
    else:
        addition = _escape(common[len(partial):])
    if not addition:
        return None
    return line + addition
