# Promptline shell integration for bash (GPL v2 only)
#
# Loaded by Terminator through `bash --rcfile` in place of ~/.bashrc; loads
# the user's normal startup files first, then reports prompt/command marks
# to the terminal (see promptlinelib/promptline/marks.py).

if [[ -n $PROMPTLINE_BASH_LOGIN ]]; then
    # Terminator asked for a login shell, which would ignore --rcfile, so
    # read the login files ourselves in bash's usual order.
    unset PROMPTLINE_BASH_LOGIN
    [[ -r /etc/profile ]] && builtin source /etc/profile
    for _promptline_f in ~/.bash_profile ~/.bash_login ~/.profile; do
        if [[ -r $_promptline_f ]]; then
            builtin source "$_promptline_f"
            break
        fi
    done
    unset _promptline_f
elif [[ -r ~/.bashrc ]]; then
    builtin source ~/.bashrc
fi

if [[ $- == *i* && -z $_PROMPTLINE_LOADED && ${BASH_VERSINFO[0]} -ge 4 ]]; then
    _PROMPTLINE_LOADED=1

    _promptline_mark() {
        builtin printf '\e]666;vte.ext.promptline.%s=%s\e\\' "$1" "$2"
    }

    _promptline_report_cwd() {
        [[ $PWD == "$_promptline_last_pwd" ]] && return
        _promptline_last_pwd=$PWD
        local path=$PWD out='' c i
        for (( i = 0; i < ${#path}; i++ )); do
            c=${path:i:1}
            case $c in
                [a-zA-Z0-9/._~-]) out+=$c ;;
                *) builtin printf -v c '%%%02X' "'$c"; out+=$c ;;
            esac
        done
        builtin printf '\e]7;file://%s%s\e\\' "${HOSTNAME}" "$out"
    }

    # Runs first in PROMPT_COMMAND, while $? is still the command's status.
    _promptline_precmd() {
        local ret=$?
        _promptline_mark done "$ret"
        return "$ret"
    }

    # Runs last, after themes have set PS1 for this prompt.
    _promptline_prompt() {
        local ret=$? rows=1 expanded newlines
        _promptline_report_cwd
        if (( BASH_VERSINFO[0] > 4 || BASH_VERSINFO[1] >= 4 )); then
            expanded=${PS1@P}
            newlines=${expanded//[!$'\n']/}
            rows=$(( ${#newlines} + 1 ))
        fi
        _promptline_mark prompt "$rows"
        [[ $PS1 == *"$_promptline_input_mark"* ]] || PS1+=$_promptline_input_mark
        return "$ret"
    }

    # Terminator runs this when Enter is pressed on an "@agent ..." line: put
    # what the user typed into history, then start the agent
    _promptline_agent() {
        local request=$PROMPTLINE_RUNTIME/$1
        if [[ -r $request.query ]]; then
            builtin history -s "@agent $(<"$request.query")"
            command rm -f -- "$request.query"
        fi
        command "$PROMPTLINE_PYTHON" "$PROMPTLINE_AGENT" "$request.json"
    }
    # ...and keep the launcher line itself out of history
    HISTIGNORE="${HISTIGNORE:+$HISTIGNORE:}[ ]_promptline_agent *"

    _promptline_input_mark='\[\e]666;vte.ext.promptline.input=1\e\\\]'
    # bash can't cheaply tell us the command text; the terminal reads it
    # off the screen. PS0 is printed just before each command runs; prepend,
    # since appending can pair our backslash with a stray one at its end.
    PS0='\e]666;vte.ext.promptline.exec=-\e\\'"${PS0:-}"

    if [[ $(declare -p PROMPT_COMMAND 2>/dev/null) == "declare -a"* ]]; then
        PROMPT_COMMAND=(_promptline_precmd "${PROMPT_COMMAND[@]}" _promptline_prompt)
    else
        _promptline_pc=${PROMPT_COMMAND%"${PROMPT_COMMAND##*[![:space:];]}"}
        PROMPT_COMMAND="_promptline_precmd;${_promptline_pc:+ $_promptline_pc;} _promptline_prompt"
        unset _promptline_pc
    fi
fi
