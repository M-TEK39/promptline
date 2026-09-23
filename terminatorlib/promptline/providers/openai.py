# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""openai.py - OpenAI Chat Completions, and compatible servers

Uses only the standard library. The same wire format is served by Ollama,
LM Studio, vLLM and others, so pointing promptline_base_url at one of those
works without a key.

>>> OpenAIProvider.needs_key('https://api.openai.com/v1')
True
>>> OpenAIProvider.needs_key('http://localhost:11434/v1')
False
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from . import ProviderError


class OpenAIProvider(object):
    """Talks to {base_url}/chat/completions"""
    def __init__(self, base_url, api_key, model, reasoning_effort=''):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.reasoning_effort = reasoning_effort

    @staticmethod
    def needs_key(base_url):
        host = urllib.parse.urlparse(base_url).hostname or ''
        return host not in ('localhost', '127.0.0.1', '::1')

    def complete(self, messages, max_tokens=256, timeout=15):
        """Return the reply text for messages"""
        body = {'model': self.model, 'messages': messages,
                'max_completion_tokens': max_tokens}
        if self.reasoning_effort:
            body['reasoning_effort'] = self.reasoning_effort
        reply = self._post('/chat/completions', body, timeout)
        try:
            return reply['choices'][0]['message'].get('content') or ''
        except (KeyError, IndexError, TypeError):
            raise ProviderError('unexpected reply from %s' % self.base_url)

    def _post(self, path, body, timeout):
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = 'Bearer ' + self.api_key
        request = urllib.request.Request(self.base_url + path,
                                         data=json.dumps(body).encode(),
                                         headers=headers, method='POST')
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as ex:
            raise ProviderError('%s: %s' % (ex.code, _error_message(ex)),
                                auth=ex.code in (401, 403, 404))
        except (urllib.error.URLError, OSError, ValueError) as ex:
            raise ProviderError(str(getattr(ex, 'reason', ex)))


def _error_message(http_error):
    """The API's own explanation, if it sent one"""
    try:
        detail = json.loads(http_error.read().decode('utf-8'))
        return detail['error']['message']
    except (ValueError, KeyError, TypeError, OSError):
        return http_error.reason
