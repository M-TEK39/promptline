# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""providers - language model backends

Messages use the common role/content dict shape ({'role': 'system' |
'user' | 'assistant', 'content': str}). A provider turns them into a reply.
Only an OpenAI-compatible provider exists today; it also covers local
servers such as Ollama or LM Studio through promptline_base_url.

API keys are never stored in Terminator's config. They come from the
environment variable named by promptline_api_key_env, or from a file named
by promptline_api_key_file (useful when Terminator is started from a
desktop launcher that doesn't see your shell's environment).

>>> resolve_api_key({'promptline_api_key_env': 'PL_TEST_KEY',
...                  'promptline_api_key_file': ''}, {'PL_TEST_KEY': ' k1 '})
'k1'
>>> resolve_api_key({'promptline_api_key_env': 'PL_TEST_KEY',
...                  'promptline_api_key_file': ''}, {}) is None
True
"""

import os

from ...config import Config
from ...util import err


class ProviderError(Exception):
    """A request failed. auth is True when retrying won't help until the
    user fixes their key or settings."""
    def __init__(self, message, auth=False):
        Exception.__init__(self, message)
        self.auth = auth


def resolve_api_key(config, environ=None):
    """Find the API key without ever writing it anywhere"""
    environ = os.environ if environ is None else environ
    name = config['promptline_api_key_env']
    if name and environ.get(name, '').strip():
        return environ[name].strip()
    path = config['promptline_api_key_file']
    if path:
        try:
            with open(os.path.expanduser(path), encoding='utf-8') as handle:
                key = handle.read().strip()
            return key or None
        except OSError as ex:
            err('promptline: unable to read API key file %s: %s' %
                (path, ex.strerror))
    return None


def make_provider(purpose):
    """Return a provider for 'autocomplete' or 'agent', or None if one
    isn't configured (no key for a hosted API)"""
    config = Config()
    name = config['promptline_provider']
    if name != 'openai':
        err('promptline: unknown provider %r' % name)
        return None
    from .openai import OpenAIProvider
    base_url = config['promptline_base_url']
    key = resolve_api_key(config)
    if key is None and OpenAIProvider.needs_key(base_url):
        return None
    return OpenAIProvider(base_url, key,
                          config['promptline_%s_model' % purpose],
                          config['promptline_%s_reasoning' % purpose])
