# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""approval.py - who decides whether an agent command may run

The agent asks its policy before every command. The only policy today asks
the user every time. Later modes (allow once for this session, trusted
command patterns, deny lists) are new policies; the agent loop and the
executor don't change.

>>> AskEveryTime().decide('rm -rf build')
'ask'
"""

ASK = 'ask'         # show Approve / Edit / Cancel
ALLOW = 'allow'     # run without asking
DENY = 'deny'       # refuse without asking


class AskEveryTime(object):
    """Every command needs the user's approval"""
    def decide(self, command):
        return ASK

    def remember(self, command, approved):
        """Called with the user's answer, for policies that learn"""
        pass
