# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""cli.py - the promptline-agent program: @agent's terminal front end

It runs in the user's terminal like any other command, so its output is
ordinary scrollback and Ctrl+C stops it.

>>> import tempfile
>>> store = ConversationStore('urn:uuid:test', directory=tempfile.mkdtemp())
>>> store.load()
[]
>>> store.save([{'role': 'user', 'content': 'hi'},
...             {'role': 'assistant', 'content': 'hello'}])
>>> [m['content'] for m in store.load()]
['hi', 'hello']
>>> trim_history([{'role': 'user', 'content': str(i)} for i in range(5)], 3)
[{'role': 'user', 'content': '2'}, {'role': 'user', 'content': '3'}, {'role': 'user', 'content': '4'}]
"""

import hashlib
import json
import math
import os
import shutil
import sys
import threading
import time

from . import read_request, runtime_dir, write_prefill
from .loop import Agent
from .prompts import system_prompt, user_message
from .tools import run_command
from ..providers import ProviderError, make_provider

CONVERSATION_TTL = 30 * 60
MAX_MESSAGES = 60
STORED_TOOL_OUTPUT = 4000

BOLD = '\033[1m'
DIM = '\033[2m'
ACCENT = '\033[36m'
RESET = '\033[0m'


def trim_history(messages, limit=MAX_MESSAGES):
    """Keep the most recent messages, starting at a user message so tool
    results are never separated from the call that produced them"""
    if len(messages) <= limit:
        return messages
    start = len(messages) - limit
    while start < len(messages) and messages[start].get('role') != 'user':
        start += 1
    return messages[start:]


class ConversationStore(object):
    """Follow-up questions in the same terminal continue the conversation,
    until it has been idle for CONVERSATION_TTL"""
    def __init__(self, terminal, directory=None):
        name = hashlib.sha256((terminal or 'none').encode()).hexdigest()[:16]
        self.path = os.path.join(directory or runtime_dir(),
                                 'conversation-%s.json' % name)

    def load(self):
        try:
            with open(self.path, encoding='utf-8') as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return []
        if time.time() - data.get('updated', 0) > CONVERSATION_TTL:
            return []
        return data.get('messages', [])

    def save(self, messages):
        stored = []
        for message in trim_history(messages):
            if message.get('role') == 'tool' and \
                    len(message.get('content') or '') > STORED_TOOL_OUTPUT:
                message = dict(message, content=message['content'][
                    :STORED_TOOL_OUTPUT] + ' [...]')
            stored.append(message)
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump({'updated': time.time(), 'messages': stored}, handle)


class TtyUI(object):
    """Talks to the user in the terminal"""
    SPINNER = '|/-\\'

    def __init__(self, out=None, tty=None):
        self.out = out or sys.stdout
        self.tty = tty if tty is not None else sys.stdin.isatty()

    def write(self, text):
        self.out.write(text)
        self.out.flush()

    def header(self, prompt_prefix, injected, query):
        """Replace the line the shell echoed (our launcher command) with
        what the user actually typed"""
        if not self.tty or prompt_prefix is None:
            return
        columns = shutil.get_terminal_size().columns
        rows = max(1, math.ceil((len(prompt_prefix) + len(injected)) /
                                max(1, columns)))
        self.write('\033[1A\r\033[2K' * rows + prompt_prefix + BOLD +
                   '@agent' + RESET + ' ' + query + '\n')

    def thinking(self, fn):
        result = {}

        def work():
            try:
                result['value'] = fn()
            except BaseException as ex:
                result['error'] = ex

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        frame = 0
        while thread.is_alive():
            if self.tty:
                self.write('\r%s%s thinking%s' % (
                    DIM, self.SPINNER[frame % len(self.SPINNER)], RESET))
            frame += 1
            thread.join(0.12)
        if self.tty:
            self.write('\r\033[K')
        if 'error' in result:
            raise result['error']
        return result['value']

    def say(self, text):
        self.write(text + '\n\n')

    def note(self, text):
        self.write(DIM + text + RESET + '\n')

    def error(self, text):
        self.write(BOLD + 'promptline-agent: ' + RESET + text + '\n')

    def approve(self, command, reason):
        if reason:
            self.write(DIM + reason + RESET + '\n')
        self.write('  ' + BOLD + '$ ' + command + RESET + '\n')
        if not self.tty:
            self.note('Not running it: no terminal to ask for approval.')
            return 'cancel', command
        while True:
            self.write('  ' + ACCENT + '[a]' + RESET + 'pprove  ' + ACCENT +
                       '[e]' + RESET + 'dit  ' + ACCENT + '[c]' + RESET +
                       'ancel ')
            key = self.read_key().lower()
            if key in ('a', 'y'):
                self.write('approved\n')
                return 'approve', command
            if key in ('c', 'n', 'q', '\x1b'):
                self.write('cancelled\n\n')
                return 'cancel', command
            if key == 'e':
                self.write('edit\n')
                edited = self.edit(command)
                if not edited:
                    self.write('  cancelled\n\n')
                    return 'cancel', command
                return 'approve', edited
            self.write('\r\033[K')

    def read_key(self):
        """One keypress, without waiting for Enter (Ctrl+C still works)"""
        import termios
        import tty
        fd = sys.stdin.fileno()
        saved = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            return os.read(fd, 1).decode('utf-8', 'replace')
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved)

    def edit(self, command):
        """Let the user edit the command line, starting from command"""
        import readline
        readline.set_startup_hook(lambda: readline.insert_text(command))
        try:
            return input('  $ ').strip()
        except EOFError:
            return ''
        finally:
            readline.set_startup_hook()

    def running(self, command):
        pass

    def finished(self, status):
        if status:
            self.note('exit %d' % status)
        self.write('\n')


def main(argv=None):
    argv = sys.argv if argv is None else argv
    if len(argv) != 2:
        sys.stderr.write('usage: promptline-agent REQUEST\n'
                         'Type "@agent <question>" at a Promptline prompt '
                         'instead of running this directly.\n')
        return 2
    path = argv[1]
    try:
        request = read_request(path)
    except (OSError, ValueError):
        sys.stderr.write('promptline-agent: request %s not found\n' % path)
        return 2

    ui = TtyUI()
    token = os.path.basename(path)[:-len('.json')]
    query = request.get('query', '')
    ui.header(request.get('prompt_prefix'), ' _promptline_agent ' + token,
              query)
    if not query:
        ui.note('Usage: @agent <question or task>, e.g. '
                '@agent why did that command fail?')
        return 0

    provider = make_provider('agent', request.get('settings'))
    if provider is None:
        ui.error('no API key found. Set OPENAI_API_KEY for Terminator, or '
                 'point promptline_api_key_file in ~/.config/terminator/'
                 'config at a file containing the key.')
        return 1

    cwd = request.get('cwd') or os.getcwd()
    shell = request.get('shell') or os.environ.get('SHELL', '/bin/sh')
    out = sys.stdout.buffer

    def executor(command):
        sys.stdout.flush()
        return run_command(command, cwd, shell, out)

    store = ConversationStore(request.get('terminal'))
    history = store.load()
    agent = Agent(provider, ui, executor, messages=[
        {'role': 'system', 'content': system_prompt(shell)}] + history)
    try:
        agent.run(user_message(request))
    except KeyboardInterrupt:
        ui.write('\n')
        ui.note('Interrupted.')
        return 130
    except ProviderError as ex:
        ui.error(str(ex))
        return 1
    store.save(agent.messages[1:])
    if agent.prefill:
        write_prefill(path, agent.prefill)
    return 0
