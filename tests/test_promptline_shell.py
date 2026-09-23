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

from terminatorlib.promptline import controller as controller_module
from terminatorlib.promptline import marks, shellint
from terminatorlib.promptline.controller import Controller
from terminatorlib.promptline.suggest.history import HistoryStore

pytestmark = pytest.mark.skipif(not marks.INSTALLED,
                                reason='VTE too old for termprops')


class FakeTerminal(object):
    """Just enough of terminatorlib.terminal.Terminal for a Controller"""
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
    from terminatorlib.promptline.providers.openai import OpenAIProvider
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
