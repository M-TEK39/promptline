# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""llm.py - predict the command being typed, using a language model

The model sees what a person looking over your shoulder would: the
directory, the last few commands and how they ended, the end of the last
output, and what you've typed so far. Private commands (typed with a
leading space) are left out and obvious secrets are redacted.

>>> clean_prediction('git push --set-upstream origin main', 'git pu')
'git push --set-upstream origin main'
>>> clean_prediction('```bash\\n$ git status\\n```', '')
'git status'
>>> clean_prediction('`ls -la`', 'ls')
'ls -la'
>>> clean_prediction('cargo build', 'git pu') is None     # must extend input
True
>>> clean_prediction('git pu', 'git pu') is None          # nothing to add
True
>>> clean_prediction('', '') is None
True
>>> redact('curl -H "Authorization: Bearer abc.def" https://x')
'curl -H "Authorization: Bearer [redacted]" https://x'
>>> redact('export OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuv')
'export OPENAI_API_KEY=[redacted]'
>>> redact('mysql -u root --password=hunter2 db')
'mysql -u root --password=[redacted] db'
"""

import collections
import os
import platform
import re
import threading

from gi.repository import GLib

from ...util import dbg, err
from ..providers import ProviderError

RECENT_COMMANDS = 8
OUTPUT_TAIL = 1500
LISTING_ENTRIES = 40
MAX_COMMAND = 400

SYSTEM_PROMPT = (
    "You predict the shell command a user is about to run in their "
    "terminal. Reply with exactly one command line and nothing else: no "
    "explanation, no quotes, no code fences. If the user has started "
    "typing, your command must begin with exactly what they typed. Use "
    "the recent commands, their exit statuses and the last output to "
    "anticipate the next step (for example the fix for a command that "
    "just failed). Prefer commands and files that exist in this context. "
    "If you have no useful prediction, reply with nothing.")

_SECRETS = [
    (re.compile(r'(?i)\b(authorization:\s*(?:bearer|basic|token)\s+)\S+?(?=["\'\s]|$)'),
     r'\1[redacted]'),
    (re.compile(r'(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z0-9_]*=)\S+'),
     r'\1[redacted]'),
    (re.compile(r'(?i)(--?(?:password|passwd|token|secret|api-key)[= ])\S+'),
     r'\1[redacted]'),
    (re.compile(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|'
                r'xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})'),
     '[redacted]'),
]


def redact(text):
    """Blank out things that look like credentials"""
    for pattern, replacement in _SECRETS:
        text = pattern.sub(replacement, text)
    return text


def git_branch(cwd):
    """The current git branch, found without running git"""
    directory = cwd
    while directory:
        head = os.path.join(directory, '.git', 'HEAD')
        try:
            with open(head, encoding='utf-8') as handle:
                ref = handle.read().strip()
            return ref.rsplit('/', 1)[-1] if ref.startswith('ref:') \
                else ref[:12]
        except OSError:
            pass
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent
    return None


def listing(cwd):
    """A short listing of cwd, directories marked with /"""
    try:
        with os.scandir(cwd) as scan:
            names = sorted((entry.name + ('/' if entry.is_dir() else '')
                            for entry in scan
                            if not entry.name.startswith('.')),
                           key=str.lower)
    except OSError:
        return None
    if len(names) > LISTING_ENTRIES:
        names = names[:LISTING_ENTRIES] + ['... (%d more)' %
                                           (len(names) - LISTING_ENTRIES)]
    return ', '.join(names)


def build_messages(typed, cwd, records, shell=None):
    """Messages asking for a prediction. records are CommandRecords,
    oldest first."""
    shell = os.path.basename(shell or os.environ.get('SHELL', 'sh'))
    lines = ['Shell: %s on %s' % (shell, platform.system())]
    if cwd:
        branch = git_branch(cwd)
        lines.append('Directory: %s%s' % (cwd, ' (git branch %s)' % branch
                                          if branch else ''))
        contents = listing(cwd)
        if contents is not None:
            lines.append('Directory contents: %s' % (contents or '(empty)'))
    public = [record for record in records if not record.private]
    recent = public[-RECENT_COMMANDS:]
    if recent:
        lines.append('Recent commands, oldest first:')
        for record in recent:
            status = '' if record.exit_status is None else \
                ' [exit %s]' % record.exit_status
            where = '' if record.cwd == cwd or not record.cwd else \
                ' (in %s)' % record.cwd
            lines.append('$ %s%s%s' % (redact(record.command[:MAX_COMMAND]),
                                       where, status))
        last = recent[-1]
        if last.output:
            lines.append('Output of the last command (tail):')
            lines.append(redact(last.output[-OUTPUT_TAIL:]))
    if typed:
        lines.append('Typed so far: %s' % typed)
    else:
        lines.append('Nothing typed yet: predict the next command.')
    return [{'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': '\n'.join(lines)}]


def clean_prediction(reply, typed):
    """Turn a model reply into a full command line extending typed, or
    None if it isn't one"""
    text = (reply or '').strip()
    if text.startswith('```'):
        text = '\n'.join(line for line in text.split('\n')
                         if not line.startswith('```'))
    text = text.strip().split('\n')[0].strip()
    if len(text) > 1 and text[0] == text[-1] == '`':
        text = text[1:-1]
    if text.startswith('$ '):
        text = text[2:]
    if not text or len(text) > MAX_COMMAND:
        return None
    # Keep the user's exact spacing for the part they typed
    if not text.startswith(typed.lstrip()):
        return None
    text = typed + text[len(typed.lstrip()):]
    return text if len(text) > len(typed) else None


class Predictor(object):
    """Runs one prediction at a time in the background and remembers the
    results. Results are delivered on the GTK main loop."""
    CACHE_SIZE = 256

    def __init__(self, provider_factory):
        self.provider_factory = provider_factory
        self.provider = None
        self.disabled = False
        self.cache = collections.OrderedDict()
        self.generation = 0
        self.busy = False

    def cached(self, key):
        return self.cache.get(key, False)

    def request(self, key, typed, messages, callback):
        """Ask for a prediction; callback(key, typed, prediction or None)
        runs on the main loop unless a newer request superseded this one"""
        if self.disabled:
            return
        if self.provider is None:
            self.provider = self.provider_factory()
            if self.provider is None:
                return
        self.generation += 1
        generation = self.generation
        thread = threading.Thread(target=self._run, name='promptline-predict',
                                  args=(generation, key, typed, messages,
                                        callback), daemon=True)
        thread.start()

    def _run(self, generation, key, typed, messages, callback):
        try:
            reply = self.provider.complete(messages)
            prediction = clean_prediction(reply, typed)
            dbg('promptline prediction for %r: %r' % (typed, reply))
        except ProviderError as ex:
            GLib.idle_add(self._failed, ex)
            return
        GLib.idle_add(self._deliver, generation, key, typed, prediction,
                      callback)

    def _deliver(self, generation, key, typed, prediction, callback):
        self.cache[key] = prediction
        while len(self.cache) > self.CACHE_SIZE:
            self.cache.popitem(last=False)
        if generation == self.generation:
            callback(key, typed, prediction)
        return False

    def _failed(self, error):
        if error.auth:
            # A bad key or model won't fix itself; stop asking
            self.disabled = True
            err('promptline: command prediction disabled: %s' % error)
        else:
            dbg('promptline prediction failed: %s' % error)
        return False
