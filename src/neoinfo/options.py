"""Configuration defaults. Mirrors the neofetch default config block."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Options:
    # Title
    title_fqdn: str = "off"

    # Kernel / distro / uptime shorthand
    kernel_shorthand: str = "on"
    distro_shorthand: str = "off"
    os_arch: str = "on"
    uptime_shorthand: str = "on"

    # Memory
    memory_percent: str = "off"
    memory_unit: str = "mib"

    # Packages
    package_managers: str = "on"

    # Shell
    shell_path: str = "off"
    shell_version: str = "on"

    # CPU
    speed_type: str = "bios_limit"
    speed_shorthand: str = "off"
    cpu_brand: str = "on"
    cpu_cores: str = "logical"
    cpu_speed: str = "on"
    cpu_temp: str = "off"

    # GPU
    gpu_brand: str = "on"
    gpu_type: str = "all"

    # Resolution
    refresh_rate: str = "off"

    # GTK theme / icons / font
    gtk_shorthand: str = "off"
    gtk2: str = "on"
    gtk3: str = "on"

    # IP address
    public_ip_host: str = "http://ident.me"
    public_ip_timeout: int = 2
    local_ip_interface: tuple = ("auto",)

    # Desktop environment
    de_version: str = "on"

    # Disk
    disk_show: tuple = ("/",)
    disk_subtitle: str = "mount"
    disk_percent: str = "on"

    # Song
    music_player: str = "auto"
    song_format: str = "%artist% - %album% - %title%"
    song_shorthand: str = "off"
    mpc_args: tuple = ()

    # Text colors / formatting
    colors: tuple = ("distro",)
    bold: str = "on"
    underline_enabled: str = "on"
    underline_char: str = "-"
    separator: str = ":"

    # Color blocks
    block_range: tuple = (0, 15)
    color_blocks: str = "on"
    block_width: int = 3
    block_height: int = 1
    col_offset: str = "auto"

    # Progress bars
    bar_char_elapsed: str = "-"
    bar_char_total: str = "="
    bar_border: str = "on"
    bar_length: int = 15
    bar_color_elapsed: str = "distro"
    bar_color_total: str = "distro"
    memory_display: str = "off"
    battery_display: str = "off"
    disk_display: str = "off"

    # Backend / ascii
    image_backend: str = "ascii"
    image_source: str = "auto"
    ascii_distro: str = "auto"
    ascii_colors: tuple = ("distro",)
    ascii_bold: str = "on"
    image_loop: str = "off"
    image_size: str = "auto"
    catimg_size: str = "2"
    gap: int = 3
    yoffset: int = 0
    xoffset: int = 0
    background_color: str = ""
    crop_mode: str = "normal"
    crop_offset: str = "center"

    # Misc
    stdout: str = "off"
    json: str = "off"
    verbose: str = "off"

    # Info lines in display order: (label, function-name).
    # "title" and "underline" are display rows; "cols" is color blocks.
    info_order: list = field(
        default_factory=lambda: [
            ("title", "title"),
            ("underline", "underline"),
            ("OS", "distro"),
            ("Host", "model"),
            ("Kernel", "kernel"),
            ("Uptime", "uptime"),
            ("Packages", "packages"),
            ("Shell", "shell"),
            ("Resolution", "resolution"),
            ("DE", "de"),
            ("WM", "wm"),
            ("WM Theme", "wm_theme"),
            ("Theme", "theme"),
            ("Icons", "icons"),
            ("Terminal", "term"),
            ("Terminal Font", "term_font"),
            ("CPU", "cpu"),
            ("GPU", "gpu"),
            ("Memory", "memory"),
            ("cols", "cols"),
        ]
    )


# Function names that produce info lines (used by positional args + --disable).
INFO_FUNCS = (
    "title",
    "distro",
    "model",
    "kernel",
    "uptime",
    "packages",
    "shell",
    "resolution",
    "de",
    "wm",
    "wm_theme",
    "theme",
    "icons",
    "font",
    "term",
    "term_font",
    "cpu",
    "gpu",
    "memory",
    "song",
    "disk",
    "battery",
    "local_ip",
    "public_ip",
    "users",
    "locale",
    "gpu_driver",
)
