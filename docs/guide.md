# Richterm setup and reference

[Back to the Richterm overview](../README.md)

Richterm automatically formats recognizable command output inside Ghostty on macOS. An unfamiliar script can print a table or JSON and get a readable display without an alias or a pipeline. Ghostty handles fonts, windows and splits. A local PTY proxy runs zsh and formats eligible output on its way to the screen.

This repository installs the complete workstation profile: black background, white input, JetBrains Mono Nerd Font at 20 pt, local history search, a themed Vim, file previews, Git tools, and Docker/SSH shell integration.

## Install on macOS

Install [Homebrew](https://brew.sh/) and Git first. Use the default macOS zsh and standard home-directory config locations. The installer **replaces the matching dotfiles**, including `~/.zshrc` and `~/.vimrc`. It saves prior copies in a private directory under `~/.local/state/richterm/before-*` and prints the exact path. Review or merge any personal startup lines afterward. Your login profile (`~/.zprofile`) stays yours.

```sh
git clone https://github.com/ajayd942/richterm.git
cd richterm
./install.sh
open -a Ghostty
```

If Ghostty is already running, press **⌘⇧,** to reload and **⌘T** to open a fresh tab. Type `desk`. To update, pull and rerun the installer. Use `./install.sh --skip-brew` when all Brewfile dependencies are already installed. The installer copies configs, so the clone can live anywhere.

The Brewfile installs released Homebrew packages and skips upgrading already-installed dependencies where supported. Use **Ghostty 1.4 or later** for unlimited scrollback. Python renderer dependencies are pinned in `requirements.txt`. The appearance and settings are reproducible; Homebrew versions can vary with time and macOS support.

## Try it

| In Ghostty | Action |
|---|---|
| `desk` | Choose the file browser, code viewer, project search, Markdown reader, or Git UI. |
| **Ctrl-R** | Search local Atuin command history. Sync is off. Enter returns the selected command for editing. |
| **Tab**, **→** | Browse completions or accept a gray autosuggestion at the end of the line. |
| **Ctrl-T**, **Option-C**, `z NAME` | Find a file, pick a directory, or jump to a frequent directory. |
| `y`, `files`, `lt` | Browse files with previews, list with Git status, or show a directory tree. |
| `cat FILE`, `codeview`, `vim FILE` | Read highlighted source, pick a file, or edit in themed Vim. Bat includes a syntax for LICENSE and NOTICE files. |
| `csearch TEXT` | Search the current tree, preview the exact line, and open in VS Code if its CLI is available, otherwise Neovim or Vim. |
| `md README.md` | Read rendered Markdown in a pager. |
| `lg`, `gd`, `gds` | Open LazyGit or review unstaged/staged diffs with Delta. |
| `show COMMAND …`, `COMMAND \| pretty` | Render a finite report. Recognizes structured tables, JSON, JSON Lines, CSV, diffs and diagnostics. Explicit modes include `pretty help`, `csv`, `json`, `table`, `log`, `yaml`, and `xml`. |
| **⌘D**, **⌘⇧D**, **⌘⇧Enter**, **⌘W** | Split right, split down, zoom a split, or close the focused split. |

Both scrollback caps are unlimited per open pane. Atuin stores command history across sessions. To import a machine's existing shell history deliberately, run `atuin import auto`. The global quick-terminal shortcut (⌘ + grave accent) may require macOS Accessibility access.

## Automatic formatting

New Ghostty tabs and splits start Richterm automatically. To check, run
`echo "$RICHTERM_ACTIVE"` (expected: `1`). Try this command:

```sh
/usr/bin/printf 'SERVICE\tSTATE\napi\tready\nworker\tpending\n'
```

Recognized complete rows, key/value reports, CSV, and single-line JSON/log events
can be styled automatically. Finite report rows are grouped in short, bounded
bursts; slow or fragmented output may stay plain. A prompt without a newline is
forwarded immediately. Existing terminal controls or user input switch the
current command to transparent relay. Vim and other terminal interfaces keep
their own display. Hooks also accompany the bundled Docker/SSH shell profiles
for zsh and Bash with PS0 support. Direct/uninstrumented remote sessions may
stay plain. Input and output have no transcript file in the proxy; the configured
shell and Atuin still maintain their own command history. Pipelines and files
receive the bytes written by the original programs.

**Plain shell / recovery.** For a separate window outside the proxy, run
`open -na Ghostty --args -e /bin/zsh -il` from macOS Terminal. To turn off the
proxy permanently, remove the `command = shell:...` line from
`~/.config/ghostty/config`, reload Ghostty, and open a tab. To bypass shell
customization as well, use `open -na Ghostty --args -e /bin/zsh -f`.

## Development

### Inspect commands

- `rtest [--full] COMMAND [ARGS...]` waits for a finite test run to finish, then summarizes recognized JUnit assertion failures and Python tracebacks. Successful or unrecognized results are printed in full. It also prints the original output if it exceeds the 1 MiB diagnostic scan window. Re-run with `--full` to see both views; Richterm doesn't keep a test transcript after the process exits. The PTY can also summarize a complete recognizable traceback during normal execution, subject to its grouping window.
- `rwatch [--interval SECONDS] [--count N] [--key COLUMN ...] COMMAND [ARGS...]` runs a command repeatedly; **use a read-only report**. The default interval is two seconds after each completed sample. Use headed CSV, TSV, aligned tables or JSON arrays of objects. The first column identifies rows by default. Repeat `--key` when multiple columns identify a row. Changed cells show old → new; added and removed rows have + and − markers. A changed schema starts a new baseline. Each sample has a 30-second timeout and a 1 MiB display limit.
- `rhttp URL` runs one HTTP(S) GET with curl, with a 30-second timeout, no retries and no redirect following. It displays status, duration, selected diagnostic headers and a body excerpt. HTTP 4xx/5xx returns status 22; transport errors retain curl's exit code. Use your regular curl command for authenticated requests or other methods.

### Run the test suite

The PTY relay, display detectors and shell integration live under
`files/.config/terminal-option3/` (the existing config directory is retained
for compatibility). The proxy preserves terminal controls and falls back to
the original bytes on rendering errors. Its 45 ms grouping window is a latency
tradeoff, not a guarantee that every document will be recognized. It is a
presentation tool, not a sanitizer for untrusted terminal escape sequences.

From the repository root, use Python 3.13 with the packages in
`requirements.txt` and `jq` on PATH. Run `python -m unittest discover -s tests -v`.

## Docker and SSH

With Docker or OpenSSH already installed, use the usual commands:

```sh
docker exec -it -w /your/workdir CONTAINER bash
ssh user@host
```

The zsh integration sends the bundled portable profile for supported interactive shell invocations. It uses temporary startup files on the destination and tools available there. `show`, `pretty`, `ll`, and `codeview` are available in supported sessions. Includes Kafka describe reports, streamed JSON consumer records, and a live `docker stats` view. Plain `command ssh …` and `command docker …` bypass the wrappers. Non-interactive transfers and command execution generally use the native clients.

For full bat and Vim in an **Alpine** container, optionally run `./scripts/alpine-extras.sh CONTAINER` from the clone on the Mac. This explicitly installs Alpine packages as root **inside that container** and copies the bat/Vim settings to the container user's home. It needs writable storage, package repositories, and administrator access within the container. Recreating a container discards those additions unless you incorporate them into your image. The workstation installer does not contact your Docker or SSH destinations.

## What is installed

- `Brewfile` lists the apps, font and tools. The installer uses Homebrew on either architecture and creates a private Python environment for Rich.
- `files/` contains only the settings and helper programs. Git styling is loaded through a small include. Each user supplies their own Git identity, credentials, optional editor integrations, language runtimes, and history.
- `files/.config/terminal-option3/` contains the shell functions, local report renderer and portable shell profile. `files/.local/bin/term-code-search` implements project search.
- To restore an overwritten setting, copy its corresponding file from the installer backup in your home directory. To disable the added Git include, run `git config --global --fixed-value --unset-all include.path '~/.config/terminal-option3/gitconfig'`. Homebrew packages can be managed independently.
