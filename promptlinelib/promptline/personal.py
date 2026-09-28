# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""personal.py - what Promptline knows about its user, from three files

* personalisation (~/.config/promptline/personal.md): written by the user,
  describing their work, tools and environments, so predictions and @agent
  fit them from day one instead of only after long command history
  (`promptline -P`)
* guardrails (~/.config/promptline/guardrails.md): the user's rules for the
  agent, added to its system prompt in every mode; Full permission mode
  requires them (`promptline --guardrails`)
* memory (~/.local/share/promptline/memory.md): facts the agent keeps about
  the user, one per line; it adds and removes them itself or when asked
  (`promptline --memory`)

Text inside <!-- --> is guidance for the user and is never sent to a model.

>>> strip_comments('<!-- help -->\\nI run a SOC.\\n<!-- more\\nhelp -->')
'I run a SOC.'
>>> guardrails_ready(TEMPLATES['guardrails'])
(False, 'write at least 3 rules (lines starting with "- ") in your guardrails')
>>> guardrails_ready('- never touch prod\\n- ask before deleting\\n- no scans of 10.0.0.0/8')
(True, None)
"""

import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

from ..util import get_config_dir
from .suggest.llm import redact

MIN_GUARDRAIL_RULES = 3
MAX_PERSONAL_CHARS = 4000
MAX_MEMORY_FACTS = 100
MAX_FACT_CHARS = 300

TEMPLATES = {
    'personal': """<!--
Tell Promptline about your work. The command prediction and @agent read this,
so they suggest your tools and follow your habits from the start. Write in
plain words; remove or keep these hints (text inside these comment markers is
never sent to the model). Don't put passwords or keys here.
-->

## My role
<!-- e.g. Security engineer in a SOC; network admin for a campus network -->

## Day to day
<!-- e.g. Vulnerability scans, triaging alerts, firewall changes, packet
captures, reviewing auth logs on Linux servers -->

## Tools I use
<!-- e.g. Nessus for enterprise scans; nmap only for quick checks on single
hosts; Wireshark/tshark; Splunk; Ansible for switch configs; ssh into
Cisco IOS and Juniper devices -->

## Tools I avoid
<!-- e.g. I don't use masscan; never suggest telnet -->

## My environments
<!-- e.g. Jump host is bastion.corp.example; lab network 10.20.0.0/16 is
safe to scan; production is 10.0.0.0/16 -->

## How I like answers
<!-- e.g. Short. Show the command first. Prefer read-only checks. -->
""",
    'guardrails': """<!--
Your rules for the @agent. They are added to its system prompt in every
permission mode and take precedence over your requests. Full permission mode
(commands run without asking) stays locked until this file has at least 3
rules, one per line, each starting with "- ".

Examples (copy the ones you want out of this comment and adapt them):

- Never run scans, exploits or brute force against hosts outside 10.20.0.0/16.
- Never change firewall rules, routing, or VPN configuration.
- Never delete files outside the current project directory.
- Never stop or restart services on production hosts.
- Never send data to external services or pastebins.
- Never modify users, groups, sudoers or SSH keys.
- Read-only commands first; explain any change before making it.
-->
""",
    'memory': """<!--
What the @agent remembers about you, one fact per line starting with "- ".
It adds and removes facts itself (and tells you when it does), or when you
ask ("@agent remember that ..."). Edit or delete lines freely.
-->
""",
}


def _data_dir():
    base = os.environ.get('XDG_DATA_HOME') or \
        os.path.join(os.path.expanduser('~'), '.local', 'share')
    return os.path.join(base, 'promptline')


def path(kind):
    """Where the 'personal', 'guardrails' or 'memory' file lives"""
    if kind == 'memory':
        return os.path.join(_data_dir(), 'memory.md')
    return os.path.join(get_config_dir(), kind + '.md')


def strip_comments(text):
    """The part of a file meant for the model"""
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def read(kind):
    """A file's content without guidance comments ('' if there is none)"""
    try:
        with open(path(kind), encoding='utf-8') as handle:
            return strip_comments(handle.read())
    except OSError:
        return ''


def personal_text(limit=MAX_PERSONAL_CHARS):
    """The user's personalisation, without headings they left empty"""
    kept = []
    for section in re.split(r'(?m)^(?=## )', read('personal')):
        lines = section.strip().split('\n')
        if not section.strip():
            continue
        if len(lines) > 1 or not lines[0].startswith('## '):
            kept.append(section.strip())
    return redact('\n\n'.join(kept))[:limit]


def guardrail_rules(text=None):
    text = read('guardrails') if text is None else strip_comments(text)
    return [line.strip() for line in text.split('\n')
            if line.strip().startswith('- ') and len(line.strip()) > 3]


