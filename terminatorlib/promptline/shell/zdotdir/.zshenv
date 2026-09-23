# Promptline zsh bootstrap (GPL v2 only)
#
# Terminator points ZDOTDIR here so zsh reads this file first. Put the
# user's ZDOTDIR back straight away, so their .zshenv, .zprofile, .zshrc and
# .zlogin load exactly as they normally would, then add Promptline's hooks.

if [[ -n ${PROMPTLINE_ZDOTDIR+set} ]]; then
    ZDOTDIR=$PROMPTLINE_ZDOTDIR
    unset PROMPTLINE_ZDOTDIR
else
    unset ZDOTDIR
fi

typeset -g _promptline_integration=${${(%):-%x}:A:h:h}/promptline.zsh

[[ -f ${ZDOTDIR:-$HOME}/.zshenv ]] && builtin source ${ZDOTDIR:-$HOME}/.zshenv

[[ -o interactive && -r $_promptline_integration ]] && builtin source $_promptline_integration
unset _promptline_integration
