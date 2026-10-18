"""Command-line interface. Port of neofetch's usage()/get_args()/main()."""

from __future__ import annotations

import argparse
import os
import sys

from neoinfo import collectors, display
from neoinfo.collectors import Host, build_host, collect
from neoinfo.display import Palette
from neoinfo.options import INFO_FUNCS, Options

try:
    import tomllib
except ImportError:  # Python < 3.11 (not supported, but stay importable)
    tomllib = None  # type: ignore


def default_config_path() -> str:
    base = os.environ.get(
        "XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config")
    )
    return os.path.join(base, "neoinfo", "config.toml")


def load_toml_config(opts: Options, path: str, errors: list[str]) -> None:
    if tomllib is None:
        errors.append(f"Config: TOML support unavailable, skipping {path}.")
        return
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except OSError as exc:
        errors.append(f"Config: cannot read {path}: {exc}.")
        return
    for key, value in data.items():
        if key == "info_order":
            continue
        if hasattr(opts, key):
            current = getattr(opts, key)
            if isinstance(current, tuple) and isinstance(value, list):
                value = tuple(value)
            setattr(opts, key, value)
        else:
            errors.append(f"Config: unknown option {key!r}, skipping.")
    order = data.get("info_order")
    if order:
        parsed = []
        for item in order:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                parsed.append((str(item[0]), str(item[1])))
        if parsed:
            opts.info_order = parsed


