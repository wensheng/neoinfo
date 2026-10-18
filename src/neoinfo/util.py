"""Small helpers shared by collectors and display code."""

from __future__ import annotations

import os
import shutil
import subprocess


def read_text(path: str) -> str | None:
    """Return file contents, or None when unreadable. Monkeypatch point."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def read_line(path: str) -> str | None:
    text = read_text(path)
    if text is None:
        return None
    return text.split("\n", 1)[0].strip()


def run(argv: list[str], timeout: int = 10) -> str | None:
    """Run a command, return stdout (stripped of trailing newline) or None."""
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            text=True,
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def trim(text: str) -> str:
    """Collapse all whitespace runs to single spaces and strip.

    Mirrors neofetch's trim(): word-split then rejoin with single spaces.
    """
    return " ".join(text.split())


def trim_quotes(text: str) -> str:
    return text.replace("'", "").replace('"', "")


def strip_ansi(text: str) -> str:
    """Remove common SGR escape sequences for width measurement."""
    import re

    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    return text


def human_size(num_bytes: int) -> str:
    """Format bytes like `df -h`: 1K-based, short suffix, no 'i'."""
    size = float(num_bytes)
    for suffix in ("K", "M", "G", "T", "P"):
        size /= 1024.0
        if abs(size) < 1024.0 or suffix == "P":
            if size >= 10:
                return f"{size:.0f}{suffix}"
            return f"{size:.1f}{suffix}"
    return f"{size:.0f}P"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)
