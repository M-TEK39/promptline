#!/usr/bin/env python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""End-to-end tests for Promptline's shell integration: a real shell in a
real VTE, reporting marks that a Controller turns into a command log."""

import shutil
import time

import pytest
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gdk, GLib, Gtk, Vte

from promptlinelib.promptline import controller as controller_module
from promptlinelib.promptline import marks, shellint
from promptlinelib.promptline.controller import Controller
from promptlinelib.promptline.suggest.history import HistoryStore

pytestmark = pytest.mark.skipif(not marks.INSTALLED,
                                reason='VTE too old for termprops')


class FakeTerminal(object):
    """Just enough of promptlinelib.terminal.Terminal for a Controller"""
    def __init__(self):
        self.vte = Vte.Terminal()
        self.fgcolor_active = Gdk.RGBA(1, 1, 1, 1)
        self.window = Gtk.Window()

    def attach(self, controller):
        self.window.add(controller.wrap(self.vte))
        self.window.show_all()

    def get_cwd(self):
        uri = self.vte.ref_termprop_uri(Vte.TERMPROP_CURRENT_DIRECTORY_URI)
        return GLib.filename_from_uri(uri.to_string())[0] if uri else None


def wait_for(predicate, timeout=10):
    """Run the main loop until predicate() is true"""
    deadline = time.monotonic() + timeout
    context = GLib.MainContext.default()
    while not predicate():
        if time.monotonic() > deadline:
            return False
        context.iteration(False)
        time.sleep(0.005)
    return True


def start_shell(shell, home, environ, with_controller=False):
    terminal = FakeTerminal()
    controller = Controller(terminal)
    terminal.attach(controller)
    argv, envv = shellint.inject(shell, [shell], ['HOME=%s' % home,
                                                  'TERM=xterm-256color'],
                                 environ=environ)
    terminal.vte.spawn_sync(Vte.PtyFlags.DEFAULT, home, [shell] + argv,
                            envv, GLib.SpawnFlags.FILE_AND_ARGV_ZERO,
                            None, None, None)
    session = controller.session
    assert wait_for(lambda: session.state == session.PROMPT), \
        'shell never reported a prompt'
    if with_controller:
        return terminal, session, controller
    return terminal, session


def run(terminal, session, command):
    count = len(session.log)
    terminal.vte.feed_child((command + '\n').encode())
    assert wait_for(lambda: len(session.log) > count and
                    session.state == session.PROMPT), \
        'no record for %r' % command
    return session.log[-1]


@pytest.fixture(autouse=True)
def history(monkeypatch):
    """Keep tests away from the user's real history"""
    store = HistoryStore(path=None)
    monkeypatch.setattr(controller_module, 'shared_store', lambda: store)
    monkeypatch.setattr(controller_module.promptline, 'enabled',
                        lambda feature=None: True)
    # Never reach a real provider, even if the developer has a key set
    monkeypatch.setattr(controller_module, 'make_provider',
                        lambda purpose: None)
    return store


@pytest.fixture
def home(tmp_path):
    (tmp_path / 'sub dir').mkdir()
    (tmp_path / 'zdot').mkdir()
    (tmp_path / 'zdot' / '.zshrc').write_text("PS1='%~ %# '\n")
    (tmp_path / '.bashrc').write_text("PS1='\\w \\$ '\n")
    return tmp_path


SHELLS = [s for s in ('bash', 'zsh') if shutil.which(s)]


@pytest.mark.parametrize('name', SHELLS)
def test_command_log(name, home):
    environ = {'ZDOTDIR': str(home / 'zdot')}
    terminal, session = start_shell(shutil.which(name), str(home), environ)

    record = run(terminal, session, "echo \"it's; fine\"")
    assert record.command == "echo \"it's; fine\""
    assert record.exit_status == 0
    assert record.output == "it's; fine"
    assert record.cwd == str(home)

    record = run(terminal, session, 'printf "a\\nb\\n"; false')
    assert record.exit_status == 1
    assert record.output == 'a\nb'

    record = run(terminal, session, "cd 'sub dir'")
    record = run(terminal, session, 'pwd')
    assert record.cwd == str(home / 'sub dir')
    assert record.output == str(home / 'sub dir')


@pytest.mark.parametrize('name', SHELLS)
def test_current_input(name, home):
    environ = {'ZDOTDIR': str(home / 'zdot')}
    terminal, session = start_shell(shutil.which(name), str(home), environ)

    terminal.vte.feed_child(b'git che')
    assert wait_for(lambda: session.current_input() is not None and
                    session.current_input().text == 'git che')
    assert session.current_input().at_end

    # Cursor moved left: input is known but we're no longer at its end
    terminal.vte.feed_child(b'\x1b[D')
    assert wait_for(lambda: not session.current_input().at_end)


def press(controller, keyval, state=0):
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.keyval = keyval
    event.state = state
    return controller.on_keypress(event)


def typed(terminal, session, controller, text):
    """Type text and wait until the suggestion has been worked out for it"""
    terminal.vte.feed_child(text.encode())
    assert wait_for(lambda: session.current_input() is not None and
                    session.current_input().text.endswith(text) and
                    controller.refresh_id is None)


