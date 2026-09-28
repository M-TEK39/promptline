# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""loop.py - the agent's tool-calling loop

The loop is independent of any terminal: it talks to the user through a UI
object and runs commands through an executor, so it is tested with fakes.

UI methods: thinking(fn) runs fn while showing progress and returns its
result; say(text); approve(command, reason, note) -> ('approve'|'cancel',
command); auto_approved(command, mode, note); running(command);
finished(status); note(text).

>>> class Provider(object):
...     def __init__(self, replies): self.replies = list(replies)
...     def chat(self, messages, tools): return self.replies.pop(0)
>>> class UI(object):
...     def __init__(self, answer): self.answer, self.log = answer, []
...     def thinking(self, fn): return fn()
...     def say(self, text): self.log.append(('say', text))
...     def approve(self, command, reason, note=None):
...         self.log.append(('approve?', command, reason)); return self.answer
...     def auto_approved(self, command, mode, note):
...         self.log.append(('auto', mode, command))
...     def running(self, command): self.log.append(('run', command))
...     def finished(self, status): pass
...     def note(self, text): self.log.append(('note', text))
>>> def call(name, **args):
...     return {'role': 'assistant', 'content': None, 'tool_calls': [
...         {'id': 'c1', 'type': 'function', 'function': {
...          'name': name, 'arguments': json.dumps(args)}}]}
>>> def executor(command): return 0, '3000/tcp: node'
>>> provider = Provider([call('run_command', command='lsof -i :3000',
...                           reason='find the process'),
...                      {'role': 'assistant', 'content': 'node holds it.'}])
>>> ui = UI(('approve', 'lsof -i :3000'))
>>> agent = Agent(provider, ui, executor)
>>> agent.run({'role': 'user', 'content': 'port 3000?'})
>>> ui.log
[('approve?', 'lsof -i :3000', 'find the process'), ('run', 'lsof -i :3000'), ('say', 'node holds it.')]
>>> json.loads(agent.messages[2]['content'])
{'exit_status': 0, 'output': '3000/tcp: node'}

Declining is reported back to the model:

>>> provider = Provider([call('run_command', command='rm -rf /tmp/x',
...                           reason='clean up'),
...                      {'role': 'assistant', 'content': 'OK, left it.'}])
>>> agent = Agent(provider, UI(('cancel', 'rm -rf /tmp/x')), executor)
>>> agent.run({'role': 'user', 'content': 'clean'})
>>> agent.messages[2]['content']
'The user declined to run this command.'

Memory tools, and edits reported back to the model:

>>> class Memory(object):
...     def __init__(self): self.facts = []
...     def add(self, fact, replaces=None): self.facts.append(fact); return True
...     def forget(self, match): return []
>>> provider = Provider([call('remember', fact='Uses Nessus, not nmap',
...                           replaces=''),
...                      call('run_command', command='nmap -sV 10.0.0.5',
...                           reason='check services'),
...                      {'role': 'assistant', 'content': 'Done.'}])
>>> ui = UI(('approve', 'nessuscli scan --target 10.0.0.5'))
>>> agent = Agent(provider, ui, executor, memory=Memory())
>>> agent.run({'role': 'user', 'content': 'scan 10.0.0.5'})
>>> ui.log[0]
('note', 'Remembered: Uses Nessus, not nmap')
>>> json.loads(agent.messages[4]['content'])['note']
'The user edited your command and ran this instead: nessuscli scan --target 10.0.0.5'

In full permission mode commands run unasked, except hard stops, and
every command run is audited:

>>> from .approval import FullPermission
>>> provider = Provider([call('run_command', command='df -h', reason='disk'),
...                      call('run_command', command='sudo reboot',
...                           reason='apply'),
...                      {'role': 'assistant', 'content': 'Done.'}])
>>> ui, audit = UI(('cancel', 'sudo reboot')), []
>>> agent = Agent(provider, ui, executor, policy=FullPermission(),
...               audit=lambda *entry: audit.append(entry))
>>> agent.run({'role': 'user', 'content': 'check disk then reboot'})
>>> ui.log[:3]
[('auto', 'full', 'df -h'), ('run', 'df -h'), ('approve?', 'sudo reboot', 'apply')]
>>> audit
[('df -h', 'full', 0)]

