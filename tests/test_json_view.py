import json
import subprocess
import sys
import threading
import unittest
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

SOURCE = Path(__file__).resolve().parents[1] / "files/.config/terminal-option3"
sys.path.insert(0, str(SOURCE))
from inspect_cli import http_view
from json_view import Document, LIMIT, MISSING, Viewer, jq_path, summary


class Model(unittest.TestCase):
    def test_records_missing_and_numeric_precision(self):
        raw = b'[{"id":900719925474099327,"price":149.00,"note":null},{"id":2}]'
        doc = Document(raw)
        view = Viewer(doc)
        self.assertEqual(view.mode, "table")
        rows, keys = view.table()
        self.assertEqual(keys, ["id", "price", "note"])
        self.assertNotEqual(
            summary(rows[0]["note"]), summary(rows[1].get("note", MISSING))
        )
        self.assertEqual(doc.clipboard_text((0, "price")), "149.00")
        self.assertIn("900719925474099327", doc.clipboard_text((0,)))
        self.assertEqual(doc.clipboard_text((), raw=True), raw.decode())

    def test_search_and_navigation(self):
        doc = Document(b'{"items":[{"bookingId":"B-42"},{"bookingId":"B-43"}]}')
        self.assertEqual(
            doc.find("bookingid"),
            [("items", 0, "bookingId"), ("items", 1, "bookingId")],
        )
        (found,) = doc.find("b-43")
        view = Viewer(doc)
        view.focus(found)
        self.assertEqual(view.tree()[view.pos], found)
        view.path = found
        view.switch("table")
        self.assertEqual((view.dataset, view.pos), (("items",), 1))

    def test_jq_path_round_trip(self):
        raw = b'{"a.b":[{"a\\"b": {"":"hello"}}]}'
        path = ("a.b", 0, 'a"b', "")
        expr = jq_path(path)
        result = subprocess.check_output(["jq", "-r", expr], input=raw)
        self.assertEqual(result.decode().strip(), Document(raw).clipboard_text(path))

    def test_invalid_input(self):
        for raw in (b"not json", b'{"x":1,"x":2}', b'{"x":NaN}', b" " * (LIMIT + 1)):
            with self.assertRaises(ValueError):
                Document(raw)

    def test_validation_fields(self):
        doc = Document(
            b'{"detail":[{"loc":["items",2,"quantity"],"msg":"Must be positive"}]}'
        )
        self.assertEqual(
            doc.errors, [("items[2].quantity", "Must be positive", ("detail", 0))]
        )
        self.assertEqual(Viewer(doc, failed=True).mode, "errors")

    def test_one_request_including_http_error(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.path)
                self.send_response(422)
                self.send_header("X-Request-ID", "demo-1")
                self.end_headers()
                self.wfile.write(b'{"errors":{"quantity":["Must be positive"]}}')

            def log_message(self, *args):
                pass

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            th = threading.Thread(target=server.serve_forever, daemon=True)
            th.start()
            try:

                def inspect(raw, metadata, failed):
                    doc = Document(raw)
                    view = Viewer(doc, metadata, failed)
                    self.assertIn("demo-1", metadata)
                    self.assertEqual(view.mode, "errors")
                    self.assertEqual(doc.nodes[doc.errors[0][2]], "Must be positive")
                    self.assertEqual(
                        json.loads(doc.raw)["errors"]["quantity"][0], "Must be positive"
                    )

                with patch("inspect_cli.explore", side_effect=inspect):
                    code = http_view(
                        Namespace(
                            url=f"http://127.0.0.1:{server.server_port}/orders",
                            explore=True,
                        ),
                        Console(),
                    )
                self.assertEqual(code, 22)
                self.assertEqual(seen, ["/orders"])
            finally:
                server.shutdown()
                th.join()
