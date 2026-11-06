# Option 3's interactive tools. Nothing here runs until a command is used.
richterm() { "$HOME/.local/bin/richterm" "$@"; }
rtest() { "$HOME/.config/terminal-option3/render-env/bin/python" "$HOME/.config/terminal-option3/inspect_cli.py" rtest "$@"; }
rwatch() { "$HOME/.config/terminal-option3/render-env/bin/python" "$HOME/.config/terminal-option3/inspect_cli.py" rwatch "$@"; }
rhttp() { "$HOME/.config/terminal-option3/render-env/bin/python" "$HOME/.config/terminal-option3/inspect_cli.py" rhttp "$@"; }
jview() { "$HOME/.config/terminal-option3/render-env/bin/python" "$HOME/.config/terminal-option3/inspect_cli.py" jview "$@"; }
if [[ -n ${RICHTERM_TOKEN:-} ]]; then
  typeset -g +x RICHTERM_TOKEN  # Keep the framing token local to this shell.
  autoload -Uz add-zsh-hook
  _richterm_begin() { builtin printf '\033]777;%s;B\007' "$RICHTERM_TOKEN" > /dev/tty; }
  _richterm_end() {
    # Ghostty registers its title/cursor hook after zshrc. Mark output only
    # after those terminal controls, or the proxy will bypass the entire job.
    preexec_functions=("${(@)preexec_functions:#_richterm_begin}" _richterm_begin)
    builtin printf '\033]777;%s;E\007' "$RICHTERM_TOKEN" > /dev/tty
  }
  add-zsh-hook preexec _richterm_begin
  add-zsh-hook precmd _richterm_end
fi
csearch() {
  "$HOME/.local/bin/term-code-search" "$@"
}

# Render human-facing output while letting pipes and option-heavy invocations
# use the system binaries.
ls() {
  local arg
  for arg in "$@"; do
    if [[ $arg == -* ]]; then
      command ls "$@"
      return
    fi
  done
  if [[ -t 1 ]]; then
    command eza --icons=auto --group-directories-first -- "$@"
  else
    command ls "$@"
  fi
}

cat() {
  if [[ -t 1 && $# == 1 && $1 != -* && -f $1 ]]; then
    command bat --paging=never -- "$1"
  else
    command cat "$@"
  fi
}

pretty() {
  case "${1:-auto}" in
    auto|table|csv|log) "$HOME/.config/terminal-option3/render-env/bin/python" "$HOME/.config/terminal-option3/render.py" "${1:-auto}" ;;
    json) command jq '.' ;;
    help) "$HOME/.config/terminal-option3/render-env/bin/python" "$HOME/.config/terminal-option3/render.py" help ;;
    yaml|xml) command bat --paging=never --style=plain --language="$1" ;;
    *) print -u2 'Pipe output into pretty with a format: auto, help, json, csv, log, yaml, xml, or table'; return 2 ;;
  esac
}

_output_dispatch() {
  local tool=$1 mode=native
  shift
  if [[ $tool == docker && -t 0 && -t 1 && ( $1 == exec || ( $1 == (container|compose) && $2 == exec ) ) ]]; then
    _option3_docker_exec "$@"
    return $?
  fi
  if [[ -t 1 && -z ${NO_COLOR:-} ]]; then
    if [[ $# == 1 && $1 == --help ]] ||
       [[ $tool == docker && $# == 1 && ( $1 == -h || $1 == help ) ]] ||
       [[ $tool == docker && $# == 2 && ( $1 == help || ( $1 != -* && $2 == -h ) ) ]] ||
       [[ $tool == curl && ( $# == 1 || $# == 2 ) && ( $1 == -h || $1 == --help ) ]] ||
       [[ $# == 2 && $1 != -* && $2 == --help && $tool == (docker|kubectl|gh|brew|pip|pip3|cargo|helm|terraform) ]] ||
       [[ $# == 1 && $1 == -h && $tool == (rg|fd|bat|jq|kubectl|gh|pip|pip3|python|python3|java|mvn|gradle|rsync) ]]; then
      mode=help
    else
      if [[ $tool == docker && ( $1 == logs || ( $1 == (compose|container) && $2 == logs ) ) ]]; then
        setopt localoptions pipefail
        if [[ -t 2 ]]; then
          command docker "$@" 2>&1 | pretty log
        else
          command docker "$@" | pretty log
        fi
        return $?
      fi
      case "$tool ${(j: :)@}" in
        'docker ps'|'docker ps -a'|'docker ps --all'|'docker container ls'|'docker image ls'|'docker context ls'|'docker volume ls'|'docker network ls'|'docker compose ps'|'docker compose ls'|'brew services list') mode=auto ;;
        'docker images') mode=images ;;
        'docker info'|'docker version') mode=grc ;;
        'pip list'|'pip3 list'|'kubectl config get-contexts'|'kubectl api-resources'|'kubectl top nodes'|'kubectl top pods'|'helm list'|'sw_vers '|'npm list --json'|'npm ls --json'|'pnpm list --json'|'terraform output -json') mode=auto ;;
      esac
      if [[ $tool == kubectl && $1 == get && -n $2 && $2 != -* ]]; then
        local arg
        mode=auto
        for arg in "${@:3}"; do
          case "$arg" in
            -A|--all-namespaces|-n|--namespace|-l|--selector|--namespace=*|--selector=*|wide) ;;
            -o|--output) mode=native; break ;;
            -*) mode=native; break ;;
          esac
        done
        if [[ $# == 4 && $3 == -o ]]; then
          case "$4" in wide) mode=auto ;; json) mode=json ;; yaml) mode=yaml ;; esac
        fi
      fi
      if [[ $tool == docker && $# == 2 && $1 == inspect && $2 != -* ]]; then mode=json; fi
      case "$tool" in
        df|du|ps|uptime|dig|ifconfig|netstat|id|stat|traceroute|lsof|last|ping|ping6|whois|iostat) mode=grc ;;
        grep) mode=grep ;;
      esac
      if [[ $tool == docker && ( $1 == stats || ( $1 == container && $2 == stats ) ) ]]; then
        local -a stats_args
        if [[ $1 == stats ]]; then stats_args=("${@:2}"); else stats_args=("${@:3}"); fi
        local arg
        mode=stats
        for arg in "${stats_args[@]}"; do
          case "$arg" in
            --all|-a|--no-stream|--no-trunc) ;;
            -*) mode=native; break ;;
          esac
        done
      fi
    fi
  fi
  case "$mode" in
    auto) setopt localoptions pipefail
      if [[ $tool == docker && ( $1 == ps || "$1 $2" == 'container ls' ) ]]; then
        command docker "$@" --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' | pretty
      else
        command "$tool" "$@" | pretty
      fi ;;
    grep) command grep --color=auto "$@" ;;
    stats) "$HOME/.config/terminal-option3/render-env/bin/python" "$HOME/.config/terminal-option3/stats.py" "${stats_args[@]}" ;;
    native) command "$tool" "$@" ;;
    images) setopt localoptions pipefail; command docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}' | pretty table ;;
    grc) command grc --colour=auto "$tool" "$@" ;;
    *) setopt localoptions pipefail; command "$tool" "$@" | pretty "$mode" ;;
  esac
}

