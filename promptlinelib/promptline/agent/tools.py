# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""tools.py - what the agent can do, and running its commands

>>> import io
>>> sink = io.BytesIO()
>>> run_command('echo out; echo err >&2; exit 3', '/', 'sh', sink)
(3, 'out\\nerr')
>>> sink.getvalue()
b'out\\nerr\\n'
>>> trim_output('x' * 10, limit=6)
'xxx\\n[... 4 characters omitted ...]\\nxxx'
"""

import os
import signal
import subprocess

OUTPUT_LIMIT = 16000

TOOLS = [
    {'type': 'function', 'function': {
        'name': 'run_command',
        'description': (
            'Run a shell command in the user\'s terminal, after the user '
            'approves it (they may edit it first or decline). Returns the '
            'exit status and the combined stdout/stderr.'),
        'parameters': {
            'type': 'object',
            'properties': {
                'command': {'type': 'string',
                            'description': 'The command line to run.'},
                'reason': {'type': 'string',
                           'description': 'One short line telling the user '
                                          'why, shown with the approval '
                                          'prompt.'},
            },
            'required': ['command', 'reason'],
            'additionalProperties': False,
        },
    }},
    {'type': 'function', 'function': {
        'name': 'place_on_prompt',
        'description': (
            'Type a command at the user\'s shell prompt once you finish, '
            'without running it; the user presses Enter if they want it. '
            'Use this for commands that must change the user\'s own shell '
            '(cd, export, source, activating an environment) or that they '
            'should run themselves. Only the last one placed is used.'),
        'parameters': {
            'type': 'object',
            'properties': {
                'command': {'type': 'string'},
            },
            'required': ['command'],
            'additionalProperties': False,
        },
    }},
]


def trim_output(text, limit=OUTPUT_LIMIT):
    """Keep the start and end of long output"""
    if len(text) <= limit:
        return text
    head = limit // 2
    tail = limit - head
    return '%s\n[... %d characters omitted ...]\n%s' % (
        text[:head], len(text) - head - tail, text[-tail:])


def run_command(command, cwd, shell, sink):
    """Run command with shell -c in cwd, copying its output to sink (a
    binary stream) as it arrives. Returns (exit status, output text).
    stdin stays the terminal, so password prompts still work."""
    process = subprocess.Popen([shell, '-c', command], cwd=cwd,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
    chunks = []
    size = 0
    try:
        while True:
            data = os.read(process.stdout.fileno(), 65536)
            if not data:
                break
            sink.write(data)
            sink.flush()
            size += len(data)
            chunks.append(data)
            # Keep memory bounded on runaway output: keep the first chunk
            # and a window of the most recent ones
            while size > OUTPUT_LIMIT * 8 and len(chunks) > 2:
                size -= len(chunks.pop(1))
        status = process.wait()
    except KeyboardInterrupt:
        process.send_signal(signal.SIGINT)
        process.wait()
        raise
    finally:
        process.stdout.close()
    if status < 0:
        status = 128 - status
    output = b''.join(chunks).decode('utf-8', 'replace')
    return status, trim_output(output.rstrip())
