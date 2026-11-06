"""Render recognizable display output between a terminal and a macOS zsh PTY."""
import errno
import fcntl
import io
import os
import pty
import re
import secrets
import select
import signal
import subprocess
import sys
import termios
import time
import tty

try:
    from rich.console import Console
    from log_stream import classify, display
    from render import csv_rows, print_table, render_diagnostic, table_rows
except ImportError:
    if __name__ != "__main__":
        raise
    print("Richterm dependencies are unavailable; opening zsh. Rerun install.sh to repair.", file=sys.stderr)
    os.execl("/bin/zsh", "zsh", "-il")


def write(fd, data):
    while data:
        data = data[os.write(fd, data):]


def format_block(raw, width):
    """Return the original bytes unless the complete block has an identifiable shape."""
    try:
        text = raw.decode().replace("\r\n", "\n")
        lines = text.strip("\n").splitlines()
        looks_json = text.lstrip().startswith(("{", "["))
        if not lines or (not looks_json and len(lines) > 300):
            return raw
        buf = io.StringIO()
        console = Console(file=buf, width=max(1, width), color_system="truecolor",
                          force_terminal=True, no_color=False, highlight=False, markup=False)
        if looks_json:
            item = classify(raw) if len(lines) == 1 else None
            if isinstance(item, dict):
                event = display(item)
                if any(ord(ch) < 32 and ch not in "\n\t" for ch in event.plain):
                    return raw
                console.print(event)
            else:
                # jq consumes complete JSON documents or consecutive JSON values.
                # Keep the original numeric tokens out of Python's float conversion.
                parsed = subprocess.run(["jq", "-C", "--indent", "2", "."], input=raw,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2)
                return parsed.stdout.replace(b"\n", b"\r\n") if parsed.returncode == 0 else raw
        elif not render_diagnostic(console, text):
            pairs = [re.fullmatch(r"([\w][\w .()-]{0,40}):[ \t]+(.+)", line) for line in lines]
            if len(lines) >= 2 and all(pairs):
                rows = [["Field", "Value"], *(p.groups() for p in pairs)]
            else:
                rows = table_rows(lines) or (csv_rows(text, False) if "," in lines[0] else None)
            if not rows or len(rows[0]) > 24 or len(rows) * len(rows[0]) > 1500:
                return raw
            print_table(console, rows)
        return buf.getvalue().replace("\n", "\r\n").encode()
    except Exception:
        # Presentation failure must never eat command output.
        return raw


class Screen:
    def __init__(self, token):
        self.prefix = b"\x1b]777;" + token.encode() + b";"
        self.markers = re.compile(re.escape(self.prefix) + rb"([BRE])\x07")
        self.tail = b""
        self.tail_deadline = 0
        self.active = False
        self.pending = bytearray()
        self.json_document = False
        self.deadline = 0
        self.partial = False
        self.remote = False

    def flush(self):
        if self.pending:
            raw = bytes(self.pending)
            self.pending.clear()
            self.json_document = False
            write(1, format_block(raw, os.get_terminal_size(1).columns))

    def body(self, data):
        if not data:
            return
        if not self.active:
            write(1, data)
            return
        # An escape, standalone CR, or other cursor/control protocol switches
        # this command to transparent relay until the next shell command.
        candidate = self.json_document or (
            not self.pending and not self.partial and data.lstrip(b" \t").startswith((b"{", b"["))
        )
        # An ONLCR-generated CRLF can itself straddle two PTY reads.
        checked = data[:-1] if candidate and data.endswith(b"\r") else data
        control = re.search(rb"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]|\r(?!\n)", checked)
        if control:
            self.body(data[:control.start()])
            self.flush()
            self.active = False
            write(1, data[control.start():])
            return
        if candidate:
            # PTY reads are arbitrary byte chunks, not JSON or line boundaries.
            # Keep structured documents together, but release a complete log
            # event immediately so idle streams never wait for a second event.
            for part in data.splitlines(keepends=True):
                if not self.active:
                    write(1, part)
                    continue
                new_line = not self.pending
                self.pending.extend(part)
                self.json_document = True
                if len(self.pending) >= 1024 * 1024:
                    write(1, self.pending)
                    self.pending.clear()
                    self.json_document = False
                    self.active = False
                elif new_line and part.endswith(b"\n") and classify(part) is not None:
                    self.flush()
            self.deadline = time.monotonic() + 0.15
            return
        for line in data.splitlines(keepends=True):
            complete = line.endswith(b"\n")
            if not self.partial and not complete and line.rstrip().endswith((b"}", b"]")):
                candidate = bytes(self.pending) + line
                if candidate.lstrip().startswith((b"{", b"[")):
                    self.pending.extend(line)
                    self.flush()
                    continue
            if self.partial or not complete:
                # Prompts without a newline must be visible immediately.
                self.flush()
                write(1, line)
                self.partial = not complete
            elif classify(line) is not None:
                self.flush()
                write(1, format_block(line, os.get_terminal_size(1).columns))
            else:
                self.pending.extend(line)
                if len(self.pending) >= 32768:
                    self.flush()
                self.deadline = time.monotonic() + 0.045

    def feed(self, data):
        data = self.tail + data
        self.tail = b""
        pos = 0
        for match in self.markers.finditer(data):
            self.body(data[pos:match.start()])
            self.flush()
            self.active = match[1] in (b"B", b"R")
            self.remote = match[1] == b"R"
            self.partial = False
            pos = match.end()
        rest = data[pos:]
        # OSC markers can straddle two reads. Forward every unrelated escape.
        cut = rest.rfind(b"\x1b", max(0, len(rest) - len(self.prefix) - 1))
        if cut >= 0 and any(m.startswith(rest[cut:]) for m in
                            (self.prefix + char + b"\x07" for char in (b"B", b"R", b"E"))):
            self.tail = rest[cut:]
            self.tail_deadline = time.monotonic() + 0.045
            rest = rest[:cut]
        self.body(rest)


