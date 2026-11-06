# Session-only profile shared by interactive Docker and SSH shells.
if [ -n "${BASH_VERSION:-}" ]; then
  PS1='\[\033[1;35m\]\u@\h\[\033[0m\] \[\033[1;36m\]\w\[\033[0m\] \$ '
elif [ -n "${ZSH_VERSION:-}" ]; then
  PS1='%F{magenta}%n@%m%f %F{cyan}%~%f %# '
  eval 'ZSH_HIGHLIGHT_HIGHLIGHTERS=()'
else
  PS1='remote ${PWD} $ '
fi
export CLICOLOR=1
export COLORTERM="${COLORTERM:-truecolor}"
if [ -z "${BAT_PAGER:-}" ] && command less --help 2>&1 | command grep -q BusyBox; then
  export BAT_PAGER='less -R'
fi
if [ -x "$HOME/.local/bin/bat" ] && ! command -v bat >/dev/null 2>&1; then
  bat() { "$HOME/.local/bin/bat" "$@"; }
fi
: "${LS_COLORS:=di=1;36:ln=1;35:ex=1;32:*.java=1;33:*.py=1;32:*.md=1;35}"
export LS_COLORS

# Use the tools and flags the destination actually supports.
if command -v eza >/dev/null 2>&1; then
  alias ll='eza --long --header --icons=auto --git'
else
  if command ls --color=auto -d . >/dev/null 2>&1; then alias ls='ls --color=auto'; fi
  alias ll='ls -lh'
fi
if command grep --color=auto x /dev/null 2>/dev/null; then :
elif [ "$?" = 1 ]; then alias grep='grep --color=auto'; fi

