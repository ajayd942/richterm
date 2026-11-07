"""Behavior checks for the display boundary, including a real nested zsh PTY."""
import fcntl
import os
from pathlib import Path
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "files/.config/terminal-option3"
sys.path.insert(0, str(SOURCE))
from pty_proxy import Screen, format_block


class Rendering(unittest.TestCase):
    def test_postgres_table_with_messages_and_pipe_in_value(self):
        raw = (b"CREATE TABLE\r\nINSERT 0 1\r\n"
               b" id | name  \r\n----+-------\r\n  1 | a | b \r\n(1 row)\r\n\r\n")
        output = format_block(raw, 80).decode()
        for part in ("CREATE TABLE", "INSERT 0 1", "╭", "a | b", "(1 row)"):
            self.assertIn(part, output)
        incomplete = raw.replace(b"(1 row)", b"(2 rows)")
        self.assertEqual(format_block(incomplete,80), incomplete)

    def test_multiline_json_split_inside_key_crlf_and_utf8(self):
        raw = '{\r\n  "café": [1, 2],\r\n  "ok": true\r\n}\r\n'.encode()
        output = bytearray()
        screen = Screen("test")
        with patch("pty_proxy.write", side_effect=lambda fd, data: output.extend(data)), \
             patch("pty_proxy.os.get_terminal_size", return_value=os.terminal_size((90, 30))):
            screen.feed(b"\x1b]777;test;B\x07")
            for byte in raw:
                screen.feed(bytes([byte]))
            screen.feed(b"\x1b]777;test;E\x07")
        self.assertIn(b"\x1b[", output)
        import json
        self.assertEqual(json.loads(re.sub(rb"\x1b\[[0-9;]*m", b"", output)), json.loads(raw))

    def test_mixed_alignment_and_json(self):
        data = b"health status docs.count store.size\r\ngreen  open            0       498b\r\n"
        result = format_block(data, 80).decode()
        for part in ("╭", "docs.count", "498b"):
            self.assertIn(part, result)
        result = format_block(b'{"items":[1,2]}', 80)
        self.assertIn(b"\x1b[", result)
        self.assertGreater(result.count(b"\r\n"), 2)

    def test_unrecognized_or_invalid_input(self):
        for raw in (b"ordinary text\r\n", b"{unfinished", b"\xff\x00\xfe"):
            self.assertEqual(format_block(raw, 80), raw)

    def test_json_escaped_terminal_controls_stay_data(self):
        raw = br'{"level":"INFO","message":"test\u001b]52;c;AAAA\u0007"}'
        self.assertNotIn(b"\x1b]52;", format_block(raw, 80))

    def test_fragmented_boundaries_and_control_passthrough(self):
        screen = Screen("test")
        output = bytearray()
        with patch("pty_proxy.write", side_effect=lambda fd, data: output.extend(data)):
            screen.feed(b"\x1b]777;te")
            screen.feed(b"st;B\x07Password: ")
            self.assertEqual(output, b"Password: ")
            tui = b"\x1b[?1049hNAME\tSTATE\r\napp\tready\r\n\x1b[?1049l"
            screen.feed(tui + b"\x1b]777;test;E\x07")
            self.assertEqual(output, b"Password: " + tui)


