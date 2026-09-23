Installing Promptline
=====================

Promptline isn't packaged by distributions yet. Run it from a checkout, or
install it for your user.

Dependencies
------------

Debian/Ubuntu:

    sudo apt install python3-gi python3-gi-cairo python3-psutil python3-configobj \
      gir1.2-gtk-3.0 gir1.2-vte-2.91 gir1.2-keybinder-3.0 gir1.2-notify-0.7 \
      gettext intltool

Suggestions, prediction and `@agent` need a VTE with terminal-property
support (0.78 or newer). On an older VTE Promptline runs as plain Terminator.

From a checkout
---------------

    git clone https://github.com/M-TEK39/promptline.git
    cd promptline
    python3 promptline

Installing
----------

    python3 setup.py build
    python3 setup.py install --user --record=install-files.txt

This installs the `promptline`, `promptline-agent` and `promptline-remote`
commands, the desktop entry, icons and man pages. Use `--without-gettext`
if gettext/intltool aren't available (the interface is then English only).
To uninstall:

    python3 setup.py uninstall --manifest=install-files.txt

Promptline installs alongside Terminator: it uses its own command, config
directory (`~/.config/promptline`), D-Bus name and desktop entry. On first
start it copies your Terminator settings.

Terminator's own install notes, which cover its distribution packages, are
in [INSTALL.terminator.md](INSTALL.terminator.md).
