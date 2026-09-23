# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""Keep the test run away from the developer's real configuration: some
tests save config (e.g. the Preferences window's config_cur snapshot)."""

import os
import tempfile


def pytest_configure(config):
    os.environ['XDG_CONFIG_HOME'] = tempfile.mkdtemp(prefix='promptline-test-')
