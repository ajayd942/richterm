# Build a POSIX-shell command containing only our portable presentation profile.
_option3_bootstrap() {
  local profile_dir="$HOME/.config/terminal-option3" profile launcher
  profile=$(<"$profile_dir/kafka-stream.sh")$'\n'$(<"$profile_dir/remote-profile.sh") || return
  if [[ -n ${RICHTERM_TOKEN:-} ]]; then
    profile+=$'\n'"_option3_view_token=${(qq)RICHTERM_TOKEN}"$'\n'$(<"$profile_dir/proxy-remote.sh")
  fi
  launcher=$(<"$profile_dir/remote-start.sh") || return
  # Quote each argument for the destination shell, including embedded newlines.
  print -r -- "sh -c ${(qq)launcher} option3 ${(qq)profile} ${(qq)1}"
}

_option3_docker_exec() {
  local -a original=("$@")
  local -i interactive=0 tty_flag=0 compose=0 no_tty=0
  if [[ $1 == compose ]]; then compose=1; shift
  elif [[ $1 == container ]]; then shift; fi
  shift # exec
  while (( $# )); do
    case "$1" in
      -it|-ti) interactive=1; tty_flag=1 ;;
      -i|--interactive|--interactive=true) interactive=1 ;;
      -t|--tty|--tty=true) tty_flag=1 ;;
      -T|--no-tty) no_tty=1 ;;
      -w|-u|-e|--workdir|--user|--env|--env-file|--detach-keys|--index)
        (( $# >= 2 )) || break
        shift ;;
      --workdir=*|--user=*|--env=*|--env-file=*|--detach-keys=*|--index=*|--privileged|-w?*|-u?*|-e?*) ;;
      --) shift; break ;;
      -*) command docker "${original[@]}"; return $? ;;
      *) break ;;
    esac
    shift
  done
  if (( ! no_tty && (compose || (interactive && tty_flag)) && $# == 2 )) && [[ ${2:t} == (bash|sh|ash|dash|zsh) ]]; then
    # Replace only the final shell argument. Preserve all Docker options and their order.
    command docker "${original[@]:0:${#original}-1}" sh -c "$(_option3_bootstrap "$2")"
    return $?
  fi
  # A one-shot report never enters a remote shell. Render its stdout on the Mac.
  local -a report_args=("${original[@]}")
  if (( compose && ! no_tty )); then
    report_args=(compose exec -T "${original[@]:2}")
  fi
  if (( ! interactive && ! tty_flag )) && [[ -t 1 && -z ${NO_COLOR:-} && ${2:t} == kafka-console-consumer.sh ]]; then
    setopt localoptions pipefail
    source "$HOME/.config/terminal-option3/kafka-stream.sh"
    command docker "${report_args[@]}" | _option3_kafka_events
    return $?
  fi
  if (( ! interactive && ! tty_flag )) && [[ -t 1 && -z ${NO_COLOR:-} && ${2:t} == kafka-*.sh ]]; then
    local arg
    for arg in "${@:3}"; do
      case "$arg" in
        --describe|describe|--list|--help|--create)
          setopt localoptions pipefail
          command docker "${report_args[@]}" | pretty
          return $? ;;
      esac
    done
  fi
  command docker "${original[@]}"
}

_option3_ssh() {
  local -a opts
  while (( $# > 1 )); do
    case "$1" in
      -p|-i|-l|-J|-F) (( $# >= 3 )) || break; opts+=("$1" "$2"); shift 2 ;;
      *) break ;;
    esac
  done
  if (( $# == 1 )) && [[ -t 0 && -t 1 && $1 != -* ]]; then
    local settings
    settings=$(command ssh -G "${opts[@]}" "$1" 2>/dev/null) &&
      ! command grep -Eq '^(requesttty no|sessiontype (none|subsystem)|stdinnull yes|forkafterauthentication yes|remotecommand .+)$' <<<"$settings" &&
      { command ssh -t "${opts[@]}" "$1" "$(_option3_bootstrap login)"; return $?; }
  fi
  command ssh "${opts[@]}" "$@"
}
ssh() { _option3_ssh "$@"; }