def dump_default_config() -> str:
    opts = Options()
    lines = ["# neoinfo default configuration (TOML).", ""]
    for field_name in sorted(vars(opts)):
        if field_name == "info_order":
            continue
        value = getattr(opts, field_name)
        if isinstance(value, str):
            lines.append(f'{field_name} = "{value}"')
        elif isinstance(value, tuple):
            inner = ", ".join(
                f'"{v}"' if isinstance(v, str) else str(v) for v in value
            )
            lines.append(f"{field_name} = [{inner}]")
        else:
            lines.append(f"{field_name} = {value}")
    lines += [
        "",
        "# Display order: [label, function] pairs.",
        "# Available functions: " + ", ".join(INFO_FUNCS),
        "info_order = [",
    ]
    for label, func in opts.info_order:
        lines.append(f'    ["{label}", "{func}"],')
    lines.append("]")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="neoinfo",
        description=(
            "Neoinfo is a CLI system information tool. "
            "Python port of neofetch 7.1.0."
        ),
    )
    p.add_argument("funcs", nargs="*", help="info function(s) to print instead of the full report")
    p.add_argument("--disable", nargs="+", default=[], metavar="FUNC",
                   help="disable info line(s) by function name")
    # Info knobs
    p.add_argument("--title_fqdn", default=None)
    p.add_argument("--package_managers", default=None)
    p.add_argument("--os_arch", default=None)
    p.add_argument("--cpu_cores", default=None)
    p.add_argument("--cpu_speed", default=None)
    p.add_argument("--speed_type", default=None)
    p.add_argument("--speed_shorthand", default=None)
    p.add_argument("--distro_shorthand", default=None)
    p.add_argument("--kernel_shorthand", default=None)
    p.add_argument("--uptime_shorthand", default=None)
    p.add_argument("--cpu_brand", default=None)
    p.add_argument("--cpu_temp", default=None)
    p.add_argument("--gpu_brand", default=None)
    p.add_argument("--gpu_type", default=None)
    p.add_argument("--refresh_rate", default=None)
    p.add_argument("--de_version", default=None)
    p.add_argument("--gtk_shorthand", default=None)
    p.add_argument("--gtk2", default=None)
    p.add_argument("--gtk3", default=None)
    p.add_argument("--shell_path", default=None)
    p.add_argument("--shell_version", default=None)
    p.add_argument("--ip_host", default=None)
    p.add_argument("--ip_timeout", default=None, type=int)
    p.add_argument("--ip_interface", action="append", default=None)
    p.add_argument("--song_format", default=None)
    p.add_argument("--song_shorthand", default=None)
    p.add_argument("--music_player", default=None)
    p.add_argument("--memory_percent", default=None)
    p.add_argument("--memory_unit", default=None)
    p.add_argument("--disk_show", action="append", default=None)
    p.add_argument("--disk_subtitle", default=None)
    p.add_argument("--disk_percent", default=None)
    # Text formatting
    p.add_argument("--colors", nargs=6, default=None, metavar="N")
    p.add_argument("--underline", default=None)
    p.add_argument("--underline_char", default=None)
    p.add_argument("--bold", default=None)
    p.add_argument("--separator", default=None)
    # Color blocks
    p.add_argument("--color_blocks", default=None)
    p.add_argument("--col_offset", default=None)
    p.add_argument("--block_width", default=None, type=int)
    p.add_argument("--block_height", default=None, type=int)
    p.add_argument("--block_range", nargs=2, default=None, metavar=("FROM", "TO"))
    # Bars
    p.add_argument("--bar_char", nargs=2, default=None, metavar=("ELAPSED", "TOTAL"))
    p.add_argument("--bar_border", default=None)
    p.add_argument("--bar_length", default=None, type=int)
    p.add_argument("--bar_colors", nargs=2, default=None, metavar=("ELAPSED", "TOTAL"))
    p.add_argument("--memory_display", default=None)
    p.add_argument("--battery_display", default=None)
    p.add_argument("--disk_display", default=None)
    # Backend / ascii
    p.add_argument("--backend", default=None)
    p.add_argument("--source", default=None)
    p.add_argument("--ascii", nargs="?", const="auto", default=None, metavar="SOURCE")
    p.add_argument("--off", action="store_true", default=False)
    p.add_argument("--ascii_colors", nargs=6, default=None, metavar="N")
    p.add_argument("--ascii_distro", default=None)
    p.add_argument("--ascii_bold", default=None)
    p.add_argument("-L", "--logo", action="store_true", default=False,
                   help="only print the ascii logo")
    p.add_argument("--gap", default=None, type=int)
    # Other
    p.add_argument("--config", default=None, metavar="PATH")
    p.add_argument("--no_config", action="store_true", default=False)
    p.add_argument("--print_config", action="store_true", default=False)
    p.add_argument("--stdout", action="store_true", default=False)
    p.add_argument("--json", action="store_true", default=False)
    p.add_argument("--clean", action="store_true", default=False,
                   help="delete cached files and thumbnails")
    p.add_argument("-v", "--verbose", action="store_true", default=False)
    p.add_argument("--version", action="store_true", default=False)
    return p


