"""Explicit views for failed test commands, HTTP GETs, and repeated reports."""
import argparse
import csv
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from failure_views import draw_failure, failures
from render import table_rows
from json_view import LIMIT as JSON_LIMIT, explore

LIMIT = 1024 * 1024


def command_args(args):
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise ValueError("Provide a command to run.")
    return command


def text_value(value):
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return "".join(c if c.isprintable() or c in "\n\t" else ascii(c)[1:-1] for c in s)


def test_view(args, console):
    with tempfile.TemporaryFile() as log:
        proc = subprocess.run(command_args(args), stdout=log, stderr=subprocess.STDOUT)
        length = log.tell()
        log.seek(max(0, length - LIMIT))
        result = failures(log.read().decode(errors="replace")) if proc.returncode else []
        for failure in result:
            draw_failure(console, failure)
        if args.full or not result or length > LIMIT:
            log.seek(0)
            while chunk := log.read(65536):
                sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
        else:
            console.print("Use rtest --full for the complete output.", style="#99aabb")
        return proc.returncode if proc.returncode >= 0 else 128 - proc.returncode


def http_view(args, console):
    if urlsplit(args.url).scheme not in ("http", "https"):
        raise ValueError("Provide an http:// or https:// URL.")
    with tempfile.TemporaryDirectory() as tmp:
        headers, body = Path(tmp)/"headers", Path(tmp)/"body"
        cap = ["--max-filesize", str(JSON_LIMIT)] if args.explore else []
        result = subprocess.run(["curl", "--disable", "--silent", "--show-error", "--globoff", *cap,
                                 "--max-time", "30", "--proto", "=http,https", "--dump-header", str(headers),
                                 "--output", str(body), "--write-out", "%{response_code} %{time_total}",
                                 "--", args.url], stdout=subprocess.PIPE, text=True)
        if result.returncode:
            return result.returncode
        code, seconds = result.stdout.split()
        blocks = headers.read_bytes().decode("latin-1").replace("\r\n", "\n").strip().split("\n\n")
        response = next(block for block in reversed(blocks) if block.startswith("HTTP/"))
        status, *fields = response.splitlines()
        metadata = {k.lower():v.strip() for field in fields for k, _, v in [field.partition(":")]}
        color = "#ffe600" if code == "429" else "#ff5577" if int(code) >= 400 else "#39ff88"
        if args.explore:
            info = [status, f"{float(seconds)*1000:.1f} ms"]
            if "x-request-id" in metadata:
                info.append("request " + metadata["x-request-id"])
            if "retry-after" in metadata:
                info.append("retry-after " + metadata["retry-after"])
            with body.open("rb") as file:
                document = file.read(JSON_LIMIT + 1)
            explore(document, "  ·  ".join(info), failed=int(code) >= 400)
            return 22 if int(code) >= 400 else 0
        summary = Text(text_value(status), style=f"bold {color}")
        summary.append(f"    {float(seconds)*1000:.1f} ms\n", style="#99aabb")
        for header, label in [("retry-after", "Retry after"), ("x-request-id", "Request ID"),
                              ("traceparent", "Trace")]:
            if header in metadata:
                val = metadata[header]
                if header == "retry-after" and val.isdigit():
                    val += " seconds"
                summary.append(f"\n{label}  ", style="#00e5ff")
                summary.append(text_value(val))
        with body.open("rb") as file:
            raw = file.read(8193)
        excerpt = raw[:8192].decode(errors="replace")
        try:
            obj = json.loads(excerpt)
        except ValueError:
            obj = excerpt
        message = obj
        if isinstance(obj, dict):
            message = obj.get("message") or obj.get("error") or obj.get("detail") or obj
        if raw:
            content = text_value(message)
            cropped = len(raw)>8192 or len(content)>700
            summary.append("\n\n" + content[:700] + (" …" if cropped else ""))
        console.print(Panel(summary, title="HTTP response", title_align="left", border_style=color, expand=False))
        return 22 if int(code) >= 400 else 0


