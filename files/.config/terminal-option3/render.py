"""Render finite command output, preserving data when its structure is ambiguous."""
import csv
import io
import json
import re
import shutil
import sys
from itertools import groupby

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.syntax import Syntax
from log_stream import classify, stream
from failure_views import draw_failure, failures


def csv_rows(value, explicit):
    try:
        rows = list(csv.reader(io.StringIO(value, newline=""), strict=True))
    except csv.Error:
        return None
    if not rows or len(rows[0]) < 2 or any(len(row) != len(rows[0]) for row in rows):
        return None
    if not explicit:
        # "Hello, world" is prose too. Require a plausible schema and evidence
        # from the data before interpreting commas as column separators.
        header = rows[0]
        if (len(rows) < 2 or len(set(header)) != len(header)
                or not all(re.fullmatch(r"[A-Za-z_][\w.-]*", col) for col in header)):
            return None
        if len(header) == 2 and '"' not in value and not any(
                re.fullmatch(r"-?\d+(?:\.\d+)?", cell) for row in rows[1:] for cell in row):
            return None
    return rows


def render_diagnostic(console, value):
    summaries = failures(value)
    for failure in summaries:
        draw_failure(console, failure)
    is_diff = (value.startswith("diff --git ") or
               re.search(r"(?m)^--- .+\n\+\+\+ .+\n@@ ", value))
    is_trace = (re.search(r"(?m)^Traceback \(most recent call last\):", value) or
                re.search(r"(?m)^\s+at [\w.$/]+\([^\n()]+\)", value))
    is_log = re.search(r"(?m)^\[?\d{4}-\d\d-\d\d[T ][\d:.]+", value)
    if not (summaries or is_diff or is_trace or is_log):
        return False
    text = Text(value)
    if is_diff:
        text.highlight_regex(r"(?m)^\+.*$", "#39ff88")
        text.highlight_regex(r"(?m)^-.*$", "#ff687e")
        text.highlight_regex(r"(?m)^(?:diff --git |@@|\+\+\+ |--- ).*$", "bold #00e5ff")
    else:
        text.highlight_regex(r'(?m)^Traceback[^\n]*|\b[\w.]+(?:Exception|Error)\b', "bold #ff687e")
        text.highlight_regex(r'"[^"\n]+", line \d+|[\w.$/-]+\.java:\d+', "#00e5ff")
        text.highlight_regex(r"\d{4}-\d\d-\d\d[T ][\d:.]+", "#82bbff")
        text.highlight_regex(r"(?i)\b(error|fatal|failed)\b", "bold #ff687e")
        text.highlight_regex(r"(?i)\b(warn|warning)\b", "#ffe600")
        text.highlight_regex(r"(?i)\b(info|ready|ok)\b", "#39ff88")
    console.print(text, end="", soft_wrap=True)
    return True


def table_rows(lines):
    if not lines:
        return None
    if len(lines) < 2:
        return None
    if all("\t" in line for line in lines):
        rows = [line.split("\t") for line in lines]
        if len({len(row) for row in rows}) == 1:
            return rows
    # Some reports mix left-aligned names with right-aligned numbers. A single
    # shared whitespace position between adjacent cells is a valid boundary.
    words = [list(re.finditer(r"\S+", line)) for line in lines]
    header = words[0]
    if (3 <= len(header) <= 24 and all(len(row) == len(header) for row in words)
            and all(re.fullmatch(r"[\w#%][\w#%.-]*", cell[0]) for cell in header)
            and any(re.search(r"\S {2,}\S", line) for line in lines)
            and any(re.match(r"\d", cell[0]) for row in words[1:] for cell in row)
            and all(max(row[i].end() for row in words) < min(row[i+1].start() for row in words)
                    for i in range(len(header) - 1))):
        return [[cell[0] for cell in row] for row in words]
    # Other reports have multiword column names or cells.
    columns = list(re.finditer(r"[^ ]+(?: [^ ]+)*", lines[0].rstrip()))
    if len(columns) < 2:
        return None
    if not all(re.fullmatch(r"[\w%#][\w%# ./()_-]{0,28}", col[0]) for col in columns):
        return None
    starts = [col.start() for col in columns]
    if starts[0] != 0 or any(not line.strip() for line in lines[1:]) or any(
            line[i-1:i].strip() for line in lines[1:] for i in starts[1:]):
        return None
    return [[line[start:end].strip() for start, end in zip(starts, starts[1:] + [None])]
            for line in lines]


