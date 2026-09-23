# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""shellint.py - load Promptline's shell integration into new shells

The user's own startup files are always loaded as normal; the integration
only adds hooks after them. Shells we don't support are left untouched.

argv follows Terminator's spawn convention: argv[0] is the name the shell
sees as $0, and '-l' there makes it a login shell.

>>> SHELL_DIR = '/pl'
>>> inject('/bin/bash', ['/bin/bash'], ['TERM=xterm'], environ={}, shell_dir=SHELL_DIR, extra_env=[])
(['/bin/bash', '--rcfile', '/pl/promptline.bash'], ['TERM=xterm', 'PROMPTLINE=1'])
>>> inject('/bin/bash', ['-l'], [], environ={}, shell_dir=SHELL_DIR, extra_env=[])
(['bash', '--rcfile', '/pl/promptline.bash'], ['PROMPTLINE=1', 'PROMPTLINE_BASH_LOGIN=1'])
>>> inject('/usr/bin/zsh', ['-l'], [], environ={'ZDOTDIR': '/z'}, shell_dir=SHELL_DIR, extra_env=[])
(['-l'], ['PROMPTLINE=1', 'ZDOTDIR=/pl/zdotdir', 'PROMPTLINE_ZDOTDIR=/z'])
>>> inject('/usr/bin/zsh', ['/usr/bin/zsh'], [], environ={}, shell_dir=SHELL_DIR, extra_env=['A=1'])
(['/usr/bin/zsh'], ['PROMPTLINE=1', 'A=1', 'ZDOTDIR=/pl/zdotdir'])
>>> inject('/usr/bin/fish', ['/usr/bin/fish'], [], environ={}, shell_dir=SHELL_DIR)
(['/usr/bin/fish'], [])
"""

import os
import sys

from . import agent

SHELL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shell')


def supported(shell):
    """Return True if we have integration for this shell binary"""
    return os.path.basename(shell) in ('bash', 'zsh')


def agent_env():
    """Environment the shell's _promptline_agent launcher needs"""
    program = agent.agent_program()
    if program is None:
        return []
    return ['PROMPTLINE_PYTHON=%s' % sys.executable,
            'PROMPTLINE_AGENT=%s' % program,
            'PROMPTLINE_RUNTIME=%s' % agent.runtime_dir()]


def inject(shell, argv, envv, environ=None, shell_dir=None, extra_env=None):
    """Return (argv, envv) that start shell with Promptline's integration.

    envv is the extra environment Terminator passes to the child; environ is
    the environment it inherits (defaults to os.environ). extra_env defaults
    to what @agent needs.
    """
    if environ is None:
        environ = os.environ
    if shell_dir is None:
        shell_dir = SHELL_DIR
    name = os.path.basename(shell)
    if not supported(shell):
        return argv, envv

    argv = list(argv)
    envv = list(envv) + ['PROMPTLINE=1']
    envv += agent_env() if extra_env is None else extra_env
    login = bool(argv) and argv[0] == '-l'

    if name == 'bash':
        # A login bash ignores --rcfile, so start a normal one and let the
        # rcfile read the login files itself.
        if login:
            argv[0] = 'bash'
            envv.append('PROMPTLINE_BASH_LOGIN=1')
        argv[1:1] = ['--rcfile', os.path.join(shell_dir, 'promptline.bash')]
    elif name == 'zsh':
        envv.append('ZDOTDIR=%s' % os.path.join(shell_dir, 'zdotdir'))
        if 'ZDOTDIR' in environ:
            envv.append('PROMPTLINE_ZDOTDIR=%s' % environ['ZDOTDIR'])

    return argv, envv
