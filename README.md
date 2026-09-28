# Promptline

**A normal terminal that predicts the command you're about to type, and works
on a task for you when you ask it with `@agent`.**

Promptline is built on [Terminator](https://github.com/gnome-terminator/terminator).
It looks and behaves like the terminal you already use: no side panels, no
chat window, no output blocks. With its AI features off, it *is* Terminator.

```text
$ git push
fatal: The current branch main has no upstream branch.
$ git pu█sh --set-upstream origin main    ← dimmed prediction; → accepts

$ @agent what's using port 3000?
Find the process listening on port 3000.
  $ lsof -i :3000
  [a]pprove  [e]dit  [c]ancel approved
COMMAND   PID USER  FD  TYPE DEVICE SIZE/OFF NODE NAME
node    48213 dev   23u IPv6 412337      0t0  TCP *:3000 (LISTEN)

A Node.js process (PID 48213) is listening on port 3000.
```

## Features

**Inline suggestions.** As you type, the most likely completion appears
dimmed after the cursor. It comes from your shell history (bash and zsh
history are read, never modified), Promptline's own log of where each command
ran and whether it worked, and the file system. Suggestions are local and
instant and work offline. Press **→** or **End** to accept one, or
**Ctrl+→** to accept a word.

**Command prediction (optional).** With a model configured, Promptline also
predicts from context: the current directory, the last few commands and how
they ended, and the end of the last output. That turns a failed `git push`
into the right `--set-upstream` fix. On an empty prompt it suggests your
likely next command. Requests wait for a pause in typing and run in the
background, so typing never waits on the network.

**`@agent`.** Type `@agent` and a question or task at the prompt. The agent
already sees what's in the terminal, so you don't paste anything:

- every command it wants to run is shown first, and asks **approve / edit /
  cancel**;
- commands run in your current directory, with their output streaming into
  the terminal;
- for things that must happen in your own shell (`cd`, `export`, activating
  an environment) it types the command at your prompt, and you decide
  whether to press Enter;
- follow-up questions in the same terminal continue the conversation;
- it's a normal program in your terminal: Ctrl+C stops it, and its output is
  ordinary scrollback.

## Privacy

- Nothing is sent anywhere unless you enable command prediction or run
  `@agent`.
- What is sent is described in the Preferences window: the directory, recent
  commands with exit statuses, and the end of recent output. Things that
  look like credentials (API keys, tokens, `password=` arguments) are
  removed first.
- A command typed with a **leading space** is private, as in bash's and
  zsh's `ignorespace`: Promptline never learns it or sends it.
- API keys are read from an environment variable or a file you point to.
  They are never written to Promptline's config.

## Requirements

- Linux, Python 3, GTK 3
- VTE with terminal-property support (0.78 or newer; developed against 0.84).
  On an older VTE Promptline runs as plain Terminator.
- bash or zsh for suggestions, prediction and `@agent` (fish isn't supported
  yet)

On Debian/Ubuntu:

```sh
sudo apt install python3-gi python3-gi-cairo python3-psutil python3-configobj \
  gir1.2-gtk-3.0 gir1.2-vte-2.91 gir1.2-keybinder-3.0 gir1.2-notify-0.7
```

## Installing

On Debian/Ubuntu, build and install the package:

```sh
sudo apt install debhelper dh-python gettext intltool
git clone https://github.com/M-TEK39/promptline.git
cd promptline
dpkg-buildpackage -us -uc -b
sudo apt install ../promptline_*_all.deb
```

Or run it straight from the checkout with `python3 promptline`. See
[INSTALL.md](INSTALL.md) for details.

Promptline installs alongside Terminator without conflicts: it has its own
command, config directory (`~/.config/promptline`), D-Bus name and desktop
entry. The first time it starts, it copies your Terminator settings and
plugins into its own config directory. Your Terminator files are left as
they are.

## Setting up a model

Open **Preferences → Promptline**, or edit `~/.config/promptline/config`:

```ini
[global_config]
  promptline_llm_autocomplete = True
  promptline_api_key_file = ~/.config/promptline/openai-key
```

| Setting | Default | |
| --- | --- | --- |
| `promptline_enabled` | `True` | Everything below; off means plain Terminator |
| `promptline_shell_integration` | `True` | Hooks loaded into new bash/zsh shells |
| `promptline_autocomplete` | `True` | Local suggestions from history and paths |
| `promptline_llm_autocomplete` | `False` | Model-based prediction (sends context) |
| `promptline_predict_next` | `True` | Predict the next command on an empty prompt |
| `promptline_autocomplete_model` / `_reasoning` | `gpt-6-luna` / `xhigh` | Model for prediction |
| `promptline_agent_model` / `_reasoning` | `gpt-6-luna` / `xhigh` | Model for `@agent` |
| `promptline_base_url` | `https://api.openai.com/v1` | Any OpenAI-compatible server |
| `promptline_api_key_env` | `OPENAI_API_KEY` | Environment variable holding the key |
| `promptline_api_key_file` | *(empty)* | File holding the key (use `chmod 600`) |

**Local models.** Point `promptline_base_url` at an OpenAI-compatible server
such as Ollama (`http://localhost:11434/v1`) or LM Studio. A local server
needs no key.

**zsh-autosuggestions and fish.** Promptline never draws over another
suggestion, so a shell plugin's history match takes precedence. To let
Promptline's predictions lead, skip the plugin inside Promptline:

```zsh
# in ~/.zshrc, before oh-my-zsh is loaded
[[ -n $PROMPTLINE ]] && plugins=(${plugins:#zsh-autosuggestions})
```

## How it works

Promptline starts bash and zsh with a small integration script that runs
after your own startup files. The script tells the terminal when a prompt
is drawn, where input begins, and when a command starts and how it exits.
Promptline then reads what you've typed straight from the screen, so history
recall, Tab completion and paste are all reflected. Suggestions are drawn on
a transparent layer over the terminal; nothing is sent to the shell until
you accept one. See [`doc/promptline-plan.md`](doc/promptline-plan.md) for
the design.

Known limits: `@agent` commands run in a fresh shell (your aliases aren't
available, and `cd` doesn't carry over; that's what "place on prompt" is
for). Shells inside ssh or tmux don't get the integration.

## Relationship to Terminator

Promptline is a downstream of Terminator. It regularly merges upstream
releases to pick up fixes, as described in [`doc/UPSTREAM.md`](doc/UPSTREAM.md).
All of Promptline's own code is in `promptlinelib/promptline/`, and the rest
of the tree stays as close to Terminator as possible. Terminator's original
README is in [`README.terminator.md`](README.terminator.md).

### Credits

Promptline exists because of Terminator. Terminator was started by Chris
Jones in 2007, maintained by Stephen Boddy from 2014 to 2020 and since then
by Matt Rose, with contributions from many others listed in
[AUTHORS](AUTHORS). Thank you.

The code Promptline inherits remains theirs: its copyright notices and
license are kept as they are, and the full Terminator history, with its
authors, is part of this repository's history. Promptline is based on
Terminator 2.1.6 (upstream commit `9f2d0b6c`).

## Development

```sh
xvfb-run -a pytest                 # all tests, including real bash/zsh sessions
python3 promptline -u -d           # run without D-Bus hand-off, with debug output
```

## License

GPL-2.0-only, like Terminator. See [COPYING](COPYING).