# Only wrap external commands, and never replace an existing user function.
typeset -ga _output_tools
_output_tools=(
  curl docker kubectl helm terraform aws gh brew
  git rg fd bat jq yq grep diff tar rsync
  npm pnpm yarn node pip pip3 python python3 java javac mvn gradle cargo
  df du ps uptime dig ifconfig netstat id stat traceroute
  lsof last ping ping6 whois iostat sw_vers
)
for _output_tool in "${_output_tools[@]}"; do
  if (( $+commands[$_output_tool] && ! $+functions[$_output_tool] )); then
    functions[$_output_tool]="_output_dispatch $_output_tool \"\$@\""
  fi
done
unset _output_tool
source "$HOME/.config/terminal-option3/remote.zsh"

# One entry point for a finite report from any external command.
show() {
  if (( $# == 0 )); then
    print 'Usage: show COMMAND [ARG ...]   |   COMMAND | pretty'
    return
  fi
  setopt localoptions pipefail
  if [[ -t 1 ]]; then
    command "$@" | pretty
  else
    command "$@"
  fi
}

y() {
  local location_file destination result
  location_file=$(mktemp -t yazi-cwd) || return 1
  {
    command yazi "$@" --cwd-file="$location_file"
    result=$?
    if (( result == 0 )); then
      IFS= read -r -d '' destination < "$location_file"
      if [[ -d $destination && $destination != $PWD ]]; then
        builtin cd -- "$destination" || return 1
      fi
    fi
    return $result
  } always {
    command rm -f -- "$location_file"
  }
}

codeview() {
  if (( $# )) || [[ ! -t 0 ]]; then
    command bat "$@"
    return
  fi
  local selected_file
  IFS= read -r -d '' selected_file < <(
    command fd --type f --hidden --exclude .git --print0 |
      command fzf --read0 --print0 --height=85% --border-label=' Read code ' \
        --preview-window='right,57%,<100(down,50%)' \
        --preview 'bat --paging=never --color=always --style=numbers,changes --line-range=:300 -- {}'
  ) || return 0
  command bat -- "$selected_file"
}

md() {
  local style="$HOME/.config/terminal-option3/markdown.json"
  if (( $# == 0 )); then
    command glow --style "$style" --tui .
  else
    command glow --style "$style" --pager -- "$@"
  fi
}

# In a narrow split, spend the available columns on the changed code.
gd() {
  local two_columns=false
  (( COLUMNS >= 125 )) && two_columns=true
  command git -c delta.side-by-side="$two_columns" diff "$@"
}
gds() { gd --staged "$@"; }

desk() {
  local selection
  local -a actions=(
    'y         Browse files and directories'
    'codeview  Read a source file'
    'csearch   Search text and open the matching line'
    'md        Read Markdown notes'
  )
  if command git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    actions+=('lg        Review Git changes')
  fi
  selection=$(printf '%s\n' "${actions[@]}" | command fzf \
    --border-label=' Developer tools ' --prompt='› ' --height='~14' \
    --no-multi --no-preview --header='Choose a tool or type to filter') || return 0
  case "$selection" in
    y\ *) y ;;
    codeview\ *) codeview ;;
    csearch\ *) csearch ;;
    md\ *) md ;;
    lg\ *) command lazygit ;;
  esac
}