def snapshot(value, keys):
    lines = value.strip("\r\n").splitlines()
    if value.lstrip().startswith("["):
        data = json.loads(value)
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            raise ValueError("Expected a JSON array of objects.")
        if not data:
            return (), {}
        header = list(dict.fromkeys(k for row in data for k in row))
        rows = [[text_value(row.get(k, "")) for k in header] for row in data]
    else:
        parsed = table_rows(lines)
        if not parsed and lines and "," in lines[0]:
            parsed = list(csv.reader(io.StringIO(value), strict=True))
        if not parsed and len(lines) == 1 and "\t" in lines[0]:
            parsed = [lines[0].split("\t")]
        if not parsed:
            raise ValueError("Expected a headed table, CSV, TSV or JSON array.")
        header, *rows = parsed
    if not header or len(set(header)) != len(header) or any(len(row)!=len(header) for row in rows):
        raise ValueError("Expected unique headers and consistent columns.")
    indices = [header.index(k) for k in keys] if keys else [0]
    result = {}
    for row in rows:
        identity = tuple(row[i] for i in indices)
        if identity in result:
            raise ValueError("Duplicate row identity. Specify --key COLUMN (repeat for a composite key).")
        result[identity] = row
    return tuple(header), result


def change_table(header, current, previous):
    table = Table(title="Report changes", title_style="bold #00e5ff",
                  border_style="#377788", header_style="bold #00e5ff")
    for name in header:
        table.add_column(Text(name), overflow="fold")
    for key, row in current.items():
        before = previous.get(key) if previous is not None else None
        added = previous is not None and before is None
        cells = []
        for i, val in enumerate(row):
            cell = Text(val, style="#39ff88" if added else "white")
            if before is not None and before[i] != val:
                cell = Text(before[i] + " → ", style="#a7b3bd")
                cell.append(val, style="bold #ffe600")
            if i == 0 and added:
                cell = Text("+ ", style="#39ff88") + cell
            cells.append(cell)
        table.add_row(*cells)
    for key, old in (previous or {}).items():
        if key not in current:
            table.add_row(*(Text(("− " if i == 0 else "") + val, style="#ff899b") for i,val in enumerate(old)))
    table.caption = "Baseline" if previous is None else "old → new  ·  + added  ·  − removed"
    return table


def watch_view(args, console):
    if not math.isfinite(args.interval) or args.interval < 0.2 or (args.count is not None and args.count < 1):
        raise ValueError("Interval must be at least 0.2 seconds and count must be positive.")
    command = command_args(args)
    header, previous = (), None
    n = 0
    with Live(console=console, auto_refresh=False) as live:
        while args.count is None or n < args.count:
            with tempfile.TemporaryFile() as out:
                proc = subprocess.run(command, stdout=out, timeout=30)
                if proc.returncode:
                    return proc.returncode if proc.returncode > 0 else 128-proc.returncode
                if out.tell() > LIMIT:
                    raise ValueError("Report exceeds the 1 MiB comparison limit.")
                out.seek(0)
                schema, current = snapshot(out.read().decode(), args.key)
            active = schema or header
            if active:
                live.update(change_table(active, current, previous if header==active else None), refresh=True)
            else:
                live.update(Text("No rows"), refresh=True)
            header, previous = active, current
            n += 1
            if args.count is None or n < args.count:
                time.sleep(args.interval)
    return 0


def main():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="view", required=True)
    test = subs.add_parser("rtest", help="Summarize a finite test command; preserve its exit status")
    test.add_argument("--full", action="store_true")
    test.add_argument("command", nargs=argparse.REMAINDER)
    http = subs.add_parser("rhttp", help="Inspect one HTTP GET response")
    http.add_argument("--explore", action="store_true", help="Browse the JSON response interactively")
    http.add_argument("url")
    watch = subs.add_parser("rwatch", help="Repeat a read-only report and compare keyed rows")
    watch.add_argument("--interval", type=float, default=2)
    watch.add_argument("--key", action="append", default=[])
    watch.add_argument("--count", type=int)
    watch.add_argument("command", nargs=argparse.REMAINDER)
    view = subs.add_parser("jview", help="Explore one JSON document from stdin or a file")
    view.add_argument("file", nargs="?")
    args = parser.parse_args()
    console = Console(markup=False, highlight=False)
    try:
        if args.view == "jview":
            if args.file:
                with open(args.file, "rb") as f:
                    raw = f.read(JSON_LIMIT + 1)
            elif not sys.stdin.isatty():
                raw = sys.stdin.buffer.read(JSON_LIMIT + 1)
            else:
                raise ValueError("Pipe JSON into jview, or provide a JSON file.")
            explore(raw)
            return 0
        return {"rtest":test_view, "rwatch":watch_view, "rhttp":http_view}[args.view](args, console)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, csv.Error, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
