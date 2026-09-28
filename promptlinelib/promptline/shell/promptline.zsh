# Promptline shell integration for zsh (GPL v2 only)
#
# Sourced from zdotdir/.zshenv for interactive shells. Hooks are finalised
# on the first prompt, after the user's .zshrc has run, so themes and
# plugin managers can't displace them. Marks are described in
# promptlinelib/promptline/marks.py.

[[ -o interactive && -z $_PROMPTLINE_LOADED ]] || return 0
typeset -g _PROMPTLINE_LOADED=1
typeset -g _promptline_running=0 _promptline_last_pwd=

_promptline_mark() {
    builtin printf '\e]666;vte.ext.promptline.%s=%s\e\\' "$1" "$2"
}

_promptline_report_cwd() {
    [[ $PWD == $_promptline_last_pwd ]] && return
    _promptline_last_pwd=$PWD
    local out= c
    for c in ${(s::)PWD}; do
        case $c in
            [a-zA-Z0-9/._~-]) out+=$c ;;
            *) builtin printf -v c '%%%02X' "'$c"; out+=$c ;;
        esac
    done
    builtin printf '\e]7;file://%s%s\e\\' "$HOST" "$out"
}

_promptline_precmd() {
    local ret=$?
    if (( _promptline_running )); then
        _promptline_running=0
        _promptline_mark done $ret
    fi
    _promptline_report_cwd
    return $ret
}

_promptline_preexec() {
    _promptline_running=1
    _promptline_mark exec "$(builtin print -rn -- "$1" | base64 | tr -d '\n')"
}

# zle-line-init runs once the prompt is on screen with the cursor at the
# start of the input: exactly where the input anchor belongs.
_promptline_line_init() {
    local expanded=${(%)PS1}
    local newlines=${expanded//[^$'\n']/}
    _promptline_mark prompt $(( ${#newlines} + 1 ))
    _promptline_mark input 1
}

# How much of the line follows the cursor: history search can leave the
# cursor at the start of a recalled line
_promptline_redraw() {
    _promptline_mark after ${#RBUFFER}
}

_promptline_setup() {
    precmd_functions=(${precmd_functions:#_promptline_setup})
    # First in line, so it sees the real exit status
    precmd_functions=(_promptline_precmd ${precmd_functions:#_promptline_precmd})
    preexec_functions+=(_promptline_preexec)
    autoload -Uz add-zle-hook-widget
    add-zle-hook-widget zle-line-init _promptline_line_init
    add-zle-hook-widget zle-line-pre-redraw _promptline_redraw
    _promptline_report_cwd
}

# Terminator runs this when Enter is pressed on an "@agent ..." line: put
# what the user typed into history, then start the agent
_promptline_agent() {
    local request=$PROMPTLINE_RUNTIME/$1
    if [[ -r $request.query ]]; then
        builtin print -rs -- "@agent $(<$request.query)"
        command rm -f -- $request.query
    fi
    command "$PROMPTLINE_PYTHON" "$PROMPTLINE_AGENT" $request.json
}

# ...and keep the launcher line itself out of history
_promptline_addhistory() {
    [[ $1 != ' _promptline_agent '* ]]
}
zshaddhistory_functions+=(_promptline_addhistory)

precmd_functions+=(_promptline_setup)
