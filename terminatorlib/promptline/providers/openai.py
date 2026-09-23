# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""openai.py - OpenAI, and servers compatible with its Chat Completions API

Uses only the standard library. The same wire format is served by Ollama,
LM Studio, vLLM and others, so pointing promptline_base_url at one of those
works without a key.

Callers use Chat Completions-shaped messages. Requests with tools go to
OpenAI's Responses API instead, since OpenAI's reasoning models only accept
tools there; the messages are translated both ways, and the model's
(encrypted) reasoning is carried along in a '_reasoning' key on assistant
messages so it survives between tool calls.

>>> to_responses_input([
...     {'role': 'user', 'content': 'hi'},
...     {'role': 'assistant', 'content': None, '_reasoning': [{'type': 'reasoning', 'id': 'r1'}],
...      'tool_calls': [{'id': 'c1', 'type': 'function',
...                      'function': {'name': 'run_command', 'arguments': '{}'}}]},
...     {'role': 'tool', 'tool_call_id': 'c1', 'content': 'ok'}])
[{'role': 'user', 'content': 'hi'}, {'type': 'reasoning', 'id': 'r1'}, {'type': 'function_call', 'call_id': 'c1', 'name': 'run_command', 'arguments': '{}'}, {'type': 'function_call_output', 'call_id': 'c1', 'output': 'ok'}]
>>> reply = from_responses_output([
...     {'type': 'reasoning', 'id': 'r2', 'summary': []},
...     {'type': 'message', 'role': 'assistant',
...      'content': [{'type': 'output_text', 'text': 'Checking.'}]},
...     {'type': 'function_call', 'call_id': 'c2', 'name': 'run_command',
...      'arguments': '{"command": "uname -r"}'}])
>>> reply['content'], reply['tool_calls'][0]['function']['name'], len(reply['_reasoning'])
('Checking.', 'run_command', 1)

>>> OpenAIProvider.needs_key('https://api.openai.com/v1')
True
>>> OpenAIProvider.needs_key('http://localhost:11434/v1')
False
>>> OpenAIProvider('http://x', None, 'm', 'xhigh').budget(256, 15)
(16640, 120)
>>> OpenAIProvider('http://x', None, 'm', '').budget(256, 15)
(256, 15)
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from . import ProviderError

# Reasoning tokens count against max_completion_tokens, so each effort level
# needs room to think on top of the visible reply, and time to do it in
REASONING_BUDGET = {
    'minimal': (512, 30),
    'low': (2048, 30),
    'medium': (4096, 60),
    'high': (8192, 90),
    'xhigh': (16384, 120),
}


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

    def uses_responses_api(self):
        """Only OpenAI itself serves the Responses API"""
        return urllib.parse.urlparse(self.base_url).hostname == \
            'api.openai.com'

    def budget(self, max_tokens, timeout):
        """(token limit, timeout) allowing for the reasoning effort"""
        extra_tokens, min_timeout = REASONING_BUDGET.get(
            self.reasoning_effort, (0, 0))
        return max_tokens + extra_tokens, max(timeout, min_timeout)

    def complete(self, messages, max_tokens=256, timeout=15):
        """Return the reply text for messages. max_tokens is the size of the
        visible reply; room for reasoning is added on top."""
        return self.chat(messages, max_tokens=max_tokens,
                         timeout=timeout)['content'] or ''

    def chat(self, messages, tools=None, max_tokens=4096, timeout=60):
        """Return the assistant message for messages, as a dict with
        'content' and, if the model called tools, 'tool_calls' (the
        OpenAI shape, which is also what the agent keeps its history in)"""
        max_tokens, timeout = self.budget(max_tokens, timeout)
        if tools and self.uses_responses_api():
            return self._responses(messages, tools, max_tokens, timeout)
        body = {'model': self.model,
                'messages': [dict((k, v) for k, v in m.items()
                                  if not k.startswith('_'))
                             for m in messages],
                'max_completion_tokens': max_tokens}
        if self.reasoning_effort:
            body['reasoning_effort'] = self.reasoning_effort
        if tools:
            body['tools'] = tools
        reply = self._post('/chat/completions', body, timeout)
        try:
            message = reply['choices'][0]['message']
        except (KeyError, IndexError, TypeError):
            raise ProviderError('unexpected reply from %s' % self.base_url)
        result = {'role': 'assistant', 'content': message.get('content')}
        if message.get('tool_calls'):
            result['tool_calls'] = message['tool_calls']
        return result

    def _responses(self, messages, tools, max_tokens, timeout):
        body = {'model': self.model,
                'input': to_responses_input(messages),
                'tools': [dict(tool['function'], type='function')
                          for tool in tools],
                'max_output_tokens': max_tokens,
                # Nothing is kept on OpenAI's side; the reasoning comes back
                # encrypted so it can be passed along with the next request
                'store': False,
                'include': ['reasoning.encrypted_content']}
        if self.reasoning_effort:
            body['reasoning'] = {'effort': self.reasoning_effort}
        reply = self._post('/responses', body, timeout)
        if not isinstance(reply.get('output'), list):
            raise ProviderError('unexpected reply from %s' % self.base_url)
        return from_responses_output(reply['output'])

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


def to_responses_input(messages):
    """Chat Completions-shaped messages to Responses API input items"""
    items = []
    for message in messages:
        role = message.get('role')
        if role == 'tool':
            items.append({'type': 'function_call_output',
                          'call_id': message.get('tool_call_id'),
                          'output': message.get('content') or ''})
            continue
        items.extend(message.get('_reasoning') or [])
        if message.get('content'):
            items.append({'role': role, 'content': message['content']})
        for call in message.get('tool_calls') or []:
            items.append({'type': 'function_call', 'call_id': call['id'],
                          'name': call['function']['name'],
                          'arguments': call['function']['arguments']})
    return items


def from_responses_output(output):
    """Responses API output items to one Chat Completions-shaped message"""
    texts, calls, reasoning = [], [], []
    for item in output:
        kind = item.get('type')
        if kind == 'message':
            texts.extend(part.get('text', '') for part in item.get('content', [])
                         if part.get('type') == 'output_text')
        elif kind == 'function_call':
            calls.append({'id': item.get('call_id'), 'type': 'function',
                          'function': {'name': item.get('name'),
                                       'arguments': item.get('arguments')}})
        elif kind == 'reasoning':
            reasoning.append(item)
    message = {'role': 'assistant', 'content': '\n'.join(texts) or None}
    if calls:
        message['tool_calls'] = calls
    if reasoning:
        message['_reasoning'] = reasoning
    return message