@pytest.mark.parametrize('name', SHELLS)
def test_autocomplete(name, home, history):
    environ = {'ZDOTDIR': str(home / 'zdot')}
    terminal, session, controller = start_shell(
        shutil.which(name), str(home), environ, with_controller=True)

    run(terminal, session, 'echo hello big world')
    run(terminal, session, ' echo private')
    assert history.best('echo h') == 'echo hello big world'
    assert history.best('echo p') is None

    typed(terminal, session, controller, 'echo h')
    assert controller.suggestion == ('echo h', 'ello big world')
    assert controller.ghost.text == 'ello big world'

    # Ctrl+Right takes one word, Right takes the rest
    assert press(controller, Gdk.KEY_Right, Gdk.ModifierType.CONTROL_MASK)
    assert wait_for(lambda: session.current_input().text == 'echo hello'
                    and controller.suggestion == ('echo hello', ' big world'))
    assert press(controller, Gdk.KEY_Right)
    assert wait_for(lambda: session.current_input().text ==
                    'echo hello big world' and controller.suggestion is None)
    assert not press(controller, Gdk.KEY_Right)
    run(terminal, session, '')

    # Nothing in history: fall back to completing the path
    typed(terminal, session, controller, 'ls su')
    assert controller.suggestion == ('ls su', 'b\\ dir/')


class FakeOpenAI(object):
    """A local stand-in for the Chat Completions endpoint"""
    def __init__(self):
        import http.server
        import json
        import threading
        server = self
        self.requests = []
        self.reply = lambda body: ''
        self.status = 200

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers['Content-Length'])
                body = json.loads(self.rfile.read(length))
                server.requests.append(body)
                if server.status != 200:
                    payload = {'error': {'message': 'bad key'}}
                else:
                    payload = {'choices': [{'message': {
                        'role': 'assistant', 'content': server.reply(body)}}]}
                data = json.dumps(payload).encode()
                self.send_response(server.status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.httpd = http.server.HTTPServer(('127.0.0.1', 0), Handler)
        self.url = 'http://127.0.0.1:%d/v1' % self.httpd.server_port
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def prompt(self, index=-1):
        return self.requests[index]['messages'][-1]['content']


@pytest.fixture
def fake_openai(monkeypatch):
    from promptlinelib.promptline.providers.openai import OpenAIProvider
    server = FakeOpenAI()
    monkeypatch.setattr(controller_module, 'make_provider',
                        lambda purpose: OpenAIProvider(server.url, None,
                                                       'test-model'))
    yield server
    server.httpd.shutdown()


def test_prediction(home, history, fake_openai):
    terminal, session, controller = start_shell(
        shutil.which('bash'), str(home), {}, with_controller=True)
    run(terminal, session, 'git push 2>/dev/null || echo "no upstream"; false')
    run(terminal, session, ' echo my-secret-thing')

    # Typing: the model completes what was started, using the context
    fake_openai.reply = lambda body: 'git push --set-upstream origin main'
    typed(terminal, session, controller, 'git pu')
    assert wait_for(lambda: controller.suggestion ==
                    ('git pu', 'sh --set-upstream origin main'))
    prompt = fake_openai.prompt()
    assert 'Typed so far: git pu' in prompt
    assert '[exit 1]' in prompt and 'no upstream' in prompt
    assert 'my-secret-thing' not in prompt
    assert fake_openai.requests[-1]['model'] == 'test-model'

    # Typing along the prediction keeps it without asking again
    asked = len(fake_openai.requests)
    typed(terminal, session, controller, 'sh')
    assert controller.suggestion == ('git push', ' --set-upstream origin main')
    time.sleep(0.5)
    assert len(fake_openai.requests) == asked

    # After a command finishes, the empty prompt gets a next-command guess
    terminal.vte.feed_child(b'\x15')    # clear the line
    fake_openai.reply = lambda body: '$ ls -la'
    run(terminal, session, 'echo done')
    assert wait_for(lambda: controller.suggestion == ('', 'ls -la'))
    assert 'Nothing typed yet' in fake_openai.prompt()

    # An @agent question is never sent for prediction
    asked = len(fake_openai.requests)
    typed(terminal, session, controller, '@agent why is it slow')
    time.sleep(0.6)
    assert len(fake_openai.requests) == asked


def test_prediction_auth_failure(home, history, fake_openai):
    terminal, session, controller = start_shell(
        shutil.which('bash'), str(home), {}, with_controller=True)
    fake_openai.status = 401
    typed(terminal, session, controller, 'git st')
    assert wait_for(lambda: controller.predictor.disabled)
    asked = len(fake_openai.requests)
    typed(terminal, session, controller, 'a')
    time.sleep(0.5)
    assert len(fake_openai.requests) == asked


def screen_text(terminal):
    vte = terminal.vte
    row = vte.get_cursor_position()[1]
    return vte.get_text_range_format(Vte.Format.TEXT, 0, 0, row,
                                     vte.get_column_count())[0]


@pytest.fixture
def agent_setup(monkeypatch, tmp_path, fake_openai):
    """Run the real promptline-agent against the fake server, with its
    runtime files in a temporary directory"""
    import os
    from promptlinelib.promptline import agent as agent_module
    program = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'promptline-agent')
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    monkeypatch.setenv('XDG_RUNTIME_DIR', str(runtime))
    monkeypatch.setenv('PYTHONPATH', os.path.dirname(program))
    monkeypatch.setattr(agent_module, 'agent_program', lambda: program)
    monkeypatch.setattr(controller_module, 'agent_program', lambda: program)
    # Prediction would share the fake server; it's tested separately
    monkeypatch.setattr(controller_module.promptline, 'enabled',
                        lambda feature=None: feature != 'llm_autocomplete')
    monkeypatch.setattr(controller_module, 'provider_settings',
                        lambda purpose: {
                            'promptline_provider': 'openai',
                            'promptline_base_url': fake_openai.url,
                            'promptline_api_key_env': '',
                            'promptline_api_key_file': '',
                            'model': 'agent-model', 'reasoning': ''})
    return fake_openai