pretty() {
  if [ "${1:-}" = json ]; then
    if command -v jq >/dev/null 2>&1; then command jq .; return; fi
    if command -v python3 >/dev/null 2>&1; then command python3 -m json.tool; return; fi
  fi
  if [ -n "${NO_COLOR:-}" ] || [ ! -t 1 ] || ! command -v awk >/dev/null 2>&1; then
    command cat
    return
  fi
  command awk -v screen="${COLUMNS:-80}" '
    BEGIN { esc=sprintf("%c",27); cyan=esc "[1;96m"; green=esc "[92m"; red=esc "[91m"; yellow=esc "[93m"; dim=esc "[90m"; off=esc "[0m" }
    index($0,esc) { print; next }
    # Find the real column offsets from an uppercase CLI header, even after a blank line.
    /^[A-Z#][A-Z0-9_# -]*$/ && NF >= 3 && /  +/ {
      rest=$0; offset=0; cols=0
      while(match(rest,/[^ ]+/)) {
        start[++cols]=offset+RSTART; column[cols]=substr(rest,RSTART,RLENGTH)
        offset+=RSTART+RLENGTH-1; rest=substr($0,offset+1)
      }
      if (cols >= 3) {
        wide=(start[cols]+length(column[cols])>screen || cols>=8)
        if (!wide) print cyan $0 off
        record=0; next
      }
    }
    cols && /^[[:space:]]*$/ { cols=0; print; next }
    cols {
      valid=(length($0)>=start[cols]-1)
      for(i=2;i<=cols;i++) if(substr($0,start[i]-1,1)!=" ")valid=0
      if (!valid) { cols=0; print; next }
      record++
      if(wide) printf "%s╭─ Record %d%s\n",dim,record,off
      for(i=1;i<=cols;i++) {
        cell=(i<cols ? substr($0,start[i],start[i+1]-start[i]) : substr($0,start[i]))
        sub(/^[ ]+/,"",cell); sub(/[ ]+$/,"",cell)
        tone=(column[i]=="LAG" && cell~/^[0-9]+$/ ? (cell+0==0 ? green : yellow) : (i==1 ? green : ""))
        if(wide) printf "%s│%s %s%-17s%s %s%s%s\n",dim,off,cyan,column[i],off,tone,cell,off
        else printf "%s%s%s%s",tone,sprintf("%-" (i<cols ? start[i+1]-start[i] : length(column[i])) "s",cell),off,(i==cols ? "\n" : "")
      }
      if(wide) print dim "╰─" off
      next
    }
    /^diff --git / || /^--- / { diff_mode=1 }
    diff_mode && /^(diff --git |--- |\+\+\+ |@@)/ { print cyan $0 off; next }
    diff_mode && /^\+/ { print green $0 off; next }
    diff_mode && /^-/ { print red $0 off; next }
    /^Traceback \(most recent call last\):/ || /^[[:alnum:]_.]+(Error|Exception):/ { print red $0 off; next }
    /^  File ".*", line [0-9]+/ || /^[[:space:]]+at .*\(.*\.java:[0-9]+\)/ { print cyan $0 off; next }
    /^[[:digit:]][[:digit:]][[:digit:]][[:digit:]]-[[:digit:]][[:digit:]]-/ {
      tone=(tolower($0) ~ /error|fatal/ ? red : (tolower($0) ~ /warn/ ? yellow : cyan))
      print tone $0 off; next
    }
    # Some CLIs label each field in every row. Keep colons inside values intact.
    /\t/ {
      line=$0; sub(/^\t+/, "", line); count=split(line,fields,"\t"); labeled=(count>1)
      signature=""
      for(i=1;i<=count;i++) {
        if(!match(fields[i],/^[[:alnum:]_.-]+:[ ]*/)) { labeled=0; break }
        keys[i]=substr(fields[i],1,index(fields[i],":")-1)
        vals[i]=substr(fields[i],RLENGTH+1); signature=signature "|" keys[i]
      }
      if(labeled && /^\t/) {
        if(signature!=previous) {
          printf "\n"
          for(i=1;i<=count;i++) {
            widths[i]=length(keys[i]); if(length(vals[i])>widths[i]) widths[i]=length(vals[i])
            printf "%s%s%s%s",cyan,sprintf("%-" widths[i] "s",keys[i]),off,(i<count ? "  │  " : "\n")
          }
        }
        for(i=1;i<=count;i++) printf "%s%s%s%s",(i==1 ? green : ""),sprintf("%-" widths[i] "s",(vals[i]=="" ? "—" : vals[i])),off,(i<count ? "  │  " : "\n")
        previous=signature; next
      }
      if(labeled) {
        for(i=1;i<=count;i++) printf "%s%-20s%s %s\n",cyan,keys[i],off,vals[i]
        previous=""; next
      }
    }
    /^[[:alnum:]_.-]+:[[:space:]]/ {
      sep=index($0,":"); val=substr($0,sep+1); sub(/^[[:space:]]+/,"",val)
      printf "%s%-20s%s %s\n",cyan,substr($0,1,sep-1),off,val; next
    }
    /^[[:space:]]*-/ && /  +/ {
      if (match($0,/[^[:space:]].*  +/)) {
        head=substr($0,1,RLENGTH+RSTART-1); sub(/  +[^ ]+.*$/,"",head)
        print green head off substr($0,length(head)+1); next
      }
    }
    NR==1 && NF>1 && /  +|\t/ {
      print cyan $0 off; n=length($0); if(n>80)n=80
      rule=""; for(i=0;i<n;i++)rule=rule "─"; print dim rule off; next
    }
    /^(Usage:|usage:)/ || /:$/ { print cyan $0 off; next }
    tolower($0) ~ /(^|[^a-z])(error|failed|fatal)([^a-z]|$)/ { print red $0 off; next }
    tolower($0) ~ /(^|[^a-z])(warn|warning|pending)([^a-z]|$)/ { print yellow $0 off; next }
    { print }
  '
}
show() { [ "$#" -gt 0 ] && _remote_output_report "$@"; }
_remote_output_report() {
  local file rc
  if [ ! -t 1 ]; then command "$@"; return; fi
  file=$(command mktemp "${TMPDIR:-/tmp}/ghostty-report.XXXXXXXX") || { command "$@"; return; }
  command "$@" > "$file"; rc=$?
  pretty < "$file"
  command rm -f "$file"
  return "$rc"
}
codeview() {
  if command -v bat >/dev/null 2>&1; then bat "$@"
  elif command -v batcat >/dev/null 2>&1; then command batcat "$@"
  elif command -v pygmentize >/dev/null 2>&1 && [ -t 1 ] && [ "$#" = 1 ]; then
    command pygmentize -g -f terminal256 -O style=monokai -- "$1"
  elif command -v awk >/dev/null 2>&1 && [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    # Basic token colors for minimal images with only POSIX tools.
    command awk '
      BEGIN { esc=sprintf("%c",27); off=esc "[0m"; sq=sprintf("%c",39) }
      function paint(code,s) { printf "%s", (code ? esc "[" code "m" s off : s) }
      FNR==1 { quote="" }
      {
        printf "%s[90m%4d │%s ", esc,FNR,off
        s=$0
        while(length(s)) {
          c=substr(s,1,1)
          if(quote!="" || c=="\"" || c==sq) {
            i=1
            if(quote=="") {
              quote=(substr(s,1,3)==c c c ? c c c : c)
              i=length(quote)+1
            }
            while(i<=length(s)) {
              if(substr(s,i,1)=="\\") { i+=2; continue }
              if(substr(s,i,length(quote))==quote) { i+=length(quote); quote=""; break }
              i++
            }
            n=i-1; paint(93,substr(s,1,n))
          } else if(c=="#") { paint(90,s); break }
          else {
            match(s,/^(\$\{[[:alnum:]_]+\}|\$[[:alnum:]_@?#]+|[[:alpha:]_][[:alnum:]_]*|[0-9]+([.][0-9]+)?|[[:space:]]+|.)/)
            n=RLENGTH; word=substr(s,1,n); color=0
            if(word ~ /^(if|elif|else|then|fi|for|in|do|done|case|esac|while|until|function|def|class|return|import|from|as|try|except|finally|with|raise|yield|async|await|break|continue|export|local|and|or|not|pass)$/) color=95
            else if(word ~ /^\$/ || (word ~ /^[[:alpha:]_]/ && substr(s,n+1,1)=="=")) color=96
            else if(word ~ /^[0-9]/ || word ~ /^(True|False|None)$/) color=33
            else if(word ~ /^(echo|printf|read|cd|exec|set|test|exit|source)$/ || (word ~ /^[[:alpha:]_]/ && substr(s,n+1,1)=="(")) color=92
            paint(color,word)
          }
          s=substr(s,n+1)
        }
        print ""
      }' "$@"
  else command cat "$@"; fi
}
_remote_cat() {
  if [ -t 1 ] && [ "$#" = 1 ] && [ -f "$1" ]; then
    case "$1" in
      -*) ;;
      *) if command -v bat >/dev/null 2>&1; then bat --paging=never -- "$1"; return
         elif command -v batcat >/dev/null 2>&1; then command batcat --paging=never -- "$1"; return
         elif command grep -Iq . "$1" 2>/dev/null; then codeview "$1"; return
         fi ;;
    esac
  fi
  command cat "$@"
}
case "$(command -v cat)" in /*) alias cat='_remote_cat' ;; esac

# Format only finite reports. Capture the producer's exit status on POSIX sh too.
_remote_output() {
  local tool mode
  tool=$1; shift
  mode=native
  if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    case "$tool:$*" in
      *:--help|docker:-h|curl:-h|python3:-h|kubectl:-h) mode=report ;;
      docker:ps|docker:'ps -a'|docker:'container ls'|docker:'network ls'|docker:'volume ls'|pip:list|pip3:list) mode=report ;;
      df:*|ps:*|id:|uname:-a) mode=report ;;
    esac
    if [ "$tool" = kubectl ] && [ "$#" = 2 ] && [ "$1" = get ]; then mode=report; fi
  fi
  if [ "$mode" = native ]; then command "$tool" "$@"; return; fi
  _remote_output_report "$tool" "$@"
}
for _remote_tool in curl docker kubectl git pip pip3 python3 df ps id uname; do
  # Keep user-defined aliases/functions; these names are a fixed local allowlist.
  case "$(command -v "$_remote_tool" 2>/dev/null)" in
    /*) eval "$_remote_tool() { _remote_output $_remote_tool \"\$@\"; }" ;;
  esac
done
unset _remote_tool

# Interactive shells can dispatch a command typed as ./name as well as by name.
# Restrict this to Kafka describe reports. Pass every argument to the executable.
_remote_kafka() {
  local tool arg
  tool=$1; shift
  if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    if [ "${tool##*/}" = kafka-console-consumer.sh ] && command -v awk >/dev/null 2>&1 && command -v _option3_kafka_events >/dev/null 2>&1; then
      (set -o pipefail; command "$tool" "$@" | _option3_kafka_events)
      return $?
    fi
    for arg in "$@"; do
      case "$arg" in describe|--describe) _remote_output_report "$tool" "$@"; return ;; esac
    done
  fi
  command "$tool" "$@"
}
if [ -n "${BASH_VERSION:-}${ZSH_VERSION:-}" ]; then
  while IFS= read -r _kafka_name; do
    case "$_kafka_name" in ''|*[!a-zA-Z0-9._-]*) continue ;; esac
    for _kafka_path in "./$_kafka_name" "/opt/kafka/bin/$_kafka_name" "$_kafka_name"; do
      eval "function $_kafka_path { _remote_kafka $_kafka_path \"\$@\"; }"
    done
  done <<EOF