def main():
    if not all(os.isatty(fd) for fd in (0, 1)):
        sys.exit("Richterm needs an interactive terminal.")
    if os.environ.get("RICHTERM_ACTIVE"):
        sys.exit("Richterm is already active in this shell.")
    token = secrets.token_hex(12)
    saved = termios.tcgetattr(0)
    size = fcntl.ioctl(0, termios.TIOCGWINSZ, bytes(8))
    child, master = pty.fork()
    if child == 0:
        termios.tcsetattr(0, termios.TCSANOW, saved)
        fcntl.ioctl(0, termios.TIOCSWINSZ, size)
        os.environ["RICHTERM_TOKEN"] = token
        os.environ["RICHTERM_ACTIVE"] = "1"
        os.execl("/bin/zsh", "zsh", "-il")

    screen = Screen(token)
    def resize(*_):
        fcntl.ioctl(master, termios.TIOCSWINSZ,
                    fcntl.ioctl(0, termios.TIOCGWINSZ, bytes(8)))

    def stop(*_):
        raise SystemExit(1)

    try:
        signal.signal(signal.SIGWINCH, resize)
        for sig in (signal.SIGHUP, signal.SIGTERM):
            signal.signal(sig, stop)
        tty.setraw(0, termios.TCSANOW)
        os.set_blocking(master, False)
        pending_input = b""
        resize()
        while True:
            deadlines = []
            if screen.pending:
                deadlines.append(screen.deadline)
            if screen.tail:
                deadlines.append(screen.tail_deadline)
            timeout = max(0, min(deadlines) - time.monotonic()) if deadlines else None
            # Hold at most one paste chunk. When the child's input queue is
            # full, keep draining its output so it can finish writing and read.
            readers = [master] if pending_input else [master, 0]
            writers = [master] if pending_input else []
            ready, writable, _ = select.select(readers, writers, [], timeout)
            if master in ready:
                try:
                    chunk = os.read(master, 65536)
                except BlockingIOError:
                    chunk = None
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    break
                if chunk == b"":
                    break
                if chunk and not screen.remote and os.tcgetpgrp(master) not in (child, 0) and not (
                        termios.tcgetattr(master)[3] & termios.ICANON):
                    screen.flush()
                    screen.active = False
                if chunk:
                    screen.feed(chunk)
            if writable:
                try:
                    written = os.write(master, pending_input)
                except BlockingIOError:
                    pass  # Readiness can change before the write.
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    break
                else:
                    pending_input = pending_input[written:]
            if 0 in ready:
                keys = os.read(0, 4096)
                if not keys:
                    break
                screen.flush()
                if screen.active:
                    screen.active = False
                pending_input = keys
            if screen.pending and time.monotonic() >= screen.deadline:
                screen.flush()
            if screen.tail and time.monotonic() >= screen.tail_deadline:
                screen.body(screen.tail)
                screen.tail = b""
    finally:
        termios.tcsetattr(0, termios.TCSANOW, saved)
        os.close(master)
    screen.flush()
    write(1, screen.tail)
    status = os.waitstatus_to_exitcode(os.waitpid(child, 0)[1])
    return status if status >= 0 else 128-status


if __name__ == "__main__":
    sys.exit(main())
