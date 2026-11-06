# Fast, readable interactive zsh configuration.
if [[ -z ${HOMEBREW_PREFIX:-} ]]; then
  for _brew in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [[ -x $_brew ]]; then eval "$("$_brew" shellenv zsh)"; break; fi
  done
  unset _brew
fi
typeset -U path fpath
path=("$HOME/.local/bin" "$HOMEBREW_PREFIX/bin" $path)

# History ---------------------------------------------------------------------
HISTFILE="$HOME/.zsh_history"
HISTSIZE=1000000
SAVEHIST=1000000000
setopt APPEND_HISTORY INC_APPEND_HISTORY SHARE_HISTORY
setopt HIST_IGNORE_ALL_DUPS HIST_FIND_NO_DUPS HIST_REDUCE_BLANKS
setopt HIST_IGNORE_SPACE EXTENDED_HISTORY

# Sensible shell behavior ------------------------------------------------------
setopt AUTO_CD AUTO_PUSHD PUSHD_IGNORE_DUPS INTERACTIVE_COMMENTS
setopt NO_BEEP
bindkey -e
autoload -Uz up-line-or-beginning-search down-line-or-beginning-search
zle -N up-line-or-beginning-search
zle -N down-line-or-beginning-search
bindkey '^[[A' up-line-or-beginning-search
bindkey '^[[B' down-line-or-beginning-search

# Completion ------------------------------------------------------------------
fpath=("$HOMEBREW_PREFIX/share/zsh-completions" "$HOMEBREW_PREFIX/share/zsh/site-functions" $fpath)
[[ -d "$HOME/.docker/completions" ]] && fpath=("$HOME/.docker/completions" $fpath)
autoload -Uz compinit
zmodload zsh/complist
compinit -d "$HOME/.zcompdump"
zstyle ':completion:*' menu select
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}' 'r:|=*' 'l:|=* r:|=*'
zstyle ':completion:*' use-cache on
zstyle ':completion:*' cache-path "$HOME/.cache/zsh"
zstyle ':completion:*:descriptions' format '%F{yellow}-- %d --%f'
zstyle ':completion:*' group-name ''
zstyle ':completion:*' verbose yes

# Better defaults for developer tools -----------------------------------------
unset NO_COLOR
export CLICOLOR=1
export COLORTERM=truecolor
export BAT_THEME="Neon Black"
export LS_COLORS='di=1;36:ln=1;35:ex=1;32:*.java=1;33:*.js=1;33:*.ts=1;34:*.py=1;32:*.json=36:*.md=35:*.zip=1;31'
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"
export EZA_COLORS='di=1;36:ex=1;32:ln=1;35:da=37:sn=1;33:sb=33:ur=32:uw=33:ux=31:gr=32:gw=33:gx=31:tr=90'
export FZF_DEFAULT_COMMAND="fd --type f --hidden --follow --exclude .git"
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
export FZF_ALT_C_COMMAND="fd --type d --hidden --follow --exclude .git"
export FZF_DEFAULT_OPTS="--height=65% --layout=reverse --border=rounded --info=inline --cycle --prompt='❯ ' --pointer='▶' --marker='✓' --color=bg:#000000,fg:#eeeeee,bg+:#102530,fg+:#ffffff,hl:#39ff88,hl+:#39ff88,border:#00e5ff,prompt:#ff55ff,pointer:#00e5ff,marker:#39ff88,spinner:#ff55ff,header:#ffe600 --preview-window=right,60%,border-left --bind=ctrl-/:toggle-preview"
export FZF_CTRL_T_OPTS="--border-label=' Files ' --preview-window='right,55%,<100(down,50%)' --preview 'bat --paging=never --color=always --style=numbers,changes --line-range=:300 -- {}'"
export FZF_ALT_C_OPTS="--border-label=' Directories ' --preview-window='right,55%,<100(down,50%)' --preview 'eza --tree --level=2 --icons --color=always -- {} 2>/dev/null'"

# Integrations ----------------------------------------------------------------
source <(fzf --zsh)
eval "$(zoxide init zsh)"
eval "$(direnv hook zsh)"
eval "$(mise activate zsh)"

# Atuin replaces Ctrl-R with contextual fuzzy history search. Sync stays off.
eval "$(atuin init zsh --disable-up-arrow)"

# Prompt.
eval "$(starship init zsh)"

# Autosuggestions must load before syntax highlighting; highlighting stays last.
ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=#8b949e'
ZSH_AUTOSUGGEST_STRATEGY=(history completion)
source "$HOMEBREW_PREFIX/share/zsh-autosuggestions/zsh-autosuggestions.zsh"
source "$HOMEBREW_PREFIX/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
# Use Ghostty's white foreground for typed commands. Suggestions have their own style.
ZSH_HIGHLIGHT_HIGHLIGHTERS=()

# Explicit shortcuts; standard commands remain unchanged.
alias ll='eza --long --header --icons --git'
alias la='eza --long --all --header --icons --git'
alias lt='eza --tree --level=2 --icons --git-ignore'
alias bcat='bat --paging=never'
alias lg='lazygit'
alias files='eza --long --all --header --icons --git --group-directories-first'
alias g='git'
alias gs='git status --short --branch'
alias gl='git log --oneline --decorate --graph --all -20'
source "$HOME/.config/terminal-option3/tools.zsh"
alias ..='cd ..'
alias ...='cd ../..'

mkcd() {
  mkdir -p -- "$1" && cd -- "$1"
}