def guardrails_ready(text=None):
    """(ready, reason) for Full permission mode"""
    if len(guardrail_rules(text)) < MIN_GUARDRAIL_RULES:
        return False, ('write at least %d rules (lines starting with "- ") '
                       'in your guardrails' % MIN_GUARDRAIL_RULES)
    return True, None


def ensure(kind):
    """Create the file from its template if it doesn't exist; return path"""
    target = path(kind)
    if not os.path.exists(target):
        os.makedirs(os.path.dirname(target), mode=0o700, exist_ok=True)
        _write(target, TEMPLATES[kind])
    return target


def _write(target, text):
    """Replace a file atomically, readable only by the user"""
    directory = os.path.dirname(target)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=directory, prefix='.tmp-')
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        handle.write(text)
    os.chmod(temp, 0o600)
    os.replace(temp, target)


def edit(kind, gui=False):
    """Open a file for editing: in $VISUAL/$EDITOR when run from a terminal,
    otherwise (or with gui) in the desktop's text editor. Returns an exit
    status."""
    target = ensure(kind)
    if not gui and sys.stdin.isatty() and sys.stdout.isatty():
        editor = os.environ.get('VISUAL') or os.environ.get('EDITOR')
        command = shlex.split(editor) if editor else \
            [next((e for e in ('nano', 'vim', 'vi') if shutil.which(e)),
                  'vi')]
        return subprocess.call(command + [target])
    from gi.repository import Gio
    Gio.AppInfo.launch_default_for_uri('file://' + target, None)
    return 0


def edit_and_report(kind):
    """`promptline -P` / `--guardrails` / `--memory`: edit, then say what
    changed for the user"""
    status = edit(kind)
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return status
    if kind == 'guardrails':
        ready, reason = guardrails_ready()
        print('%d guardrail rules. Full permission mode is %s.' % (
            len(guardrail_rules()),
            'available' if ready else 'locked: ' + reason))
    elif kind == 'personal':
        print('Saved %s. Predictions and @agent use it from now on.' %
              path(kind) if personal_text() else
              'Nothing written yet (hints in <!-- --> are ignored).')
    else:
        print('The agent remembers %d facts.' % len(Memory().facts()))
    return status


class Memory(object):
    """The agent's memory: a list of short facts in memory.md

    >>> memory = Memory(os.path.join(tempfile.mkdtemp(), 'memory.md'))
    >>> memory.add('Uses Nessus for enterprise scans')
    True
    >>> memory.add('uses nessus for enterprise scans')      # already known
    False
    >>> memory.add('Prefers nmap for everything')
    True
    >>> memory.add('Only uses nmap for single hosts',
    ...            replaces='nmap for everything')
    True
    >>> memory.forget('nessus')
    ['Uses Nessus for enterprise scans']
    >>> memory.facts()
    ['Only uses nmap for single hosts']
    >>> memory.add('API token is sk-abcdefghijklmnopqrstuvwxyz')
    True
    >>> memory.facts()[-1]
    'API token is [redacted]'
    """
    def __init__(self, filename=None):
        self.filename = filename or path('memory')

    def _read(self):
        try:
            with open(self.filename, encoding='utf-8') as handle:
                return handle.read()
        except OSError:
            return TEMPLATES['memory']

    def facts(self):
        return [line.strip()[2:].strip()
                for line in strip_comments(self._read()).split('\n')
                if line.strip().startswith('- ')]

    def _save(self, facts):
        header = re.match(r'\s*<!--.*?-->\s*', self._read(), re.DOTALL)
        text = (header.group(0).rstrip() + '\n\n' if header else '') + \
            ''.join('- %s\n' % fact for fact in facts)
        _write(self.filename, text)

    def add(self, fact, replaces=None):
        """Remember fact (replacing facts that contain `replaces`). Returns
        False if it was already known."""
        fact = redact(' '.join(fact.split()))[:MAX_FACT_CHARS]
        facts = self.facts()
        if replaces:
            facts = [f for f in facts if replaces.lower() not in f.lower()]
        if any(f.lower() == fact.lower() for f in facts):
            return False
        facts.append(fact)
        self._save(facts[-MAX_MEMORY_FACTS:])
        return True

    def forget(self, match):
        """Forget facts containing match; returns what was forgotten"""
        facts = self.facts()
        gone = [f for f in facts if match.lower() in f.lower()]
        if gone:
            self._save([f for f in facts if f not in gone])
        return gone

    def text(self):
        return '\n'.join('- ' + fact for fact in self.facts())
