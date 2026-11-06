"""Incremental log display shared by pretty, show, and streaming producers."""
import json
import re
import sys

from rich.console import Console
from rich.text import Text

LEVEL = re.compile(r"\b(TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|FATAL|CRITICAL)\b", re.I)
STAMP = re.compile(r"\d{4}-\d\d-\d\d[T ][\d:.]+(?:Z|[+-]\d\d:\d\d)?")
COLORS = {"INFO": "#39ff88", "WARN": "#ffe600", "WARNING": "#ffe600",
          "ERROR": "#ff5577", "FATAL": "#ff5577", "CRITICAL": "#ff5577"}
LIMIT = 1024 * 1024


def classify(raw):
    try:
        value = raw.decode()
    except UnicodeDecodeError:
        return None
    if raw.lstrip().startswith(b"{"):
        try:
            obj = json.loads(value)
        except (ValueError, RecursionError):
            return None
        if isinstance(obj, dict) and any(k in obj for k in ("message", "msg")) and any(
                k in obj for k in ("log.level", "level", "severity", "@timestamp", "timestamp", "time")):
            return obj
    if STAMP.match(value.lstrip(" [")) and LEVEL.search(value):
        return value
    return None


def display(obj):
    parts = obj.copy()

    def take(*keys):
        for key in keys:
            if key in parts:
                val = parts.pop(key)
                if isinstance(val, str):
                    # JSON escaping is a data boundary. Never turn a logged
                    # "\\u001b" or C1 control into a terminal instruction.
                    return "".join(ch if ch.isprintable() or ch in "\n\t"
                                   else ascii(ch)[1:-1] for ch in val)
                return json.dumps(val, ensure_ascii=True)
        return ""

    time = take("@timestamp", "timestamp", "time")
    level = take("log.level", "level", "severity")
    logger = take("log.logger", "logger")
    msg = take("message", "msg")
    line = Text("▌ ", style="#00e5ff")
    line.append(time + "  ", style="#8dbfff")
    line.append(level, style="bold " + COLORS.get(level.upper(), "#cfbfff"))
    line.append("  " + logger + "\n  " if logger else "  ", style="#00e5ff")
    line.append(msg, style="#ffffff")
    if parts:
        line.append("\n  " + json.dumps(parts, ensure_ascii=True), style="#a7b3bd")
    return line


def stream(first):
    console = Console(highlight=False, markup=False)
    raw = first
    while raw:
        if len(raw) >= LIMIT or re.search(rb"[\x00-\x08\x0b-\x1f]", raw.rstrip(b"\r\n")):
            sys.stdout.buffer.write(raw)
        else:
            item = classify(raw)
            if isinstance(item, dict):
                console.print(display(item))
            else:
                try:
                    text = Text(raw.decode())
                except UnicodeDecodeError:
                    sys.stdout.buffer.write(raw)
                else:
                    text.highlight_regex(STAMP, "#8dbfff")
                    for match in LEVEL.finditer(text.plain):
                        text.stylize("bold " + COLORS.get(match[0].upper(), "#cfbfff"), *match.span())
                    console.print(text, end="", soft_wrap=True)
        sys.stdout.flush()
        raw = sys.stdin.buffer.readline(LIMIT)
