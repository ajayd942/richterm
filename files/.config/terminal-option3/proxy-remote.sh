# Optional command boundaries for a locally running richterm session.
_option3_view_begin() { printf '\033]777;%s;R\007' "$_option3_view_token" > /dev/tty; }
_option3_view_end() { printf '\033]777;%s;E\007' "$_option3_view_token" > /dev/tty; }
if [ -n "${ZSH_VERSION:-}" ]; then
  autoload -Uz add-zsh-hook
  add-zsh-hook preexec _option3_view_begin
  add-zsh-hook precmd _option3_view_end
elif [ -n "${BASH_VERSION:-}" ]; then
  PS0="${PS0-}$(printf '\033]777;%s;R\007' "$_option3_view_token")"
  if [ "$(declare -p PROMPT_COMMAND 2>/dev/null | cut -c1-10)" = 'declare -a' ]; then
    eval 'PROMPT_COMMAND+=(_option3_view_end)'
  else
    PROMPT_COMMAND="${PROMPT_COMMAND:+$PROMPT_COMMAND$'\n'}_option3_view_end"
  fi
fi
