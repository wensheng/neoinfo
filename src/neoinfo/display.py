"""Text formatting and layout. Port of neofetch's COLORS / prin / info code."""

from __future__ import annotations

import json
import re

from neoinfo import logos, util
from neoinfo.options import Options

RESET = "\033[0m"


def color(code: str) -> str:
    """Map a color number to an ANSI sequence. Mirrors neofetch's color()."""
    if code in ("0", "1", "2", "3", "4", "5", "6"):
        return f"{RESET}\033[3{code}m"
    if code in ("7", "fg"):
        return f"{RESET}\033[37m"
    return f"\033[38;5;{code}m"


class Palette:
    """All text colors resolved for one run."""

    def __init__(self, opts: Options, logo_colors: tuple) -> None:
        self.plain = opts.stdout == "on"
        bold_seq = "" if (opts.bold == "off" or self.plain) else "\033[1m"
        self.bold = bold_seq
        ascii_bold = "" if (opts.ascii_bold == "off" or self.plain) else "\033[1m"
        self.ascii_bold = ascii_bold
        self.logo = [color(c) + ascii_bold for c in logo_colors]

        if self.plain:
            self.title = self.at = self.underline = ""
            self.subtitle = self.colon = self.info = ""
            self.bar_elapsed = self.bar_total = ""
            return

        if opts.colors[0] == "distro":
            c1 = logo_colors[0] if len(logo_colors) > 0 else "1"
            c2 = logo_colors[1] if len(logo_colors) > 1 else "7"
            self.title = color(c1)
            self.at = RESET
            self.underline = RESET
            self.subtitle = color(c2)
            self.colon = RESET
            self.info = RESET
            try:
                if int(c1) == 8:
                    self.title = RESET
            except ValueError:
                pass
            try:
                if int(c2) == 8:
                    self.subtitle = RESET
            except ValueError:
                pass
            try:
                if int(c2) == 7:
                    self.subtitle = color(c1)
            except ValueError:
                pass
            try:
                if int(c1) == 7:
                    self.title = RESET
            except ValueError:
                pass
        else:
            cols = list(opts.colors) + ["7"] * 6
            self.title = color(cols[0])
            self.at = color(cols[1])
            self.underline = color(cols[2])
            self.subtitle = color(cols[3])
            self.colon = color(cols[4])
            self.info = color(cols[5])

        if opts.bar_color_elapsed == "distro":
            self.bar_elapsed = color("fg")
        else:
            self.bar_elapsed = color(opts.bar_color_elapsed)
        total = opts.bar_color_total
        first = logo_colors[0] if logo_colors else "1"
        second = logo_colors[1] if len(logo_colors) > 1 else "7"
        if total == "distro" and first in "736":
            self.bar_total = color(first)
        elif total == "distro":
            self.bar_total = color(second)
        else:
            self.bar_total = color(total)


def render_bar(elapsed: int, total: int, opts: Options) -> str:
    """Draw a progress bar. Mirrors neofetch's bar()."""
    filled = elapsed * opts.bar_length // total if total else 0
    prog = opts.bar_char_elapsed * filled
    rest = opts.bar_char_total * (opts.bar_length - filled)
    pal = getattr(opts, "_palette", None)
    use_color = pal is not None and not pal.plain
    if use_color:
        bar = f"{pal.bar_elapsed}{prog}{pal.bar_total}{rest}"
    else:
        bar = f"{prog}{rest}"
    if opts.bar_border == "on":
        if use_color:
            bar = f"{color('fg')}[{bar}{color('fg')}]"
        else:
            bar = f"[{bar}]"
    if use_color:
        bar += pal.info
    return bar


def find_logo(
    distro: str, kernel_name: str
) -> tuple[tuple, str]:
    """Return (colors, art) for a distro, falling back to kernel art."""
    for pattern, colors, art in logos.LOGOS:
        if re.fullmatch(pattern, distro, re.IGNORECASE):
            return colors, art
    for pattern, colors, art in logos.KERNEL_FALLBACK:
        if re.fullmatch(pattern, kernel_name, re.IGNORECASE):
            return colors, art
    # Last resort: generic Tux logo.
    for pattern, colors, art in logos.KERNEL_FALLBACK:
        if pattern == "(?:Linux)":
            return colors, art
    return (("2", "7"), "")


