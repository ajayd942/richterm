#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
[[ $(uname -s) == Darwin ]] || { echo 'This workstation setup requires macOS.' >&2; exit 1; }
case "${1:-}" in
  ""|--skip-brew) ;;
  *) echo 'Usage: ./install.sh [--skip-brew]' >&2; exit 2 ;;
esac
brew_bin=$(command -v brew || true)
for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
  [[ -n $brew_bin || ! -x $candidate ]] || brew_bin=$candidate
done
[[ -n $brew_bin ]] || { echo 'Install Homebrew (https://brew.sh), then rerun this installer.' >&2; exit 1; }
eval "$("$brew_bin" shellenv bash)"
if [[ ${1:-} != --skip-brew ]]; then
  "$brew_bin" bundle install --file=Brewfile --no-upgrade
fi
python="$("$brew_bin" --prefix python@3.13)/bin/python3.13"
"$python" scripts/install.py
