"""Keyboard JSON inspector. All views refer to one immutable response."""

import curses
import json
import os
import re
import subprocess
import sys

LIMIT = 8 * 1024 * 1024
MISSING = object()


class Number(str):
    """Keep JSON's original numeric spelling and precision."""


def encode(value):
    if isinstance(value, Number):
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(map(encode, value)) + "]"
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(json.dumps(k) + ":" + encode(v) for k, v in value.items())
            + "}"
        )
    return json.dumps(value, ensure_ascii=True)


def summary(value):
    if value is MISSING:
        return "— missing"
    if isinstance(value, dict):
        return "{%d fields}" % len(value)
    if isinstance(value, list):
        return "[%d items]" % len(value)
    if isinstance(value, str) and not isinstance(value, Number):
        return json.dumps(value, ensure_ascii=False)
    return encode(value)


def jq_path(path):
    result = ""
    for key in path:
        if isinstance(key, str) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", key):
            result += "." + key
        else:
            result = (result or ".") + "[" + json.dumps(key) + "]"
    return result or "."


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(
                "Duplicate JSON field; use the original response to inspect it."
            )
        result[key] = value
    return result


def invalid(token):
    raise ValueError(f"Invalid JSON constant: {token}")


def children(value):
    if isinstance(value, dict):
        return value.items()
    if isinstance(value, list):
        return enumerate(value)
    return ()


class Document:
    def __init__(self, raw):
        if len(raw) > LIMIT:
            raise ValueError("JSON explorer limit is 8 MiB.")
        self.raw = raw.decode("utf-8-sig")
        self.root = json.loads(
            self.raw,
            parse_int=Number,
            parse_float=Number,
            parse_constant=invalid,
            object_pairs_hook=unique,
        )
        self.nodes = {}
        self.records = []
        self._index((), self.root)
        self.errors = self._errors()

    def _index(self, path, value):
        if len(self.nodes) >= 100000 or len(path) > 128:
            raise ValueError("JSON explorer limit is 100,000 nodes and 128 levels.")
        self.nodes[path] = value
        if (
            isinstance(value, list)
            and value
            and all(isinstance(row, dict) for row in value)
        ):
            self.records.append(path)
        for key, item in children(value):
            self._index((*path, key), item)

    def find(self, query):
        needle = query.casefold()
        return [
            p
            for p, v in self.nodes.items()
            if (p and needle in str(p[-1]).casefold())
            or (not isinstance(v, (dict, list)) and needle in summary(v).casefold())
        ]

    def clipboard_text(self, path, *, copy_path=False, raw=False):
        if copy_path:
            return "." if raw else jq_path(path)
        if raw:
            return self.raw
        value = self.nodes[path]
        return str(value) if isinstance(value, str) else encode(value)

    def _errors(self):
        if not isinstance(self.root, dict):
            return []
        rows = []
        for key in ("errors", "detail", "error", "message"):
            value = self.root.get(key)
            if (
                isinstance(value, dict)
                and key == "error"
                and isinstance(value.get("message"), str)
            ):
                rows.append(("error", value["message"], (key, "message")))
            elif isinstance(value, dict) and key == "errors":
                for field, reasons in value.items():
                    if isinstance(reasons, list):
                        rows.extend(
                            (str(field), text_value, (key, field, i))
                            for i, text_value in enumerate(map(str, reasons))
                        )
                    else:
                        rows.append((str(field), str(reasons), (key, field)))
            elif isinstance(value, list):
                for i, detail in enumerate(value):
                    if not isinstance(detail, dict):
                        continue
                    field = detail.get("loc", detail.get("field", "response"))
                    if isinstance(field, list):
                        field = "".join(
                            f"[{n}]" if isinstance(n, Number) else "." + str(n)
                            for n in field
                        ).lstrip(".")
                    reason = (
                        detail.get("msg")
                        or detail.get("message")
                        or detail.get("reason")
                        or detail.get("detail")
                    )
                    if reason:
                        rows.append((str(field), str(reason), (key, i)))
            elif isinstance(value, str):
                rows.append((key, value, (key,)))
        return rows


def safe(text):
    return "".join(c if c.isprintable() else ascii(c)[1:-1] for c in str(text))