def render():
    limit = 1024 * 1024
    first = sys.stdin.buffer.readline(limit)
    if sys.argv[1] == "log" or (sys.argv[1] == "auto" and len(first) < limit and classify(first) is not None):
        stream(first)
        return
    raw = first + sys.stdin.buffer.read(limit - len(first))
    if len(raw) == 1024 * 1024 or re.search(rb"[\x00-\x08\x0b-\x0c\x0e-\x1f]|\r(?!\n)", raw):
        sys.stdout.buffer.write(raw)
        shutil.copyfileobj(sys.stdin.buffer, sys.stdout.buffer)
        return
    try:
        value = raw.decode()
    except UnicodeDecodeError:
        sys.stdout.buffer.write(raw)
        return
    console = Console(highlight=False, markup=False)
    is_help = re.search(r"(?im)^usage:\s+", value[:1200])
    if sys.argv[1] == "help" or (sys.argv[1] == "auto" and is_help):
        text = Text(value)
        text.highlight_regex(r"(?m)^Usage:|^[^\s\n][^:\n]*:(?=\s*$)", "bold #00e5ff")
        text.highlight_regex(r"(?m)^  [a-z][\w-]*(?=\s{2,})", "bold #39ff88")
        text.highlight_regex(r"(?<!\S)--?[\w][\w-]*", "#39ff88")
        text.highlight_regex(r"<[^>\n]+>|\[[^\]\n]+\]", "#ff55ff")
        console.print(text, end="", soft_wrap=True)
        return
    if sys.argv[1] == "auto" and value.lstrip().startswith(("{", "[")):
        try:
            json.loads(value)
        except ValueError:
            pass
        else:
            # jq pretty-prints without Python converting numeric values.
            import subprocess
            flags = ["-C"] if sys.stdout.isatty() else []
            sys.exit(subprocess.run(["jq", *flags, "."], input=raw).returncode)
    lines = value.splitlines()
    if (len(lines) > 1 and all(line.startswith("{") for line in
                               (line.lstrip() for line in lines))):
        try:
            for line in lines:
                json.loads(line)
        except ValueError:
            pass
        else:
            console.print(Syntax(value.rstrip("\r\n"), "json", theme="monokai",
                                 background_color="default", word_wrap=True))
            return
    if render_diagnostic(console, value):
        return
    if lines and "," in lines[0]:
        csv_data = csv_rows(value, sys.argv[1] == "csv")
        if csv_data:
            print_table(console, csv_data)
            return
    # Repeated "Field: value" records can contain a summary and detail rows
    # with different columns. Match field boundaries, never colons inside values.
    records = []
    for line in lines:
        parts = re.split(r"(?:\t+| {2,})(?=[A-Za-z][\w.-]*:)", line.strip())
        fields = [re.fullmatch(r"([A-Za-z][\w.-]*):[ \t]*(.*)", part) for part in parts]
        if len(parts) < 2 or not all(fields):
            break
        records.append(([f[1] for f in fields], [f[2] for f in fields]))
    if records and len(records) == len(lines):
        for headers, group in groupby(records, key=lambda record: record[0]):
            data = [record[1] for record in group]
            if len(data) == 1:
                print_table(console, [["Field", "Value"], *zip(headers, data[0])])
            else:
                print_table(console, [headers, *data])
        return
    pairs = [re.fullmatch(r"([A-Za-z][\w .()-]{0,40}):[ \t]+(.+)", line) for line in lines]
    if len(pairs) >= 2 and all(pairs):
        rows = [["Field", "Value"], *(list(pair.groups()) for pair in pairs)]
    else:
        rows = table_rows(value.strip("\r\n").splitlines())
    if rows and len(rows) > 1 and all(re.fullmatch(r"-+", cell) for cell in rows[1]):
        rows.pop(1)
    if not rows:
        text = Text(value)
        text.highlight_regex(r"(?m)^Created topic\b", "bold #39ff88")
        text.highlight_regex(r"(?m)(?<=^Created topic )[^\n]+(?=\.$)", "bold #00e5ff")
        text.highlight_regex(r"(?m)^\s*[A-Za-z][\w ./()-]{0,38}:(?=[ \t])", "bold #00e5ff")
        text.highlight_regex(r"\b\d+(?:\.\d+){1,3}\b", "#ff90ee")
        text.highlight_regex(r"(?i)\b(error|failed|fatal|unhealthy)\b", "bold #ff5577")
        text.highlight_regex(r"(?i)\b(warn|warning|pending)\b", "#ffe600")
        text.highlight_regex(r"(?i)\b(ok|ready|running|success|healthy)\b", "#39ff88")
        console.print(text, end="", soft_wrap=True)
        return
    print_table(console, rows)


def print_table(console, rows):
    headers = rows[0]
    # Long IDs can make even a full-width terminal unreadable. Account for
    # actual cell widths, including the borders and padding between columns.
    natural_width = 1 + sum(3 + max(len(str(cell)) for cell in column)
                            for column in zip(*rows))
    compact = len(rows) > 1 and (console.width < 10 * len(headers)
                                or (len(headers) >= 6 and natural_width > console.width))
    table = Table(box=box.ROUNDED, border_style="#377788", header_style="bold #00e5ff",
                  show_header=not compact, show_lines=compact, padding=(0, 1))
    if compact:
        table.add_column()
        for row in rows[1:]:
            card = Text()
            for pos, (header, cell) in enumerate(zip(headers, row)):
                if pos:
                    card.append("\n")
                card.append(header + "  ", style="bold #00e5ff")
                card.append(cell or "—")
            table.add_row(card)
    else:
        for index, header in enumerate(headers):
            table.add_column(Text(header), style="#72ffad" if index == 0 else "#cfedef",
                             overflow="fold")
        for row in rows[1:]:
            cells = [Text(cell) for cell in row]
            for cell in cells:
                cell.highlight_regex(r"(?i)\b(up|healthy|ready|running|ok)\b", "bold #39ff88")
                cell.highlight_regex(r"(?i)\b(restarting|pending|warning)\b", "bold #ffe600")
                cell.highlight_regex(r"(?i)\b(exited|unhealthy|failed|error)\b", "bold #ff5577")
            table.add_row(*cells)
    console.print(table)


if __name__ == "__main__":
    try:
        render()
    except BrokenPipeError:
        pass
