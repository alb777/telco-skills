#!/usr/bin/env python3
"""Record docs/demo.gif from real telcode and Claude Code output.

The commands are typed out in an asciicast and rendered with agg. Every output
shown is captured from a real run: telcode through a `telcode` symlink, and a
headless Claude Code session with this repository loaded as a plugin. The
script fails if that session does not use the telcode skill. Claude's markdown
answer is word-wrapped and its bold and code spans are colored, as an
interactive session would render them; the text itself is unchanged.

Needs `agg` (https://github.com/asciinema/agg) and `claude` on PATH.
Usage: python3 tools/record_demo.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIF = ROOT / "docs" / "demo.gif"
COLS, ROWS = 104, 20
PROMPT = "\x1b[1;32m$\x1b[0m "
COMMENT = "\x1b[2m"
RESET = "\x1b[0m"
QUESTION = "S6a ULA returned Experimental-Result-Code 5420. What does it mean? Keep it short."


class Cast:
    """An asciicast v2 recording built event by event."""

    def __init__(self) -> None:
        self.clock = 0.0
        self.events: list[tuple[float, str]] = []

    def out(self, text: str, delay: float = 0.0) -> None:
        self.clock += delay
        self.events.append((round(self.clock, 3), text.replace("\n", "\r\n")))

    def type(self, command: str, style: str = "") -> None:
        self.out(PROMPT + style, 0.5)
        for char in command:
            self.out(char, 0.04)
        self.out(RESET + "\n", 0.4)

    def lines(self, text: str, step: float = 0.0, pause: float = 0.0) -> None:
        for i, line in enumerate(text.rstrip("\n").split("\n")):
            self.out(line + "\n", step + (pause if i == 0 else 0.0))

    def clear(self, pause: float) -> None:
        self.out("\x1b[2J\x1b[H", pause)

    def write(self, path: Path) -> None:
        header = {"version": 2, "width": COLS, "height": ROWS, "env": {"TERM": "xterm-256color"}}
        rows = [json.dumps(header)] + [json.dumps([t, "o", text]) for t, text in self.events]
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def as_terminal(markdown: str) -> str:
    """Word-wrap Claude's markdown answer to the terminal width and show bold and code spans in color."""
    lines = []
    for line in markdown.splitlines():
        marker = re.match(r"\s*(?:[-*]|\d+\.)\s+", line)
        indent = " " * (marker.end() if marker else 0)
        lines.append(textwrap.fill(line, COLS - 2, subsequent_indent=indent) if line.strip() else "")
    text = re.sub(r"\*\*(.+?)\*\*", "\x1b[1m\\1\x1b[22m", "\n".join(lines), flags=re.S)
    return re.sub(r"`([^`\n]+)`", "\x1b[36m\\1\x1b[39m", text)


def telcode(bin_dir: Path, *args: str) -> str:
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    done = subprocess.run(["telcode", *args], env=env, capture_output=True, text=True, check=True)
    return done.stdout


def ask_claude(workdir: Path) -> str:
    """Run a real headless Claude Code session with the plugin and return its answer."""
    done = subprocess.run(
        [
            "claude",
            "-p",
            QUESTION,
            "--plugin-dir",
            str(ROOT),
            "--setting-sources",
            "project",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--allowedTools",
            "Bash(python3:*)",
            "--output-format",
            "stream-json",
            "--verbose",
        ],
        cwd=workdir,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )
    used_skill = False
    answer = ""
    for line in done.stdout.splitlines():
        event = json.loads(line)
        if event.get("type") == "assistant":
            for block in event["message"].get("content", []):
                if block.get("type") == "tool_use" and block.get("input", {}).get("skill", "").endswith("telcode"):
                    used_skill = True
        if event.get("type") == "result":
            answer = event.get("result", "")
    if not used_skill or not answer:
        raise SystemExit("the Claude Code session did not use the telcode skill, not recording a demo of it")
    return answer


def main() -> int:
    agg = shutil.which("agg")
    if not agg or not shutil.which("claude"):
        raise SystemExit("needs agg and claude on PATH")
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        (tmpdir / "bin").mkdir()
        (tmpdir / "bin" / "telcode").symlink_to(ROOT / "skills" / "telcode" / "scripts" / "telcode.py")
        answer = ask_claude(tmpdir)

        cast = Cast()
        cast.type("telcode 5001")
        cast.lines(telcode(tmpdir / "bin", "5001"), 0.03)
        cast.clear(5.0)
        cast.type("telcode search absent")
        cast.lines(telcode(tmpdir / "bin", "search", "absent"), 0.03)
        cast.type("telcode tbcd 62 02 11 32 54 76 98 f0")
        cast.lines(telcode(tmpdir / "bin", "tbcd", "62", "02", "11", "32", "54", "76", "98", "f0"))
        cast.clear(4.0)
        cast.type("# Claude Code with the telco-skills plugin installed", COMMENT)
        cast.type(f'claude -p "{QUESTION}"')
        cast.lines(as_terminal(answer), 0.08, pause=2.5)

        cast_path = tmpdir / "demo.cast"
        cast.write(cast_path)
        GIF.parent.mkdir(exist_ok=True)
        render = [agg, "--theme", "github-dark", "--font-family", "DejaVu Sans Mono", "--font-size", "16"]
        subprocess.run([*render, "--last-frame-duration", "8", str(cast_path), str(GIF)], check=True)
    print(f"{GIF.relative_to(ROOT)}: {GIF.stat().st_size / 1024:.0f} KiB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
