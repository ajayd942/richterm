import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading
import unittest

from rich.console import Console

SOURCE = Path(__file__).resolve().parents[1] / "files/.config/terminal-option3"
sys.path.insert(0, str(SOURCE))
from failure_views import failures
from inspect_cli import change_table, snapshot


def cli(*args):
    return subprocess.run([sys.executable, str(SOURCE / "inspect_cli.py"), *args],
                          capture_output=True, text=True, timeout=10)


class Failures(unittest.TestCase):
    def test_junit_and_framework_filter(self):
        output = """MethodSource [className = 'BookingTest', methodName = 'counts', methodParameterTypes = '']
    => org.opentest4j.AssertionFailedError: seats ==> expected: <3> but was: <2>
       org.junit.jupiter.api.Assertions.assertEquals(Assertions.java:42)
       BookingTest.counts(BookingTest.java:7)
"""
        result, = failures(output)
        self.assertEqual((result.title, result.location, result.comparison),
                         ("BookingTest.counts", "BookingTest.java:7", ("3", "2")))

    def test_real_python_and_full_trace(self):
        result = cli("rtest", "--full", sys.executable, "-c", "def inner(): return {}['missing']\ninner()")
        self.assertEqual(result.returncode, 1)
        for term in ("Failure", "inner", "KeyError", "Traceback"):
            self.assertIn(term, result.stdout)

    def test_unrecognized_exit_and_output_preserved(self):
        result = cli("rtest", sys.executable, "-c", "print('custom failure'); raise SystemExit(7)")
        self.assertEqual((result.returncode, result.stdout), (7, "custom failure\n"))


class Reports(unittest.TestCase):
    def test_compares_values_by_key_and_handles_new_and_removed(self):
        header, old = snapshot("ID\tLAG\na\t48\nb\t1\nc\t0", ["ID"])
        _, new = snapshot("ID\tLAG\nc\t0\na\t0\nd\t1", ["ID"])
        buf = io.StringIO()
        Console(file=buf, width=90).print(change_table(header, new, old))
        for change in ("48 → 0", "+ d", "− b"):
            self.assertIn(change, buf.getvalue())
        self.assertNotIn("0 → 0", buf.getvalue())

    def test_duplicate_key_and_composite(self):
        data = "GROUP\tPARTITION\tLAG\na\t0\t20\na\t1\t10"
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            snapshot(data, ["GROUP"])
        self.assertEqual(len(snapshot(data, ["GROUP", "PARTITION"])[1]), 2)


class Http(unittest.TestCase):
    def test_real_http_responses(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                code = int(self.path[1:])
                self.send_response(code)
                self.send_header("X-Request-ID", "demo-17")
                if code == 429:
                    self.send_header("Retry-After", "30")
                self.end_headers()
                self.wfile.write(b'{"message":"response detail"}')

            def log_message(self, *args):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for code in (200, 429, 500):
                    result = cli("rhttp", f"http://127.0.0.1:{server.server_port}/{code}")
                    self.assertEqual(result.returncode, 0 if code == 200 else 22)
                    self.assertIn("demo-17", result.stdout)
                    self.assertIn("response detail", result.stdout)
                    self.assertEqual("30 seconds" in result.stdout, code == 429)
            finally:
                server.shutdown()
                thread.join()
