# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""promptline_defaults.py - defaults for Promptline's [global_config] keys

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
}