def tool_call(name, **args):
    import json
    return {'id': 'call_%s' % name, 'type': 'function',
            'function': {'name': name, 'arguments': json.dumps(args)}}


@pytest.mark.parametrize('name', SHELLS)
def test_agent(name, home, history, agent_setup):
    import json
    server = agent_setup
    steps = [
        {'tool_calls': [tool_call('run_command', command='echo agent-ran',
                                  reason='check something')]},
        {'tool_calls': [tool_call('place_on_prompt', command='cd /tmp')]},
        {'content': 'All done.'},
    ]

    # Let the fake server return whole messages, not just text
    original = server.httpd.RequestHandlerClass.do_POST

    def do_POST(handler):
        length = int(handler.headers['Content-Length'])
        body = json.loads(handler.rfile.read(length))
        server.requests.append(body)
        message = dict({'role': 'assistant', 'content': None},
                       **steps[len(server.requests) - 1])
        data = json.dumps({'choices': [{'message': message}]}).encode()
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/json')
        handler.send_header('Content-Length', str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)
    server.httpd.RequestHandlerClass.do_POST = do_POST
    try:
        terminal, session, controller = start_shell(
            shutil.which(name), str(home), {'ZDOTDIR': str(home / 'zdot')},
            with_controller=True)
        run(terminal, session, 'ls /nonexistent-dir')

        typed(terminal, session, controller, "@agent what's wrong?")
        assert press(controller, Gdk.KEY_Return)
        # Starting the agent program is the slow part on a loaded machine
        assert wait_for(lambda: '[a]pprove' in screen_text(terminal),
                        timeout=30), screen_text(terminal)
        terminal.vte.feed_child(b'a')
        assert wait_for(lambda: session.state == session.PROMPT and
                        session.current_input() is not None and
                        session.current_input().text == 'cd /tmp',
                        timeout=20), screen_text(terminal)

        screen = screen_text(terminal)
        assert "@agent what's wrong?" in screen
        assert '_promptline_agent' not in screen
        assert 'agent-ran' in screen and 'All done.' in screen

        first = server.requests[0]
        assert first['model'] == 'agent-model'
        assert [t['function']['name'] for t in first['tools']] == \
            ['run_command', 'place_on_prompt']
        request = first['messages'][-1]['content']
        assert "Request: what's wrong?" in request
        assert 'ls /nonexistent-dir' in request and '[exit 2]' in request
        result = json.loads(server.requests[1]['messages'][-1]['content'])
        assert result == {'exit_status': 0, 'output': 'agent-ran'}

        # History has the question, not the launcher; the agent's run isn't
        # learned as a command
        terminal.vte.feed_child(b'\x15')
        record = run(terminal, session, 'fc -ln -5')
        assert "@agent what's wrong?" in record.output
        assert '_promptline_agent' not in record.output
        assert history.best('_promptline') is None
    finally:
        server.httpd.RequestHandlerClass.do_POST = original


def test_termprops_registered_before_first_terminal():
    """VTE refuses new termprops once a terminal exists, so they must be
    registered when terminal.py is imported. Run in a fresh process: this
    test module has already imported marks itself."""
    import subprocess
    import sys
    code = ('import gi\n'
            'gi.require_version("Gtk", "3.0")\n'
            'gi.require_version("Gdk", "3.0")\n'
            'import promptlinelib.terminal\n'
            'from gi.repository import Gtk, Vte\n'
            'window = Gtk.Window()\n'
            'window.add(Vte.Terminal())\n'
            'window.show_all()\n'
            'from promptlinelib.promptline import available\n'
            'print(available(), Vte.query_termprop("vte.ext.promptline.exec")[0])\n')
    result = subprocess.run([sys.executable, '-c', code], capture_output=True,
                            text=True, timeout=60)
    assert result.stdout.split() == ['True', 'True'], result.stderr
    assert 'CRITICAL' not in result.stderr
