"""Install the curated files, backing up every existing configuration we change."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
home = Path.home()
files = root / "files"
backup_root = home / ".local/state/richterm"
backup_root.mkdir(parents=True, exist_ok=True)
backup = Path(tempfile.mkdtemp(prefix="before-", dir=backup_root))
print(f"Backup of replaced files: {backup}", flush=True)


def preserve(dest):
    if dest.is_symlink() or dest.exists():
        if dest.is_dir():
            raise SystemExit(f"Expected a file at {dest}; stopping.")
        saved = backup / dest.relative_to(home)
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, saved, follow_symlinks=False)


def run(*cmd):
    subprocess.run(cmd, check=True)


venv = home / ".config/terminal-option3/render-env"
run(sys.executable, "-m", "venv", str(venv))
run(str(venv / "bin/python"), "-m", "pip", "install", "-q", "-r", str(root / "requirements.txt"))

def install_file(src):
    dest = home / src.relative_to(files)
    content = src.read_bytes()
    if dest == home / ".config/yazi/theme.toml":
        theme = str(home / ".config/bat/themes/Neon Black.tmTheme")
        content = content.replace(b'"__BAT_THEME_PATH__"', json.dumps(theme, ensure_ascii=False).encode())
    if dest.is_file() and dest.read_bytes() == content and (dest.stat().st_mode & 0o777) == (src.stat().st_mode & 0o777):
        return
    preserve(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
        tmp.write(content)
    os.chmod(tmp.name, src.stat().st_mode & 0o777)
    os.replace(tmp.name, dest)


# Activate the new terminal command only after installing its runtime and hooks.
ghostty = files / ".config/ghostty/config"
for src in sorted(files.rglob("*")):
    if src.is_file() and src != ghostty and "__pycache__" not in src.parts:
        install_file(src)

git_include = "~/.config/terminal-option3/gitconfig"
includes = subprocess.run(["git", "config", "--global", "--get-all", "include.path"],
                          capture_output=True, text=True)
if includes.returncode not in (0, 1):
    raise SystemExit(includes.stderr)
if git_include not in includes.stdout.splitlines():
    # Use an explicit file to avoid modifying an inherited global config path.
    gitcfg = home / ".gitconfig"
    preserve(gitcfg)
    run("git", "config", "--file", str(gitcfg), "--add", "include.path", git_include)
run("bat", "cache", "--build")
install_file(ghostty)
print("Open Ghostty, reload with Cmd-Shift-comma, open a new tab and type desk.")
