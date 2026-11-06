#!/bin/bash
# Optional: install the rich viewer and editor in a running Alpine container.
set -euo pipefail
[[ $# == 1 && $1 =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || { echo 'Usage: scripts/alpine-extras.sh CONTAINER' >&2; exit 2; }
target=$1
cd "$(dirname "$0")/../files"
docker exec "$target" sh -c 'test -r /etc/alpine-release && test -w "$HOME"'
docker exec -u 0 "$target" apk add --no-cache bat vim less fzf
backup=$(docker exec "$target" sh -c 'mktemp -d "$HOME/.terminal-extras-before.XXXXXXXX"')
echo "Container config backup: $backup"
for file in .vimrc .config/bat/config .config/bat/themes/* .config/bat/syntaxes/*; do
  docker exec -i "$target" sh -ec '
    cd "$HOME"
    file=$1
    if test -e "$file" || test -L "$file"; then
      mkdir -p "$2/$(dirname "$file")"
      cp -Pp "$file" "$2/$file"
    fi
    mkdir -p "$(dirname "$file")"
    tmp=$(mktemp "$(dirname "$file")/.terminal-config.XXXXXXXX")
    cat > "$tmp"
    mv "$tmp" "$file"
  ' sh "$file" "$backup" < "$file"
done
docker exec "$target" bat cache --build