place_on_prompt remembers the command for the user's prompt:

>>> provider = Provider([call('place_on_prompt', command='cd /srv/app'),
...                      {'role': 'assistant', 'content': 'Done.'}])
>>> agent = Agent(provider, UI(None), executor)
>>> agent.run({'role': 'user', 'content': 'go to the app'})
>>> agent.prefill
'cd /srv/app'
"""

import json

from .approval import ALLOW, DENY, AskEveryTime
from .tools import TOOLS

MAX_STEPS = 25


class Agent(object):
    def __init__(self, provider, ui, executor, policy=None, messages=None,
                 max_steps=MAX_STEPS, memory=None, audit=None):
        self.provider = provider
        self.ui = ui
        self.executor = executor
        self.policy = policy or AskEveryTime()
        self.memory = memory
        self.audit = audit          # audit(command, how, exit status)
        self.messages = list(messages or [])
        self.max_steps = max_steps
        self.prefill = None

    def run(self, user_message):
        """Handle one request from the user, until the model stops calling
        tools"""
        self.messages.append(user_message)
        for _step in range(self.max_steps):
            reply = self.ui.thinking(
                lambda: self.provider.chat(self.messages, TOOLS))
            self.messages.append(reply)
            if reply.get('content'):
                self.ui.say(reply['content'].strip())
            calls = reply.get('tool_calls') or []
            if not calls:
                return
            for call in calls:
                self.messages.append({'role': 'tool',
                                      'tool_call_id': call.get('id'),
                                      'content': self.handle(call)})
        self.ui.note('Stopped after %d steps.' % self.max_steps)

    def handle(self, call):
        """Carry out one tool call; returns the text sent back to the model"""
        function = call.get('function', {})
        name = function.get('name')
        try:
            args = json.loads(function.get('arguments') or '{}')
        except ValueError:
            return 'Error: the arguments were not valid JSON.'
        if name in ('remember', 'forget'):
            return self.handle_memory(name, args)
        command = (args.get('command') or '').strip()
        if not command:
            return 'Error: no command given.'

        if name == 'place_on_prompt':
            self.prefill = command
            self.ui.note('Will be placed on your prompt: %s' % command)
            return 'The command will be typed at the user\'s prompt.'

        if name != 'run_command':
            return 'Error: there is no tool called %r.' % name
        reason = args.get('reason', '')
        decision = self.policy.decide(command, reason)
        if decision.action == DENY:
            return 'This command is not allowed.'
        proposed = command
        if decision.action == ALLOW:
            self.ui.auto_approved(command, self.policy.mode, decision.note)
            how = self.policy.mode
        else:
            answer, command = self.ui.approve(command, reason, decision.note)
            self.policy.remember(command, answer == 'approve')
            if answer != 'approve':
                result = 'The user declined to run this command.'
                if decision.note:
                    result += ' (It was flagged: %s.)' % decision.note
                return result
            how = 'edited' if command != proposed else 'approved'
        self.ui.running(command)
        status, output = self.executor(command)
        self.ui.finished(status)
        if self.audit is not None:
            self.audit(command, how, status)
        result = {'exit_status': status, 'output': output}
        if command != proposed:
            # How the user changes a command is worth learning from
            result['note'] = 'The user edited your command and ran this ' \
                'instead: %s' % command
        return json.dumps(result)

    def handle_memory(self, name, args):
        if self.memory is None:
            return 'Error: memory is not available.'
        if name == 'remember':
            fact = (args.get('fact') or '').strip()
            if not fact:
                return 'Error: no fact given.'
            if self.memory.add(fact, (args.get('replaces') or '').strip()
                               or None):
                self.ui.note('Remembered: %s' % fact)
                return 'Saved to memory.'
            return 'Already in memory.'
        match = (args.get('match') or '').strip()
        gone = self.memory.forget(match) if match else []
        for fact in gone:
            self.ui.note('Forgot: %s' % fact)
        return 'Forgot %d fact(s).' % len(gone)