def apply_args(opts: Options, args: argparse.Namespace, errors: list[str]) -> None:
    table = {
        "title_fqdn": "title_fqdn",
        "package_managers": "package_managers",
        "os_arch": "os_arch",
        "cpu_cores": "cpu_cores",
        "cpu_speed": "cpu_speed",
        "speed_type": "speed_type",
        "speed_shorthand": "speed_shorthand",
        "distro_shorthand": "distro_shorthand",
        "kernel_shorthand": "kernel_shorthand",
        "uptime_shorthand": "uptime_shorthand",
        "cpu_brand": "cpu_brand",
        "gpu_brand": "gpu_brand",
        "gpu_type": "gpu_type",
        "refresh_rate": "refresh_rate",
        "de_version": "de_version",
        "gtk_shorthand": "gtk_shorthand",
        "gtk2": "gtk2",
        "gtk3": "gtk3",
        "shell_path": "shell_path",
        "shell_version": "shell_version",
        "song_format": "song_format",
        "song_shorthand": "song_shorthand",
        "music_player": "music_player",
        "memory_percent": "memory_percent",
        "memory_unit": "memory_unit",
        "disk_subtitle": "disk_subtitle",
        "disk_percent": "disk_percent",
        "underline": "underline_enabled",
        "underline_char": "underline_char",
        "bold": "bold",
        "separator": "separator",
        "color_blocks": "color_blocks",
        "col_offset": "col_offset",
        "bar_border": "bar_border",
        "memory_display": "memory_display",
        "battery_display": "battery_display",
        "disk_display": "disk_display",
        "backend": "image_backend",
        "source": "image_source",
        "ascii_distro": "ascii_distro",
        "ascii_bold": "ascii_bold",
    }
    for flag, field in table.items():
        value = getattr(args, flag)
        if value is not None:
            setattr(opts, field, value)
    if args.cpu_temp is not None:
        opts.cpu_temp = "C" if args.cpu_temp == "on" else args.cpu_temp
    if args.ip_host is not None:
        opts.public_ip_host = args.ip_host
    if args.ip_timeout is not None:
        opts.public_ip_timeout = args.ip_timeout
    if args.ip_interface:
        opts.local_ip_interface = tuple(args.ip_interface)
    if args.disk_show:
        opts.disk_show = tuple(args.disk_show)
    if args.colors:
        opts.colors = tuple(args.colors)
    if args.ascii_colors:
        opts.ascii_colors = tuple(args.ascii_colors)
    if args.block_range:
        opts.block_range = (int(args.block_range[0]), int(args.block_range[1]))
    if args.block_width is not None:
        opts.block_width = args.block_width
    if args.block_height is not None:
        opts.block_height = args.block_height
    if args.bar_char:
        opts.bar_char_elapsed, opts.bar_char_total = args.bar_char
    if args.bar_length is not None:
        opts.bar_length = args.bar_length
    if args.bar_colors:
        opts.bar_color_elapsed, opts.bar_color_total = args.bar_colors
    if args.ascii is not None:
        opts.image_backend = "ascii"
        if args.ascii != "auto":
            opts.image_source = args.ascii
    if args.off:
        opts.image_backend = "off"
    if args.gap is not None:
        opts.gap = args.gap
    if args.stdout:
        opts.stdout = "on"
    if args.json:
        opts.json = "on"
    if args.verbose:
        opts.verbose = "on"
    for func in args.disable:
        opts.info_order = [
            (label, name)
            for label, name in opts.info_order
            if name != func.lower()
        ]


def clean_cache() -> None:
    import shutil

    for path in (
        os.path.join(
            os.environ.get(
                "XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache")
            ),
            "thumbnails",
            "neoinfo",
        ),
        "/tmp/neoinfo",
    ):
        shutil.rmtree(path, ignore_errors=True)


def gather(
    host: Host, opts: Options, names: list[tuple[str, str]], errors: list[str]
) -> tuple[list[tuple[str, str]], list[str]]:
    """Collect info lines as (label, value) pairs plus block lines."""
    pairs: list[tuple[str, str]] = []
    cache: dict = {}
    for label, name in names:
        if name in ("title", "underline", "cols"):
            continue
        try:
            value = collect(name, host, opts, cache)
        except Exception as exc:  # noqa: BLE001 - one bad probe must not kill output
            errors.append(f"Info: couldn't detect {label} ({exc}).")
            continue
        if isinstance(value, str):
            value = value.strip()
            if value:
                pairs.append((label, value))
            else:
                errors.append(f"Info: Couldn't detect {label}.")
        else:
            if not value:
                errors.append(f"Info: Couldn't detect {label}.")
            for suffix, item in value:
                item = (item or "").strip()
                if item:
                    pairs.append((f"{label}{suffix}", item))
    return pairs, errors


