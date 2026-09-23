# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""prefs.py - the Promptline page of the Preferences window

Built in code rather than in preferences.glade, so that Promptline's UI
stays out of the upstream Terminator files.
"""

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from ..translation import _
from .providers import resolve_api_key

REASONING = ['', 'none', 'minimal', 'low', 'medium', 'high', 'xhigh']


class PromptlinePage(object):
    """Widgets bound to the promptline_* keys in [global_config]"""
    def __init__(self, config):
        self.config = config
        self.grid = Gtk.Grid(column_spacing=12, row_spacing=6,
                             margin=18)
        self.row = 0
        self.key_status = None

        self.heading(_('Promptline'))
        self.note(_('With these off, Promptline behaves exactly like '
                    'Terminator. Changes apply to new terminals.'))
        self.check('enabled', _('Enable Promptline'))
        self.check('shell_integration',
                   _('Load shell integration (bash and zsh)'))
        self.check('autocomplete',
                   _('Suggest from history and paths as you type'))

        self.heading(_('Command prediction'))
        self.check('llm_autocomplete', _('Predict commands with a model'))
        self.note(_('Sends the current directory, recent commands, their '
                    'exit status and the end of the last output to the '
                    'provider. Things that look like secrets are removed, '
                    'and commands typed with a leading space are never '
                    'sent.'))
        self.check('predict_next',
                   _('Predict the next command on an empty prompt'))
        self.entry('autocomplete_model', _('Model'))
        self.reasoning('autocomplete_reasoning', _('Reasoning effort'))

        self.heading(_('@agent'))
        self.note(_('Type "@agent" and a question or task at the prompt. '
                    'Every command it wants to run asks for your approval.'))
        self.entry('agent_model', _('Model'))
        self.reasoning('agent_reasoning', _('Reasoning effort'))

        self.heading(_('Provider'))
        self.entry('base_url', _('API base URL'))
        self.note(_('OpenAI, or any OpenAI-compatible server such as '
                    'Ollama (http://localhost:11434/v1), which needs no '
                    'key.'))
        self.entry('api_key_env', _('Key environment variable'))
        self.key_file()
        self.key_status = Gtk.Label(xalign=0)
        self.attach(self.key_status)
        self.update_key_status()

    # Rows

    def attach(self, widget, label=None):
        if label is None:
            self.grid.attach(widget, 0, self.row, 2, 1)
        else:
            self.grid.attach(Gtk.Label(label=label, xalign=0), 0, self.row,
                             1, 1)
            widget.set_hexpand(True)
            self.grid.attach(widget, 1, self.row, 1, 1)
        self.row += 1

    def heading(self, text):
        label = Gtk.Label(xalign=0)
        label.set_markup('<b>%s</b>' % text)
        if self.row:
            label.set_margin_top(12)
        self.attach(label)

    def note(self, text):
        label = Gtk.Label(label=text, xalign=0, wrap=True,
                          max_width_chars=70)
        label.get_style_context().add_class('dim-label')
        self.attach(label)

    def check(self, key, text):
        button = Gtk.CheckButton(label=text)
        button.set_active(bool(self.config['promptline_' + key]))
        button.connect('toggled', lambda b: self.set(key, b.get_active()))
        self.attach(button)

    def entry(self, key, text):
        entry = Gtk.Entry(text=self.config['promptline_' + key])
        entry.connect('changed', lambda e: self.set(key, e.get_text().strip()))
        self.attach(entry, text)

    def reasoning(self, key, text):
        combo = Gtk.ComboBoxText.new_with_entry()
        for effort in REASONING:
            combo.append_text(effort)
        combo.get_child().set_text(self.config['promptline_' + key])
        combo.connect('changed', lambda c: self.set(
            key, c.get_active_text().strip()))
        self.attach(combo, text)

    def key_file(self):
        box = Gtk.Box(spacing=6)
        entry = Gtk.Entry(text=self.config['promptline_api_key_file'],
                          hexpand=True,
                          placeholder_text=_('optional, e.g. '
                                             '~/.config/promptline/openai-key'))
        entry.connect('changed',
                      lambda e: self.set('api_key_file', e.get_text().strip()))
        choose = Gtk.Button(label=_('Choose...'))
        choose.connect('clicked', self.on_choose_key_file, entry)
        box.pack_start(entry, True, True, 0)
        box.pack_start(choose, False, False, 0)
        self.attach(box, _('Key file'))

    # Behaviour

    def set(self, key, value):
        self.config['promptline_' + key] = value
        self.config.save()
        if key.startswith('api_key') and self.key_status is not None:
            self.update_key_status()

    def update_key_status(self):
        """Say whether a key is found, without ever showing it"""
        if resolve_api_key(self.config):
            self.key_status.set_text(_('An API key was found.'))
        else:
            self.key_status.set_text(_('No API key found: prediction and '
                                       '@agent need one for hosted '
                                       'providers.'))

    def on_choose_key_file(self, button, entry):
        dialog = Gtk.FileChooserDialog(
            title=_('Choose the file containing your API key'),
            transient_for=button.get_toplevel(),
            action=Gtk.FileChooserAction.OPEN)
        dialog.add_buttons(_('Cancel'), Gtk.ResponseType.CANCEL,
                           _('Choose'), Gtk.ResponseType.ACCEPT)
        dialog.set_show_hidden(True)
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            entry.set_text(dialog.get_filename())
        dialog.destroy()


def add_page(notebook, config):
    """Append the Promptline page to the Preferences notebook"""
    page = PromptlinePage(config)
    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroller.add(page.grid)
    scroller.show_all()
    notebook.append_page(scroller, Gtk.Label(label=_('Promptline')))
    return page