def ascii_width(art: str) -> int:
    """Visible width of ascii art. Mirrors print_ascii's length calc."""
    width = 0
    for line in art.split("\n"):
        line = line.replace("\\\\", "\\").replace("\u2588", " ")
        line = re.sub(r"\{c[1-6]\}", "", line)
        width = max(width, len(line))
    return width


def render_logo_lines(art: str, pal: Palette) -> list[str]:
    out = []
    for i in range(1, 7):
        art = art.replace(f"{{c{i}}}", pal.logo[i - 1] if i - 1 < len(pal.logo) else "")
    for line in art.split("\n"):
        out.append(f"{line}{RESET}")
    return out


def format_info_line(
    label: str, value: str, opts: Options, pal: Palette
) -> str:
    """Format one `Subtitle: value` line. Mirrors prin()."""
    separator = opts.separator
    if label:
        text = f"{label}{separator} {value}"
    else:
        text = value
    text = util.trim(text.replace(RESET, ""))
    if opts.stdout == "on":
        return text
    if label:
        colored = f"{pal.subtitle}{pal.bold}{label}{RESET}{pal.colon}{separator}{pal.info} {value}"
    else:
        colored = f"{pal.info}{value}"
    return f"{colored}{RESET} "


def format_title(user: str, hostname: str, opts: Options, pal: Palette) -> str:
    if opts.stdout == "on":
        return f"{user}@{hostname}"
    return (
        f"{pal.title}{pal.bold}{user}{pal.at}@{pal.title}{pal.bold}{hostname}{RESET} "
    )


def format_underline(length: int, opts: Options, pal: Palette) -> str | None:
    if opts.underline_enabled != "on":
        return None
    bar = opts.underline_char * length
    if opts.stdout == "on":
        return bar
    return f"{pal.underline}{bar}{RESET} "


def color_block_lines(opts: Options, pad: int) -> list[str]:
    """Render the color blocks. Mirrors get_cols()."""
    if opts.color_blocks != "on":
        return []
    try:
        start, end = int(opts.block_range[0]), int(opts.block_range[1])
    except (ValueError, IndexError):
        return []
    width = " " * int(opts.block_width)
    blocks = blocks2 = ""
    for num in range(start, end + 1):
        if 0 <= num <= 7:
            blocks += f"{RESET}\033[3{num}m\033[4{num}m{width}"
        else:
            blocks2 += f"\033[38;5;{num}m\033[48;5;{num}m{width}"
    rows: list[str] = []
    height = max(1, int(opts.block_height))
    for _ in range(height):
        row = ""
        if blocks:
            row += f"{blocks}{RESET}"
        if blocks2:
            row += f"{blocks2}{RESET}"
        rows.append(row)
    try:
        offset = pad if opts.col_offset == "auto" else int(opts.col_offset)
    except ValueError:
        offset = pad
    prefix = "" if opts.stdout == "on" else f"\033[{offset}C"
    return [f"{prefix}{row}" for row in rows]


def layout(
    logo_lines: list[str], info_lines: list[str], gap: int, plain: bool
) -> list[str]:
    """Zip logo and info side-by-side. Same visuals as neofetch's layout."""
    if not logo_lines:
        return list(info_lines)
    width = max((len(util.strip_ansi(line)) for line in logo_lines), default=0)
    out = []
    for i in range(max(len(logo_lines), len(info_lines))):
        left = logo_lines[i] if i < len(logo_lines) else ""
        visible = len(util.strip_ansi(left))
        right = info_lines[i] if i < len(info_lines) else ""
        padding = " " * (width - visible + gap)
        if plain:
            out.append(f"{util.strip_ansi(left)}{padding}{right}".rstrip())
        else:
            out.append(f"{left}{padding}{right}".rstrip())
    return out


def to_json(pairs: list[tuple[str, str]], version: str) -> str:
    lines = ["{"]
    for key, value in pairs:
        lines.append(f"    {json.dumps(key)}: {json.dumps(value)},")
    lines.append(f"    {json.dumps('Version')}: {json.dumps(version)}")
    lines.append("}")
    return "\n".join(lines)
