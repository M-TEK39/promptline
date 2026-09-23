# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""agent - @agent, the terminal agent the user invokes from their prompt

When the user presses Enter on a line starting with @agent, Terminator
writes a request (the question, a snapshot of the terminal's context and
the provider settings, never the API key) into a private runtime
directory, clears the line, and runs the `promptline-agent` program in the
same terminal. The shell integration defines `_promptline_agent TOKEN`,
which records the question in shell history and starts the program.

Files for a request TOKEN, all in runtime_dir() and readable only by the
user:
    TOKEN.json      the request, deleted by the agent once read
    TOKEN.query     the question, deleted by the shell once in history
    TOKEN.prefill   written by the agent: text to type at the next prompt

>>> import tempfile
>>> directory = tempfile.mkdtemp()
>>> token = write_request({'query': 'hi'}, 'hi', directory)
>>> sorted(os.listdir(directory)) == [token + '.json', token + '.query']
True
>>> read_request(request_path(token, directory))
{'query': 'hi'}
>>> os.path.exists(request_path(token, directory))
False
>>> parse_invocation('@agent why did that fail?')
'why did that fail?'
>>> parse_invocation('  @agent')
''
>>> parse_invocation('@agents') is None
True
"""

import json
import os
import re
import secrets
import shutil
import sys
import tempfile

INVOCATION = re.compile(r'^\s*@agent(?:\s+(.*))?$', re.DOTALL)


def parse_invocation(line):
    """Return the question if line invokes the agent, else None"""
    match = INVOCATION.match(line)
    if match is None:
        return None
    return (match.group(1) or '').strip()


def runtime_dir():
    """A directory only this user can read"""
    base = os.environ.get('XDG_RUNTIME_DIR')
    if not base or not os.path.isdir(base):
        base = os.path.join(tempfile.gettempdir(), 'promptline-%d' %
                            os.getuid())
    return os.path.join(base, 'promptline')


def _private_write(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        handle.write(text)


def request_path(token, directory=None):
    return os.path.join(directory or runtime_dir(), token + '.json')


def write_request(request, query, directory=None):
    """Store a request for the agent; returns its token"""
    directory = directory or runtime_dir()
    os.makedirs(directory, mode=0o700, exist_ok=True)
    token = secrets.token_hex(8)
    base = os.path.join(directory, token)
    _private_write(base + '.json', json.dumps(request))
    _private_write(base + '.query', query)
    return token


def read_request(path):
    """Load and delete a request"""
    with open(path, encoding='utf-8') as handle:
        request = json.load(handle)
    os.unlink(path)
    return request


def write_prefill(request_file, text):
    """Ask Terminator to type text at the user's next prompt"""
    _private_write(request_file[:-len('.json')] + '.prefill', text)


def take_prefill(token, directory=None):
    """Return and remove the text the agent left for the prompt, if any,
    and tidy up anything else left over from the request"""
    base = os.path.join(directory or runtime_dir(), token)
    text = None
    try:
        with open(base + '.prefill', encoding='utf-8') as handle:
            text = handle.read()
    except OSError:
        pass
    for suffix in ('.prefill', '.json', '.query'):
        try:
            os.unlink(base + suffix)
        except OSError:
            pass
    return text


def agent_program():
    """Path to the promptline-agent script: next to the running
    terminator script (source tree or install), or on PATH"""
    here = os.path.dirname(os.path.abspath(sys.argv[0] or ''))
    candidate = os.path.join(here, 'promptline-agent')
    if os.path.isfile(candidate):
        return candidate
    return shutil.which('promptline-agent')