class Viewer:
    modes = ("tree", "table", "raw", "errors")

    def __init__(self, doc, metadata="", failed=False):
        self.doc, self.metadata, self.failed = doc, metadata, failed
        self.mode = (
            "errors"
            if failed and doc.errors
            else "table"
            if () in doc.records
            else "tree"
        )
        self.dataset = doc.records[0] if doc.records else None
        self.open = {()}
        self.pos = self.column = self.offset = 0
        self.message = ""
        self.hits = []
        self.hit = 0
        self.raw_lines = doc.raw.splitlines() or [""]
        self.schemas = {
            path: list(dict.fromkeys(k for row in doc.nodes[path] for k in row))
            for path in doc.records
        }

    def tree(self):
        def visit(path):
            yield path
            if path in self.open:
                for key, _ in children(self.doc.nodes[path]):
                    yield from visit((*path, key))

        return list(visit(()))

    def table(self):
        return self.doc.nodes[self.dataset], self.schemas[self.dataset]

    def focus(self, path):
        self.mode, self.offset = "tree", 0
        self.open.update(path[:i] for i in range(len(path)))
        self.pos = self.tree().index(path)

    def switch(self, mode):
        pos = column = 0
        if mode == "table":
            if not self.doc.records:
                self.message = "No array of records in this response"
                return
            ancestors = [p for p in self.doc.records if self.path[: len(p)] == p]
            self.dataset = max(ancestors, key=len) if ancestors else self.dataset
            suffix = self.path[len(self.dataset) :] if ancestors else ()
            if suffix and isinstance(suffix[0], int):
                pos = suffix[0]
                if len(suffix) > 1 and suffix[1] in self.schemas[self.dataset]:
                    column = self.schemas[self.dataset].index(suffix[1])
        if mode == "errors" and not self.doc.errors:
            self.message = "No recognized error fields in this response"
            return
        self.mode, self.pos, self.column, self.offset = mode, pos, column, 0

    def put(self, y, x, text, color=0, bold=False, width=None):
        room = self.w - x - 1
        if room <= 0 or not 0 <= y < self.h:
            return
        attr = curses.color_pair(color) | (curses.A_BOLD if bold else 0)
        try:
            self.screen.addnstr(
                y, x, safe(text), min(room, width if width is not None else room), attr
            )
        except curses.error:
            pass  # Window may have resized during this frame.

    def paint(self):
        s = self.screen
        self.h, self.w = s.getmaxyx()
        s.erase()
        self.put(0, 1, "JSON", 1, True)
        self.put(0, 7, self.metadata or "Response explorer", 3 if self.failed else 2)
        x = 1
        for i, mode in enumerate(self.modes, 1):
            label = f"{i} {mode.upper()}"
            self.put(2, x, label, 1 if mode == self.mode else 0, mode == self.mode)
            x += len(label) + 3
        self.put(3, 1, "─" * max(0, self.w - 3), 1)
        height = max(1, self.h - 9)
        self.path = ()
        self.missing = False
        if self.mode == "tree":
            paths = self.tree()
            self.length = len(paths)
        elif self.mode == "table":
            rows, keys = self.table()
            self.length = len(rows)
        else:
            self.length = len(self.raw_lines if self.mode == "raw" else self.doc.errors)
        self.pos = max(0, min(self.pos, self.length - 1))
        start = (self.pos // height) * height
        if self.mode == "table":
            self.put(4, 1, f"{jq_path(self.dataset)}   ·   {len(rows)} records", 2)
            cell = max(12, min(24, (self.w - 4) // max(1, len(keys))))
            slots = max(1, (self.w - 4) // cell)
            first = (self.column // slots) * slots
            for i, key in enumerate(keys[first : first + slots]):
                self.put(5, 3 + i * cell, key, 1, True, cell - 1)
        elif self.mode == "tree":
            self.put(4, 1, "Fields   ·   Enter to expand or collapse", 1)
        elif self.mode == "errors":
            self.put(4, 1, "Validation details   ·   Enter to inspect the source", 3)
        else:
            self.put(4, 1, "Original response   ·   ← → scroll horizontally", 1)
        for i in range(start, min(self.length, start + height)):
            y = 6 + i - start
            selected = i == self.pos
            self.put(y, 0, "›" if selected else " ", 2, True)
            if self.mode == "tree":
                path = paths[i]
                val = self.doc.nodes[path]
                if selected:
                    self.path = path
                leaf = not isinstance(val, (dict, list))
                icon = " " if leaf else "▾" if path in self.open else "▸"
                x = min(2 * len(path) + 2, max(2, self.w // 3))
                key = str(path[-1]) if path else "$"
                self.put(y, x, icon + " " + key, 1, selected)
                self.put(
                    y, x + 3 + len(key), summary(val), 2 if selected else 0, selected
                )
            elif self.mode == "table":
                for j, key in enumerate(keys[first : first + slots]):
                    val = rows[i].get(key, MISSING)
                    active = selected and j + first == self.column
                    if active:
                        self.missing = val is MISSING
                        self.path = (*self.dataset, i, key)
                    label = summary(val)
                    if len(label) > cell - 1:
                        label = label[: cell - 2] + "…"
                    self.put(
                        y, 3 + j * cell, label, 2 if active else 0, active, cell - 1
                    )
                if selected and not keys:
                    self.path = (*self.dataset, i)
            elif self.mode == "errors":
                field, reason, path = self.doc.errors[i]
                if selected:
                    self.path = path
                self.put(y, 3, field, 3, True)
                self.put(y, 5 + len(field), reason, 0)
            else:
                self.put(y, 3, self.raw_lines[i][self.offset :])
        self.put(
            self.h - 3,
            1,
            self.message
            or (
                jq_path(self.path)
                if self.mode != "raw"
                else f"Source line {self.pos + 1}"
            ),
            2,
        )
        self.put(
            self.h - 2,
            1,
            "↑↓ move  ←→ browse  Enter open  / find  n next  y copy  p path  q quit",
        )
        s.refresh()

    def search(self):
        query = ""
        while True:
            self.screen.move(self.h - 3, 0)
            self.screen.clrtoeol()
            self.put(self.h - 3, 1, "Search keys and values: " + query, 1)
            self.screen.refresh()
            key = self.screen.get_wch()
            if key in ("\x1b", curses.KEY_RESIZE):
                return
            if key in ("\n", "\r"):
                break
            if key in ("\x7f", "\b", curses.KEY_BACKSPACE):
                query = query[:-1]
            elif isinstance(key, str) and key.isprintable():
                query += key
        if not query:
            return
        self.hits = self.doc.find(query)
        self.hit = 0
        self.goto_hit()

    def goto_hit(self):
        if self.hits:
            self.focus(self.hits[self.hit])
            self.message = (
                f"{self.hit + 1}/{len(self.hits)}   {jq_path(self.hits[self.hit])}"
            )
        else:
            self.message = "No matches"

    def run(self, screen):
        self.screen = screen
        screen.keypad(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            for i, color in enumerate(
                (curses.COLOR_CYAN, curses.COLOR_GREEN, curses.COLOR_RED), 1
            ):
                curses.init_pair(i, color, -1)
        while True:
            self.paint()
            key = screen.get_wch()
            self.message = ""
            if key in ("q", "\x1b"):
                return
            if key in ("1", "2", "3", "4"):
                self.switch(self.modes[int(key) - 1])
            elif key in ("j", curses.KEY_DOWN):
                self.pos += 1
            elif key in ("k", curses.KEY_UP):
                self.pos -= 1
            elif key in (curses.KEY_NPAGE, curses.KEY_PPAGE):
                self.pos += (1 if key == curses.KEY_NPAGE else -1) * max(1, self.h - 9)
            elif key == "/" and self.h >= 4:
                self.search()
            elif key in ("n", "N") and self.hits:
                self.hit = (self.hit + (1 if key == "n" else -1)) % len(self.hits)
                self.goto_hit()
            elif key in ("y", "p"):
                if self.missing and key == "y":
                    self.message = "This field is absent"
                    continue
                payload = self.doc.clipboard_text(
                    self.path, copy_path=key == "p", raw=self.mode == "raw"
                )
                proc = subprocess.run(
                    ["pbcopy"], input=payload.encode("utf-8", "backslashreplace")
                )
                self.message = (
                    "Copied " + ("path" if key == "p" else "value")
                    if proc.returncode == 0
                    else "Clipboard unavailable"
                )
            elif key in (
                "\n",
                "\r",
                curses.KEY_ENTER,
                curses.KEY_RIGHT,
                curses.KEY_LEFT,
            ):
                right = key != curses.KEY_LEFT
                if self.mode == "tree":
                    if not right and self.path not in self.open and self.path:
                        self.focus(self.path[:-1])
                    elif not right:
                        self.open.discard(self.path)
                    elif isinstance(self.doc.nodes[self.path], (dict, list)):
                        if (
                            key in ("\r", "\n", curses.KEY_ENTER)
                            and self.path in self.open
                        ):
                            self.open.remove(self.path)
                        else:
                            self.open.add(self.path)
                elif self.mode == "table" and key in (
                    curses.KEY_RIGHT,
                    curses.KEY_LEFT,
                ):
                    self.column = max(
                        0,
                        min(
                            len(self.table()[1]) - 1, self.column + (1 if right else -1)
                        ),
                    )
                elif self.mode == "raw":
                    self.offset = max(0, self.offset + (20 if right else -20))
                elif self.mode == "table":
                    row = (*self.dataset, self.pos)
                    self.open.add(row)
                    self.focus(row)
                else:
                    self.open.add(self.path)
                    self.focus(self.path)


def explore(raw, metadata="", failed=False):
    try:
        doc = Document(raw)
    except RecursionError:
        raise ValueError("JSON is too deeply nested.") from None
    if not sys.stdout.isatty():
        raise ValueError(
            "Open jview in an interactive terminal; use pretty json for redirected output."
        )
    # Piped JSON occupies stdin. Once consumed, curses needs the controlling tty.
    fd = os.open("/dev/tty", os.O_RDONLY)
    try:
        saved = os.dup(0)
        try:
            os.dup2(fd, 0)
            curses.wrapper(Viewer(doc, metadata, failed).run)
        finally:
            os.dup2(saved, 0)
            os.close(saved)
    finally:
        os.close(fd)
