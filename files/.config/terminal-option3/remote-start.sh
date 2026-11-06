# Run by sh -c on the destination. Data arrives in argv; stdin stays a TTY.
profile=$1
if [ "${TERM:-}" = xterm-ghostty ] && ! infocmp xterm-ghostty >/dev/null 2>&1; then
  export TERM=xterm-256color
fi
requested=$2
shell=$requested
[ "$requested" != login ] || shell=${SHELL:-/bin/sh}
case ${shell##*/} in bash|zsh|sh|ash|dash) ;; *) exec "$shell" -l ;; esac
umask_before=$(umask)
umask 077
dir=$(mktemp -d "${TMPDIR:-/tmp}/ghostty-session.XXXXXXXX") || exec "$shell" -i
trap 'rm -f "$dir/init" "$dir/.zshenv" "$dir/.zprofile" "$dir/.zshrc"; rmdir "$dir" 2>/dev/null' EXIT
case ${shell##*/} in
  bash)
    if [ "$requested" = login ]; then
      printf '%s\n' '[ ! -r /etc/profile ] || . /etc/profile' 'for f in "$HOME/.bash_profile" "$HOME/.bash_login" "$HOME/.profile"; do if [ -r "$f" ]; then . "$f"; break; fi; done' > "$dir/init"
    else
      printf '%s\n' 'if [ -r /etc/bash.bashrc ]; then . /etc/bash.bashrc; fi' 'if [ -r "$HOME/.bashrc" ]; then . "$HOME/.bashrc"; fi' > "$dir/init"
    fi
    printf '%s\n' "$profile" >> "$dir/init"
    umask "$umask_before"; "$shell" --rcfile "$dir/init" -i ;;
  zsh)
    export OPTION3_ZDOTDIR=${ZDOTDIR:-$HOME}
    for name in .zshenv .zprofile; do
      printf '%s\n' '_option3_tmp=$ZDOTDIR; ZDOTDIR=$OPTION3_ZDOTDIR' \
        "[[ ! -r \"\$ZDOTDIR/$name\" ]] || source \"\$ZDOTDIR/$name\"" \
        'OPTION3_ZDOTDIR=$ZDOTDIR; ZDOTDIR=$_option3_tmp; unset _option3_tmp' > "$dir/$name"
    done
    printf '%s\n' 'ZDOTDIR=$OPTION3_ZDOTDIR; unset OPTION3_ZDOTDIR' '[[ ! -r "$ZDOTDIR/.zshrc" ]] || source "$ZDOTDIR/.zshrc"' "$profile" > "$dir/.zshrc"
    umask "$umask_before"
    if [ "$requested" = login ]; then ZDOTDIR="$dir" "$shell" -il; else ZDOTDIR="$dir" "$shell" -i; fi ;;
  *)
    export OPTION3_OLD_ENV=${ENV:-}
    printf '%s\n' 'if [ -n "$OPTION3_OLD_ENV" ] && [ -r "$OPTION3_OLD_ENV" ]; then . "$OPTION3_OLD_ENV"; fi' 'ENV=$OPTION3_OLD_ENV; unset OPTION3_OLD_ENV' "$profile" > "$dir/init"
    umask "$umask_before"
    if [ "$requested" = login ]; then ENV="$dir/init" "$shell" -il; else ENV="$dir/init" "$shell" -i; fi ;;
esac
