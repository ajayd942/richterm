"""Display Docker's resource counters as a terminal-sized, refreshing table."""
import json
import subprocess
import sys
import time

from rich import box
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text


def sample(args, width):
    result = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", *args],
        stdout=subprocess.PIPE, check=True, text=True,
    )
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    fields = [("Name", "Container"), ("ID", "ID"), ("CPUPerc", "CPU"),
              ("MemUsage", "Memory / limit"), ("MemPerc", "Mem %"),
              ("NetIO", "Network I/O"), ("BlockIO", "Disk I/O"), ("PIDs", "PIDs")]
    table = Table(title=f"Docker stats  ·  {time.strftime('%H:%M:%S')}",
                  title_style="bold #00e5ff", header_style="bold #00e5ff",
                  border_style="#377788", box=box.ROUNDED, highlight=False)
    if width < 105:
        table.add_column("Metric", style="#72ffad")
        table.add_column("Value")
        for row in rows:
            for i, (key, label) in enumerate(fields):
                table.add_row(label, Text(row[key]), end_section=i == len(fields) - 1)
    else:
        for key, label in fields:
            table.add_column(label, style="#72ffad" if key == "Name" else "#cfedef")
        for row in rows:
            table.add_row(*(Text(row[key]) for key, _ in fields))
    if not rows:
        table.caption = "No containers matched"
    return table


def main(args):
    console = Console()
    options = [arg for arg in args if arg != "--no-stream"]
    first = sample(options, console.width)
    if "--no-stream" in args:
        console.print(first)
        return
    with Live(first, console=console, auto_refresh=False) as live:
        live.refresh()
        while True:
            time.sleep(1)
            live.update(sample(options, console.width), refresh=True)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        sys.exit(130)
    except subprocess.CalledProcessError as err:
        sys.exit(err.returncode)