@unittest.skipUnless(sys.platform == "darwin", "the workstation target is macOS")
class TerminalSession(unittest.TestCase):
    def test_paste_while_child_fills_output_queue(self):
        import hashlib
        import shlex

        paste = bytes(range(32, 128)) * 2048
        burst = b"output-0123456789" * 16384
        expected = b"DIGEST:" + hashlib.sha256(paste).hexdigest().encode()
        with tempfile.TemporaryDirectory() as tmp:
            helper = Path(tmp) / "producer.py"
            helper.write_text(
                "import hashlib, os, sys, time, tty\n"
                "tty.setraw(0)\n"
                "os.write(1, b'READY!')\n"
                "time.sleep(0.3)\n"  # Let the paste fill the child's unread input queue.
                "sys.stdout.buffer.write(b'output-0123456789' * 16384)\n"
                "sys.stdout.buffer.flush()\n"
                f"remaining = {len(paste)}\n"
                "digest = hashlib.sha256()\n"
                "while remaining:\n"
                "    chunk = os.read(0, min(remaining, 4096))\n"
                "    digest.update(chunk)\n"
                "    remaining -= len(chunk)\n"
                "os.write(1, b'DIGEST:' + digest.hexdigest().encode())\n"
            )
            (Path(tmp) / ".zshrc").write_text("exec " + shlex.join([sys.executable, str(helper)]) + "\n")
            env = dict(os.environ, HOME=tmp, ZDOTDIR=tmp, TERM="xterm-256color")
            env.pop("RICHTERM_ACTIVE", None)
            master, slave = pty.openpty()
            self.addCleanup(os.close, master)
            self.addCleanup(os.close, slave)
            os.set_blocking(master, False)
            proc = subprocess.Popen([sys.executable, str(SOURCE / "pty_proxy.py")],
                                    stdin=slave, stdout=slave, stderr=slave, env=env)
            capture = bytearray()
            sent = 0
            ready = False
            try:
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and not capture.endswith(expected):
                    writers = [master] if ready and sent < len(paste) else []
                    rd, wr, _ = select.select([master], writers, [], 0.05)
                    if rd:
                        capture.extend(os.read(master, 65536))
                        ready = ready or b"READY!" in capture
                    if wr:
                        try:
                            sent += os.write(master, paste[sent:sent+4096])
                        except BlockingIOError:
                            pass
                self.assertEqual(sent, len(paste), "paste stalled while child was writing")
                self.assertTrue(capture.endswith(b"READY!" + burst + expected),
                                "output was lost, or pasted bytes changed")
                self.assertEqual(proc.wait(timeout=5), 0)
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=5)

    def test_resize_table_pipeline_and_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".config").mkdir()
            (home / ".config/terminal-option3").symlink_to(SOURCE)
            (home / ".zshrc").write_text(
                'source "$HOME/.config/terminal-option3/tools.zsh"\nPROMPT="rich-test> "\n'
            )
            master, slave = pty.openpty()
            self.addCleanup(os.close, master)
            self.addCleanup(os.close, slave)
            before = termios.tcgetattr(slave)
            env = dict(os.environ, HOME=tmp, ZDOTDIR=tmp, TERM="xterm-256color")
            for key in ("RICHTERM_ACTIVE", "RICHTERM_TOKEN", "NO_COLOR"):
                env.pop(key, None)
            proc = subprocess.Popen([sys.executable, str(SOURCE / "pty_proxy.py")],
                                    stdin=slave, stdout=slave, stderr=slave, env=env)

            def expect(pattern):
                data = bytearray()
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    if select.select([master], [], [], 0.1)[0]:
                        data.extend(os.read(master, 65536))
                        if re.search(pattern, data):
                            return
                self.fail(f"timed out waiting for {pattern!r}; tail={data[-400:]!r}")

            try:
                expect(b"rich-test>")
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 96, 0, 0))
                proc.send_signal(signal.SIGWINCH)
                os.write(master, b"stty size\n")
                expect(rb"32 96\r")
                os.write(master, b"printf 'NAME\\tSTATE\\napi\\tready\\n'\n")
                expect("╭".encode())
                os.write(master, b"printf 'A\\tB\\n' | od -An -tx1\n")
                expect(rb"41\s+09\s+42\s+0a")
                os.write(master, b"exit 7\n")
                self.assertEqual(proc.wait(timeout=5), 7)
                after = termios.tcgetattr(slave)
                # Darwin may set PENDIN while restoring cooked mode.
                for attrs in (before, after):
                    attrs[3] &= ~termios.PENDIN
                self.assertEqual(after, before)
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=5)
