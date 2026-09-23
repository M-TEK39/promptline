# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""prompts.py - what the agent is told about itself and the terminal

>>> request = {'cwd': '/nonexistent', 'shell': '/bin/zsh', 'records': [
...     {'command': 'npm start', 'cwd': '/nonexistent', 'exit_status': 1,
...      'output': 'Error: listen EADDRINUSE :::3000', 'private': False},
...     {'command': 'cat .env', 'cwd': '/nonexistent', 'exit_status': 0,
...      'output': 'TOKEN=abc', 'private': True}]}
>>> text = context_text(request)
>>> 'EADDRINUSE' in text, 'TOKEN' in text, '[exit 1]' in text
(True, False, True)
"""

import os
import platform

from ..suggest.llm import git_branch, listing, redact

RECENT_COMMANDS = 10
FULL_OUTPUTS = 3
OUTPUT_TAIL = 3000
SHORT_OUTPUT_TAIL = 400


def system_prompt(shell):
    shell = os.path.basename(shell or 'sh')
    return ' '.join([
        "You are the Promptline terminal agent. The user called you from "
        "their shell prompt by typing @agent, and your replies are printed "
        "straight into their terminal.",

        "Write plain text for a terminal: short paragraphs, no Markdown "
        "headings, tables or bold. Put any command on a line of its own. "
        "Be brief and concrete.",

        "Use the context you are given (recent commands, their exit "
        "statuses and output) instead of asking the user to paste things.",

        "You can run commands with run_command. The user approves each one "
        "before it runs and may edit or decline it, so propose one command "
        "at a time, each with a short reason, and look before you change "
        "anything: prefer read-only commands to investigate. If the user "
        "declines, don't retry the same command; ask or suggest instead.",

        "Each command runs with `%s -c` in the user's current directory "
        "with their environment, but without their aliases or functions, "
        "and shell state such as cd or exported variables does not carry "
        "over to the next command (use `cd dir && ...`). Interactive "
        "programs (editors, pagers, prompts, TUIs) will not work; use "
        "non-interactive flags such as --no-pager or -y only when the user "
        "clearly wants the change." % shell,

        "For anything that must happen in the user's own shell (cd, export, "
        "source, activating an environment), or that they should run "
        "themselves, use place_on_prompt: the command is typed at their "
        "prompt when you finish, and they choose whether to press Enter.",

        "Be careful with destructive commands: say what they will affect. "
        "When you are done, say in a sentence or two what you found or did.",
    ])


def context_text(request):
    """Describe the terminal for the model"""
    cwd = request.get('cwd')
    lines = ['Shell: %s on %s' % (os.path.basename(request.get('shell') or
                                                   'sh'), platform.system())]
    if cwd:
        branch = git_branch(cwd)
        lines.append('Current directory: %s%s' % (
            cwd, ' (git branch %s)' % branch if branch else ''))
        contents = listing(cwd)
        if contents is not None:
            lines.append('Directory contents: %s' % (contents or '(empty)'))
    records = [r for r in request.get('records', []) if not r.get('private')]
    records = records[-RECENT_COMMANDS:]
    if records:
        lines.append('')
        lines.append('Recent commands in this terminal, oldest first:')
        for index, record in enumerate(records):
            status = record.get('exit_status')
            where = record.get('cwd')
            lines.append('$ %s%s%s' % (
                redact(record.get('command', '')),
                ' (in %s)' % where if where and where != cwd else '',
                ' [exit %s]' % status if status is not None else ''))
            output = record.get('output') or ''
            if output:
                full = index >= len(records) - FULL_OUTPUTS
                tail = OUTPUT_TAIL if full else SHORT_OUTPUT_TAIL
                if len(output) > tail:
                    output = '[...]\n' + output[-tail:]
                lines.append(redact(output))
    else:
        lines.append('No commands recorded in this terminal yet.')
    return '\n'.join(lines)


def user_message(request):
    """The message for this invocation: fresh context, then the question"""
    return {'role': 'user', 'content': '%s\n\nRequest: %s' % (
        context_text(request), request.get('query', ''))}
