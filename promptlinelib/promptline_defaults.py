# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""promptline_defaults.py - Promptline's configuration defaults

Kept out of config.py's DEFAULTS literal, where upstream Terminator adds its
own options, so that merging upstream releases doesn't conflict. This module
must not import anything from promptlinelib: config.py imports it.
"""

GLOBAL_DEFAULTS = {
    'promptline_enabled': True,
    'promptline_shell_integration': True,
    'promptline_autocomplete': True,
    # Model-based command prediction sends terminal context to the provider,
    # so it is opt-in
    'promptline_llm_autocomplete': False,
    'promptline_predict_next': True,
    'promptline_provider': 'openai',
    'promptline_base_url': 'https://api.openai.com/v1',
    'promptline_api_key_env': 'OPENAI_API_KEY',
    'promptline_api_key_file': '',
    'promptline_autocomplete_model': 'gpt-6-luna',
    'promptline_autocomplete_reasoning': 'xhigh',
    'promptline_agent_model': 'gpt-6-luna',
    'promptline_agent_reasoning': 'xhigh',
    # ask | auto-review | full. Full also needs the user's guardrails
    'promptline_agent_mode': 'ask',
    'promptline_review_reasoning': 'medium',
}

# Changes to Terminator's own profile defaults
PROFILE_DEFAULTS = {
    # The focused terminal's titlebar: dark grey instead of Terminator's
    # red. Blue stays reserved for terminals receiving broadcast input
    # (title_receive_bg_color), so the two remain easy to tell apart.
    'title_transmit_bg_color': '#2e3436',
}