def main(argv: list[str] | None = None) -> int:
    from neoinfo import __version__

    parser = build_parser()
    args = parser.parse_args(argv)
    opts = Options()
    errors: list[str] = []

    if args.version:
        print(f"Neoinfo {__version__}")
        return 0
    if args.print_config:
        print(dump_default_config(), end="")
        return 0
    if args.clean:
        clean_cache()
        return 0

    # Config file (skipped with --config none/off or --no_config).
    config_arg = args.config
    if not args.no_config and config_arg not in ("none", "off"):
        load_toml_config(opts, config_arg or default_config_path(), errors)
    elif config_arg not in (None, "none", "off"):
        load_toml_config(opts, config_arg, errors)

    apply_args(opts, args, errors)

    host = build_host(opts)

    # Positional func names: print only those, like `neofetch uptime`.
    simple = [f.lower() for f in args.funcs if f.lower() in INFO_FUNCS]
    if simple and not args.logo:
        opts.stdout = "on"
        pairs, _ = gather(host, opts, [(f, f) for f in simple], [])
        for label, value in pairs:
            print(f"{label}{opts.separator} {value}")
        print()
        return 0
    if args.funcs and not simple and not args.logo:
        parser.error(f"unknown info function(s): {' '.join(args.funcs)}")

    if opts.ascii_distro == "auto":
        ascii_distro = host.distro
    else:
        ascii_distro = opts.ascii_distro
    logo_colors, art = display.find_logo(ascii_distro.strip(), host.kernel_name)
    if opts.ascii_colors[0] != "distro":
        logo_colors = tuple(opts.ascii_colors)

    if opts.stdout == "on":
        logo_colors, art = (), ""
        opts.color_blocks = "off"

    pal = Palette(opts, logo_colors)
    opts._palette = pal  # type: ignore[attr-defined]

    if opts.json == "on":
        pairs, _ = gather(host, opts, opts.info_order, [])
        print(display.to_json(pairs, __version__))
        return 0

    if args.logo:
        for line in display.render_logo_lines(art, pal):
            print(line)
        return 0

    backend = opts.image_backend
    logo_lines: list[str] = []
    if not art:
        logo_lines = []
    elif backend == "ascii":
        if opts.image_source not in ("auto", "ascii") and os.path.isfile(
            opts.image_source
        ):
            custom = (open(opts.image_source, encoding="utf-8", errors="replace").read())
            logo_lines = display.render_logo_lines(custom, pal)
        elif opts.image_source not in ("auto", "ascii"):
            errors.append(
                f"Image: '{opts.image_source}' doesn't exist, "
                "falling back to ascii mode."
            )
            logo_lines = display.render_logo_lines(art, pal)
        else:
            logo_lines = display.render_logo_lines(art, pal)
    elif backend == "off":
        logo_lines = []
    else:
        errors.append(
            f"Image: backend '{backend}' is not supported by neoinfo, "
            "falling back to ascii mode."
        )
        logo_lines = display.render_logo_lines(art, pal)

    info_lines: list[str] = []
    pairs, _ = gather(host, opts, opts.info_order, errors)
    cache_user_host = ""
    for label, value in pairs:
        info_lines.append(display.format_info_line(label, value, opts, pal))

    # Title + underline come first, like print_info().
    user_host = collect("title", host, opts, {})
    assert isinstance(user_host, str)
    user, _, hostname = user_host.partition("@")
    title_line = display.format_title(user, hostname, opts, pal)
    underline = display.format_underline(len(user) + len(hostname) + 1, opts, pal)
    head = [title_line] + ([underline] if underline is not None else [])

    block_lines = display.color_block_lines(
        opts, display.ascii_width(art) + opts.gap if art else 0
    )
    if ("cols", "cols") in opts.info_order or any(
        name == "cols" for _, name in opts.info_order
    ):
        tail = block_lines
    else:
        tail = []

    for line in display.layout(logo_lines, head + info_lines, opts.gap, opts.stdout == "on"):
        print(line)
    for line in tail:
        print(line)
    if opts.stdout == "on":
        # Matches neofetch's dynamic_prompt newline in backend-off mode.
        print()

    if opts.verbose == "on":
        for err in errors:
            print(f"[!] {err}", file=sys.stderr)
    return 0