kafka-topics.sh
kafka-metadata-quorum.sh
kafka-consumer-groups.sh
kafka-console-consumer.sh
$(if [ -d /opt/kafka/bin ]; then command find /opt/kafka/bin -maxdepth 1 -name 'kafka-*.sh' -exec basename '{}' \; 2>/dev/null; fi)
EOF
  unset _kafka_name _kafka_path
fi

# Use the destination's Bash history. Selecting a match edits the current line.
if [ -n "${BASH_VERSION:-}" ] && [ -t 0 ] && [ -t 1 ] && command -v fzf >/dev/null 2>&1; then
  if _opt3_fzf_init=$(command fzf --bash 2>/dev/null); then
    export FZF_CTRL_R_OPTS="--height=65% --layout=reverse --border=rounded --border-label=' Shell history ' --prompt='History › ' --header='Enter: edit command   Esc: cancel' --color=bg:#000000,fg:#eeeeee,bg+:#102530,fg+:#ffffff,hl:#39ff88,hl+:#39ff88,border:#00e5ff,prompt:#ff55ff,pointer:#00e5ff,header:#66bbff --bind=shift-delete:ignore"
    FZF_CTRL_T_COMMAND='' FZF_ALT_C_COMMAND='' eval "$_opt3_fzf_init"
  fi
  unset _opt3_fzf_init
fi
