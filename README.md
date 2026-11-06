# Richterm

A macOS terminal for people who spend their day reading code, logs, and command output. Keep typing your usual commands. Richterm turns recognizable reports into tables and makes warnings stand out as logs arrive.

![A Ghostty session showing four services in a bordered table, followed by live deployment events with a highlighted worker warning.](docs/screenshots/service-overview.png)

The two demo scripts above print ordinary CSV and JSON logs. Richterm does the styling.

## Get started

You'll need macOS, [Homebrew](https://brew.sh/), and Git. The installer sets up Ghostty, the font, and the developer tools. **It backs up and replaces matching settings, including `~/.zshrc` and `~/.vimrc`.** See the [setup and recovery guide](docs/guide.md) if you already have a customized shell.

```sh
git clone https://github.com/ajayd942/richterm.git
cd richterm
./install.sh
open -a Ghostty
```

Open a new tab and type **`desk`** to explore. For a quick first look, paste this into the prompt:

```sh
printf 'SERVICE\tSTATE\napi\tready\nworker\tpending\n'
```

## Find the line you need

Run `csearch` and type a fragment you remember. Move through the matches to see each line in context. Press **Enter** to open the selected line in your editor.

![Searching for latency_ms shows two matches in health.py, with the selected Python line highlighted in the preview.](docs/screenshots/code-search.png)

## Review a change

Inside a Git repository, `gd` shows your unstaged changes. Here a two-line change adds a health check and raises a latency threshold. For a larger review, `lg` opens the interactive Git browser.

![A Python diff showing a new replica check in green and the old latency threshold in red.](docs/screenshots/git-diff.png)

**A few everyday shortcuts:** **Ctrl-R** searches command history, `y` browses files with previews, and `md README.md` opens a formatted Markdown reader. For Docker, SSH, keyboard shortcuts, or switching back to a plain shell, see the [full guide](docs/guide.md).
