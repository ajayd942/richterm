"""Summaries grounded in stack frames and assertion text emitted by the program."""
from dataclasses import dataclass
from pathlib import Path
import re

from rich.panel import Panel
from rich.text import Text


@dataclass
class Failure:
    title: str
    error: str
    location: str
    comparison: tuple | None = None


def failures(output):
    if not any(marker in output for marker in ("Traceback (", "AssertionFailedError:", "AssertionError:", "ComparisonFailure:")):
        return []
    plain = re.sub(r"\x1b\[[0-9;]*m", "", output)
    found = []
    for trace in plain.split("Traceback (most recent call last):")[1:]:
        frames = list(re.finditer(r'^\s*File "([^"\n]+)", line (\d+), in ([^\n]+)', trace, re.M))
        error = re.search(r"^((?:[\w.]*?(?:Error|Exception|Interrupt|Exit)|StopIteration)(?::[^\n]*)?)$", trace, re.M)
        if frames and error:
            relevant = [f for f in frames if f.start() < error.start()]
            if relevant:
                path, line, name = relevant[-1].groups()
                if Path(path).is_absolute() and Path(path).is_relative_to(Path.cwd()):
                    path = str(Path(path).relative_to(Path.cwd()))
                found.append(Failure(name, error[1], f"{path}:{line}"))
    # JUnit console and Maven/Surefire both include Class.method(File.java:line).
    errors = list(re.finditer(r"(?m)^.*?\b((?:[\w$]+\.)*(?:AssertionFailedError|AssertionError|ComparisonFailure)):\s*([^\n]*)", plain))
    for i, error in enumerate(errors):
        section = plain[error.end():errors[i+1].start() if i+1 < len(errors) else None]
        frames = re.finditer(r"(?:^|\s)(?:at )?([\w.$]+)\(([\w.$-]+\.java:\d+)\)", section)
        frame = next((f for f in frames if not f[1].startswith(
            ("org.junit.", "junit.", "org.opentest4j.", "org.assertj.", "java.", "jdk.", "sun."))), None)
        if frame:
            message = error[2].strip()
            values = re.search(r"expected:\s*<(.*?)>\s*but was:\s*<(.*?)>", message)
            sources = re.findall(r"MethodSource \[className = '([^']+)', methodName = '([^']+)'",
                                 plain[errors[i-1].end() if i else 0:error.start()])
            title = ".".join(sources[-1]) if sources else frame[1]
            found.append(Failure(title, message, frame[2], values.groups() if values else None))
    return found


def draw_failure(console, failure):
    body = Text(failure.title, style="bold white")
    body.append("\n" + failure.location, style="bold #00e5ff")
    if failure.comparison:
        expected, actual = failure.comparison
        body.append("\nexpected  ", style="#99aabb")
        body.append(expected, style="#39ff88")
        body.append("    actual  ", style="#99aabb")
        body.append(actual, style="bold #ff5577")
        context = failure.error.split("expected:", 1)[0].removesuffix(" ==> ").strip()
        if context:
            body.append("\n" + context)
    else:
        body.append("\n" + failure.error, style="#ff899b")
    console.print(Panel(body, title="Failure", title_align="left", border_style="#ff5577", expand=False))
