"""Collector unit tests. Pure parsing logic with faked files/commands."""

import os

import pytest

from neoinfo import collectors, util
from neoinfo.collectors import Host
from neoinfo.options import Options


def make_host(**kwargs):
    base = {
        "kernel_name": "Linux",
        "kernel_version": "6.8.0-test",
        "kernel_machine": "x86_64",
        "os": "Linux",
        "distro": "Ubuntu 24.04 LTS x86_64",
        "machine_arch": "x86_64",
    }
    base.update(kwargs)
    return Host(**base)


# -- uptime ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("seconds", "shorthand", "expected"),
    [
        (8 * 86400 + 22 * 3600 + 4 * 60, "on", "8 days, 22 hours, 4 mins"),
        (8 * 86400 + 22 * 3600 + 4 * 60, "tiny", "8d 22h 4m"),
        (8 * 86400 + 22 * 3600 + 4 * 60, "off", "8 days, 22 hours, 4 minutes"),
        (3661, "on", "1 hour, 1 min"),
        (61, "tiny", "1m"),
        (0, "on", "0 secs"),
        (90, "on", "1 min"),
    ],
)
def test_format_uptime(seconds, shorthand, expected):
    assert collectors.format_uptime(seconds, shorthand) == expected


def test_get_uptime_proc(monkeypatch):
    monkeypatch.setattr(
        util, "read_text", lambda path: "12345.67 0.0" if path == "/proc/uptime" else None
    )
    assert collectors.get_uptime(make_host(), Options()) == "3 hours, 25 mins"


# -- distro ---------------------------------------------------------------

UBUNTU_OS_RELEASE = """\
PRETTY_NAME="Ubuntu 24.04.5 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.5 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
UBUNTU_CODENAME=noble
"""


def _fake_files(monkeypatch, mapping):
    def fake_read(path):
        return mapping.get(path)

    monkeypatch.setattr(util, "read_text", fake_read)
    monkeypatch.setattr(util, "which", lambda cmd: None)
    monkeypatch.setattr(os.path, "isdir", lambda path: False)


def test_get_distro_ubuntu(monkeypatch):
    # Only os-release exists: bash falls back to
    # "${PRETTY_NAME} ${UBUNTU_CODENAME}" + arch.
    _fake_files(monkeypatch, {"/etc/os-release": UBUNTU_OS_RELEASE})
    host = make_host()
    assert (
        collectors.get_distro(host, Options())
        == "Ubuntu 24.04.5 LTS noble x86_64"
    )


def test_get_distro_shorthand_on(monkeypatch):
    _fake_files(monkeypatch, {"/etc/os-release": UBUNTU_OS_RELEASE})
    opts = Options(distro_shorthand="on")
    assert collectors.get_distro(make_host(), opts) == "Ubuntu 24.04 x86_64"


def test_get_distro_shorthand_tiny_no_arch(monkeypatch):
    _fake_files(monkeypatch, {"/etc/os-release": UBUNTU_OS_RELEASE})
    opts = Options(distro_shorthand="tiny", os_arch="off")
    assert collectors.get_distro(make_host(), opts) == "Ubuntu"


# -- cpu ------------------------------------------------------------------

CPUINFO = """\
processor\t: 0
model name\t: AMD Ryzen 9 5900X 12-Core Processor
cpu MHz\t\t: 3700.000
processor\t: 1
model name\t: AMD Ryzen 9 5900X 12-Core Processor
cpu MHz\t\t: 3700.000
core id\t\t: 0
core id\t\t: 1
"""


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AMD Ryzen 9 5900X 12-Core Processor", "AMD Ryzen 9 5900X"),
        ("Intel(R) Core(TM) i7-6500U CPU @ 2.50GHz", "Intel i7-6500U @ 2.50GHz"),
        ("Intel Core2 Duo CPU E8400", "Intel Core 2 Duo E8400"),
        ("AMD EPYC 7713 64-Core Processor", "AMD EPYC 7713"),
    ],
)
def test_clean_cpu_name(raw, expected):
    assert collectors._clean_cpu_name(raw) == expected


def test_get_cpu_linux(monkeypatch):
    monkeypatch.setattr(util, "read_text", lambda path: CPUINFO if path == "/proc/cpuinfo" else None)
    monkeypatch.setattr(os.path, "isdir", lambda path: False)
    monkeypatch.setattr(collectors._glob, "glob", lambda pattern: [])
    assert (
        collectors.get_cpu(make_host(), Options())
        == "AMD Ryzen 9 5900X (2) @ 3.700GHz"
    )


def test_get_cpu_no_speed_no_cores(monkeypatch):
    monkeypatch.setattr(util, "read_text", lambda path: CPUINFO if path == "/proc/cpuinfo" else None)
    monkeypatch.setattr(os.path, "isdir", lambda path: False)
    monkeypatch.setattr(collectors._glob, "glob", lambda pattern: [])
    opts = Options(cpu_cores="off", cpu_speed="off")
    assert collectors.get_cpu(make_host(), opts) == "AMD Ryzen 9 5900X"


# -- memory ---------------------------------------------------------------

MEMINFO = """\
MemTotal:       131784392 kB
MemFree:         40000000 kB
MemAvailable:    90000000 kB
Buffers:          1000000 kB
Cached:          20000000 kB
Shmem:             500000 kB
SReclaimable:     1000000 kB
"""


def test_get_memory_mib(monkeypatch):
    monkeypatch.setattr(
        util, "read_text", lambda path: MEMINFO if path == "/proc/meminfo" else None
    )
    # (131784392 - 90000000) // 1024 = 40805 used, 128695 total
    assert collectors.get_memory(make_host(), Options()) == "40805MiB / 128695MiB"


def test_get_memory_percent_gib(monkeypatch):
    monkeypatch.setattr(
        util, "read_text", lambda path: MEMINFO if path == "/proc/meminfo" else None
    )
    opts = Options(memory_percent="on", memory_unit="gib")
    assert collectors.get_memory(make_host(), opts) == "39.85GiB / 125.68GiB (31%)"


# -- packages -------------------------------------------------------------

def _fake_pkg_env(monkeypatch, commands):
    monkeypatch.setattr(util, "which", lambda cmd: cmd if cmd in commands else None)
    monkeypatch.setattr(
        collectors, "_snapd_running", lambda: False,
    )

    def fake_run(argv, timeout=10):
        return commands.get(argv[0])

    monkeypatch.setattr(util, "run", fake_run)


def test_get_packages_on(monkeypatch):
    dpkg_out = "\n".join(f"pkg{i}" for i in range(5))
    # Keys are both the `which` probe name and the counting command name,
    # mirroring `has dpkg && tot dpkg-query ...`.
    _fake_pkg_env(
        monkeypatch,
        {"dpkg": "", "dpkg-query": dpkg_out, "flatpak": "a\nb\nc\n"},
    )
    assert collectors.get_packages(make_host(), Options()) == (
        "5 (dpkg), 3 (flatpak)"
    )


def test_get_packages_tiny_and_off(monkeypatch):
    _fake_pkg_env(monkeypatch, {"dpkg": "", "dpkg-query": "a\nb\n"})
    assert collectors.get_packages(make_host(), Options(package_managers="tiny")) == (
        "2 (dpkg)"
    )
    assert collectors.get_packages(make_host(), Options(package_managers="off")) == "2"


def test_get_packages_none(monkeypatch):
    _fake_pkg_env(monkeypatch, {})
    assert collectors.get_packages(make_host(), Options()) == ""


# -- gpu ------------------------------------------------------------------

LSPCI_MM = """\
04:00.0 "VGA compatible controller" "NVIDIA Corporation" "GA102 [GeForce RTX 3090]" -ra1 -p00 "MSI" "GA102 [GeForce RTX 3090]"
2b:00.0 "VGA compatible controller" "NVIDIA Corporation" "GA102 [GeForce RTX 3090]" -ra1 -p00 "NVIDIA Corporation" "GA102 [GeForce RTX 3090]"
00:02.0 "VGA compatible controller" "Intel Corporation" "UHD Graphics 630 (Desktop)" -p00 "Intel Corporation" "UHD Graphics 630"
"""


def test_get_gpu_all(monkeypatch):
    monkeypatch.setattr(util, "run", lambda argv, timeout=10: LSPCI_MM)
    result = collectors.get_gpu(make_host(), Options())
    assert result == [
        ("", "NVIDIA GeForce RTX 3090"),
        ("", "NVIDIA GeForce RTX 3090"),
        ("", "Intel UHD Graphics 630"),
    ]


def test_lspci_raw_keeps_slot_for_dedupe():
    # awk dedupes on the pre-sub value (slot included), so identical GPUs
    # in different slots are both kept; the slot is stripped for display.
    short = (
        '04:00.0 "VGA compatible controller" "NVIDIA Corporation" '
        '"GA102 [GeForce RTX 3090]" -ra1'
    )
    assert collectors._lspci_gpu_raw(short) == (
        "04:00.0  NVIDIA Corporation GA102 [GeForce RTX 3090]"
    )


def test_get_gpu_dedicated(monkeypatch):
    monkeypatch.setattr(util, "run", lambda argv, timeout=10: LSPCI_MM)
    result = collectors.get_gpu(make_host(), Options(gpu_type="dedicated"))
    assert all("Intel" not in name for _, name in result)
    assert len(result) == 2


def test_get_gpu_no_brand(monkeypatch):
    monkeypatch.setattr(util, "run", lambda argv, timeout=10: LSPCI_MM)
    result = collectors.get_gpu(make_host(), Options(gpu_brand="off"))
    assert result[0] == ("", "GeForce RTX 3090")


# -- misc -----------------------------------------------------------------

def test_get_kernel_shorthand():
    assert collectors.get_kernel(make_host(), Options()) == "6.8.0-test"
    assert (
        collectors.get_kernel(make_host(), Options(kernel_shorthand="off"))
        == "Linux 6.8.0-test"
    )


def test_trim_collapses_whitespace():
    assert util.trim("  Ubuntu   24.04  LTS  ") == "Ubuntu 24.04 LTS"


def test_get_users_unique(monkeypatch):
    monkeypatch.setattr(
        util, "run", lambda argv, timeout=10: "amy pts/0\namy pts/1\nbob pts/2\n"
    )
    assert collectors.get_users(make_host(), Options()) == "amy, bob"


# -- terminal -------------------------------------------------------------

def _fake_term_env(monkeypatch, env, tree, realpaths=None):
    """Fake environment and process tree. `tree` lists (name) from neoinfo's
    parent upward; anything above it is pid 1, named "launchd"/"systemd"."""
    monkeypatch.setattr(util, "env", lambda name, default="": env.get(name, default))
    pids = list(range(101, 101 + len(tree)))
    chain = [os.getpid(), *pids, 1]
    parents = dict(zip(chain, chain[1:]))
    names = dict(zip(pids, tree))
    monkeypatch.setattr(collectors, "_ppid", lambda pid: parents.get(pid))
    monkeypatch.setattr(collectors, "_process_name", lambda pid: names.get(pid, "systemd"))
    realpaths = realpaths or {}
    monkeypatch.setattr(os.path, "realpath", lambda path: realpaths.get(path, path))
    monkeypatch.setattr(util, "run", lambda argv, timeout=10: "/dev/tty1\n" if argv == ["tty"] else None)


def test_get_term_macos_kitty_via_login(monkeypatch):
    # kitty on macOS starts the shell through /usr/bin/login.
    _fake_term_env(
        monkeypatch,
        {"SHELL": "/bin/zsh", "TERM": "xterm-256color"},
        ["-zsh", "/usr/bin/login", "/Applications/kitty.app/Contents/MacOS/kitty"],
    )
    assert collectors.get_term(make_host(os="macOS"), Options()) == "kitty"


def test_get_term_linux_resolves_exe(monkeypatch):
    _fake_term_env(
        monkeypatch,
        {"SHELL": "/usr/bin/bash"},
        ["bash", "uv", "xterm"],
        realpaths={"/proc/103/exe": "/usr/bin/xterm"},
    )
    assert collectors.get_term(make_host(), Options()) == "xterm"


def test_get_term_ssh_uses_term_variable(monkeypatch):
    _fake_term_env(
        monkeypatch,
        {"SHELL": "/bin/bash", "TERM": "xterm-kitty",
         "SSH_CONNECTION": "10.0.0.2 50000 10.0.0.1 22", "SSH_TTY": "/dev/pts/4"},
        ["-bash", "sshd-session"],
    )
    assert collectors.get_term(make_host(), Options()) == "kitty"


def test_get_term_ssh_uses_lc_terminal(monkeypatch):
    _fake_term_env(
        monkeypatch,
        {"SHELL": "/bin/bash", "TERM": "xterm-256color", "LC_TERMINAL": "iTerm2",
         "SSH_CONNECTION": "10.0.0.2 50000 10.0.0.1 22", "SSH_TTY": "/dev/pts/4"},
        ["-bash", "sshd-session"],
    )
    assert collectors.get_term(make_host(), Options()) == "iTerm2"


def test_get_term_ssh_unknown_client_falls_back_to_tty(monkeypatch):
    _fake_term_env(
        monkeypatch,
        {"SHELL": "/bin/bash", "TERM": "xterm-256color",
         "SSH_CONNECTION": "10.0.0.2 50000 10.0.0.1 22", "SSH_TTY": "/dev/pts/4"},
        ["-bash", "sshd"],
    )
    assert collectors.get_term(make_host(), Options()) == "/dev/pts/4"


def test_get_term_inside_tmux_uses_env(monkeypatch):
    _fake_term_env(
        monkeypatch,
        {"SHELL": "/bin/zsh", "TERM": "tmux-256color", "ALACRITTY_WINDOW_ID": "1"},
        ["zsh", "tmux: server"],
    )
    assert collectors.get_term(make_host(), Options()) == "alacritty"


def test_get_term_console_login_shows_tty(monkeypatch):
    _fake_term_env(monkeypatch, {"SHELL": "/bin/bash", "TERM": "linux"}, ["-bash", "login"])
    assert collectors.get_term(make_host(), Options()) == "/dev/tty1"


def test_get_term_program_wins(monkeypatch):
    _fake_term_env(
        monkeypatch,
        {"TERM_PROGRAM": "iTerm.app", "KITTY_WINDOW_ID": "1"},
        ["zsh", "login", "kitty"],
    )
    assert collectors.get_term(make_host(os="macOS"), Options()) == "iTerm2"


# -- macOS cpu / gpu / memory ---------------------------------------------

VM_STAT = """\
Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                    43527.
Pages wired down:                             265168.
Pages purgeable:                                8419.
Pages occupied by compressor:                 268795.
"""

SP_DISPLAYS_INTEL = """\
Graphics/Displays:

    Radeon Pro 560X:

      Chipset Model: AMD Radeon Pro 560X
      Type: GPU

    Intel UHD Graphics 630:

      Chipset Model: Intel UHD Graphics 630
      Type: GPU
"""


@pytest.fixture(autouse=True)
def _clear_system_profiler_cache():
    collectors._system_profiler.cache_clear()
    yield
    collectors._system_profiler.cache_clear()


def _fake_macos(monkeypatch, sysctl, commands=None, which=()):
    """`commands` is keyed by the full argv as a tuple, or by argv[0]."""
    commands = commands or {}

    def fake_run(argv, timeout=10):
        if argv[:2] == ["sysctl", "-n"]:
            value = sysctl.get(argv[2])
            return None if value is None else f"{value}\n"
        return commands.get(tuple(argv), commands.get(argv[0]))

    monkeypatch.setattr(util, "run", fake_run)
    monkeypatch.setattr(util, "which", lambda cmd: cmd if cmd in which else None)


def test_get_cpu_macos_apple_silicon(monkeypatch):
    _fake_macos(monkeypatch, {"machdep.cpu.brand_string": "Apple M4", "hw.logicalcpu_max": "10"})
    assert collectors.get_cpu(make_host(os="macOS"), Options()) == "Apple M4 (10)"


def test_get_cpu_macos_intel(monkeypatch):
    _fake_macos(monkeypatch, {
        "machdep.cpu.brand_string": "Intel(R) Core(TM) i7-8700B CPU @ 3.20GHz",
        "hw.logicalcpu_max": "12",
        "hw.physicalcpu_max": "6",
    })
    host = make_host(os="macOS")
    assert collectors.get_cpu(host, Options()) == "Intel i7-8700B (12) @ 3.20GHz"
    opts = Options()
    opts.cpu_cores = "physical"
    opts.cpu_speed = "off"
    opts.cpu_brand = "off"
    assert collectors.get_cpu(host, opts) == "i7-8700B (6)"


def test_get_gpu_macos_lists_all(monkeypatch):
    _fake_macos(monkeypatch, {}, {"system_profiler": SP_DISPLAYS_INTEL})
    assert collectors.get_gpu(make_host(os="macOS"), Options()) == [
        ("", "AMD Radeon Pro 560X, Intel UHD Graphics 630")
    ]


def test_get_gpu_macos_none(monkeypatch):
    _fake_macos(monkeypatch, {}, {})
    assert collectors.get_gpu(make_host(os="macOS"), Options()) == []


def test_get_memory_macos(monkeypatch):
    _fake_macos(
        monkeypatch,
        {
            "hw.pagesize": "16384",
            "hw.memsize": "34359738368",
            "vm.page_pageable_internal_count": "931003",
            "vm.page_purgeable_count": "8419",
        },
        {"vm_stat": VM_STAT},
    )
    opts = Options()
    opts.memory_percent = "on"
    # (931003 - 8419 + 265168 + 268795) pages * 16 KiB = 22758 MiB
    assert collectors.get_memory(make_host(os="macOS"), opts) == "22758MiB / 32768MiB (69%)"


# -- macOS os / host / uptime / packages / resolution ----------------------

SP_HARDWARE_AND_DISPLAYS = """\
Hardware:

    Hardware Overview:

      Model Name: Mac mini
      Model Identifier: Mac16,10

Graphics/Displays:

    Apple M4:

      Chipset Model: Apple M4
      Displays:
        HISENSE:
          Resolution: 6016 x 3384
          UI Looks like: 3008 x 1692 @ 30.00Hz
        DELL U2720Q:
          Resolution: 3840 x 2160 (2160p/4K UHD 1 - Ultra High Definition)
          UI Looks like: 1920 x 1080 @ 59.94Hz
"""

SP_DISPLAYS_OLD = """\
Graphics/Displays:

    Intel Iris:

      Chipset Model: Intel Iris
      Displays:
        Color LCD:
          Resolution: 2560 x 1600 @ 60Hz
"""


def _sw_vers(version, build):
    return {
        ("sw_vers", "-productVersion"): f"{version}\n",
        ("sw_vers", "-buildVersion"): f"{build}\n",
    }


@pytest.mark.parametrize(
    ("version", "build", "shorthand", "expected"),
    [
        ("15.6", "24G84", "off", "macOS Sequoia 15.6 24G84 arm64"),
        ("15.6", "24G84", "on", "macOS Sequoia 15.6 arm64"),
        ("15.6", "24G84", "tiny", "macOS 15.6 arm64"),
        ("26.0", "25A354", "off", "macOS Tahoe 26.0 25A354 arm64"),
        ("10.10.5", "14F27", "off", "OS X Yosemite 10.10.5 14F27 arm64"),
        # 10.1.5 must not be mistaken for 10.10 or 10.11.
        ("10.1.5", "5S60", "off", "macOS 10.1.5 5S60 arm64"),
        # A release the table doesn't know yet.
        ("27.0.1", "26A434", "off", "macOS 27.0.1 26A434 arm64"),
    ],
)
def test_get_distro_macos(monkeypatch, version, build, shorthand, expected):
    _fake_macos(monkeypatch, {}, _sw_vers(version, build))
    host = make_host(os="macOS", kernel_name="Darwin", machine_arch="arm64")
    assert collectors.get_distro(host, Options(distro_shorthand=shorthand)) == expected


def test_get_model_macos(monkeypatch):
    _fake_macos(monkeypatch, {"hw.model": "Mac16,10"}, {"system_profiler": SP_HARDWARE_AND_DISPLAYS})
    assert collectors.get_model(make_host(os="macOS"), Options()) == "Mac mini (Mac16,10)"


def test_get_model_macos_identifier_only(monkeypatch):
    _fake_macos(monkeypatch, {"hw.model": "MacBookPro18,3"})
    assert collectors.get_model(make_host(os="macOS"), Options()) == "MacBookPro18,3"


def test_get_uptime_macos(monkeypatch):
    import time

    boot = int(time.time()) - (2 * 86400 + 3 * 3600 + 4 * 60 + 30)
    _fake_macos(monkeypatch, {"kern.boottime": f"{{ sec = {boot}, usec = 385528 }} Thu Oct  1 15:20:54 2026"})
    assert collectors.get_uptime(make_host(os="macOS"), Options()) == "2 days, 3 hours, 4 mins"


def test_get_packages_macos(monkeypatch, tmp_path):
    cellar, caskroom = tmp_path / "Cellar", tmp_path / "Caskroom"
    for path in (cellar / "git", cellar / "wget", cellar / "uv", caskroom / "kitty"):
        path.mkdir(parents=True)
    _fake_macos(
        monkeypatch,
        {},
        {
            ("brew", "--cellar"): f"{cellar}\n",
            ("brew", "--caskroom"): f"{caskroom}\n",
            "port": "The following ports are currently installed:\n  zlib @1.3\n  xz @5.4\n",
        },
        which=("brew", "port"),
    )
    host = make_host(os="macOS")
    assert collectors.get_packages(host, Options()) == "2 (port), 4 (brew)"
    assert collectors.get_packages(host, Options(package_managers="off")) == "6"


def test_get_packages_linux_brew_is_one_entry(monkeypatch, tmp_path):
    cellar, caskroom = tmp_path / "Cellar", tmp_path / "Caskroom"
    for path in (cellar / "git", caskroom / "kitty"):
        path.mkdir(parents=True)
    _fake_pkg_env(
        monkeypatch,
        {"brew": None},
    )
    monkeypatch.setattr(
        util, "run",
        lambda argv, timeout=10: {"--cellar": f"{cellar}\n", "--caskroom": f"{caskroom}\n"}.get(argv[-1]),
    )
    assert collectors.get_packages(make_host(), Options()) == "2 (brew)"


def test_get_resolution_macos(monkeypatch):
    _fake_macos(monkeypatch, {}, {"system_profiler": SP_HARDWARE_AND_DISPLAYS})
    host = make_host(os="macOS")
    assert collectors.get_resolution(host, Options()) == "6016x3384, 3840x2160"
    assert collectors.get_resolution(host, Options(refresh_rate="on")) == (
        "6016x3384 @ 30Hz, 3840x2160 @ 59.94Hz"
    )


def test_get_resolution_macos_old_format(monkeypatch):
    _fake_macos(monkeypatch, {}, {"system_profiler": SP_DISPLAYS_OLD})
    host = make_host(os="macOS")
    assert collectors.get_resolution(host, Options()) == "2560x1600"
    assert collectors.get_resolution(host, Options(refresh_rate="on")) == "2560x1600 @ 60Hz"


# -- terminal font: kitty, Ghostty, Alacritty, Vivido ---------------------

@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ('family="JetBrainsMono Nerd Font Mono"', "JetBrainsMono Nerd Font Mono"),
        ('family="Fira Code" style="Retina" features="+zero"', "Fira Code"),
        ("family='Iosevka Term'", "Iosevka Term"),
        ("family=Menlo", "Menlo"),
        ("postscript_name=FiraCode-Retina", "FiraCode-Retina"),
        ("Operator Mono Book", "Operator Mono Book"),
        ("monospace\n", "monospace"),
    ],
)
def test_kitty_font_family(spec, expected):
    assert collectors._kitty_font_family(spec) == expected


@pytest.fixture
def font_home(monkeypatch, tmp_path):
    """Empty home and XDG config dir, no SSH, no terminal CLI installed."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    for var in ("SSH_CONNECTION", "KITTY_CONFIG_DIRECTORY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(collectors, "_term_binary", lambda source: "")
    return tmp_path


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.mark.parametrize(
    ("term", "query_output", "expected"),
    [
        ("kitty", 'family="JetBrainsMono Nerd Font Mono"\n', "JetBrainsMono Nerd Font Mono"),
        ("ghostty", "font-family = Hack Nerd Font Mono\nfont-family = Symbols Nerd Font\nfont-size = 15\n",
         "Hack Nerd Font Mono"),
        ("alacritty", '{"font":{"normal":{"family":"Menlo","style":null},"size":11.25}}', "Menlo"),
        ("vivido", '{"font":{"normal":{"family":"JetBrainsMono Nerd Font Mono","style":null}}}',
         "JetBrainsMono Nerd Font Mono"),
    ],
)
def test_get_term_font_asks_terminal(monkeypatch, font_home, term, query_output, expected):
    monkeypatch.setattr(collectors, "_term_binary", lambda source: f"/bin/{source.programs[0][0]}")
    calls = []

    def fake_run(argv, timeout=10):
        calls.append(argv)
        return query_output

    monkeypatch.setattr(util, "run", fake_run)
    assert collectors.get_term_font(make_host(os="macOS"), Options(), term) == expected
    assert calls == [[f"/bin/{term}", *collectors._TERM_FONTS[term].query]]


def test_get_term_font_kitty_config(font_home):
    _write(font_home / ".config/kitty/kitty.conf",
           "# font_family Commented Out\n"
           "font_family Menlo\n"
           'font_family      family="JetBrainsMono Nerd Font Mono"\n'
           "bold_font        auto\n")
    assert collectors.get_term_font(make_host(), Options(), "kitty") == "JetBrainsMono Nerd Font Mono"


def test_get_term_font_ghostty_config_later_file_wins(font_home):
    _write(font_home / ".config/ghostty/config", 'font-family = "Iosevka"\n')
    _write(font_home / "Library/Application Support/com.mitchellh.ghostty/config",
           "# font-family = Commented Out\n"
           "font-family =\n"  # clears Iosevka
           'font-family = "Hack Nerd Font Mono"\n'
           "font-family = Symbols Nerd Font\n")
    assert collectors.get_term_font(make_host(os="macOS"), Options(), "ghostty") == "Hack Nerd Font Mono"


def test_get_term_font_alacritty_toml_with_import(font_home):
    _write(font_home / ".config/alacritty/fonts.toml", '[font.normal]\nfamily = "Fira Code"\n')
    _write(font_home / ".config/alacritty/alacritty.toml",
           '[general]\nimport = ["fonts.toml"]\n\n[font]\nsize = 13.0\n')
    assert collectors.get_term_font(make_host(), Options(), "alacritty") == "Fira Code"
    # The main file overrides what it imports.
    _write(font_home / ".config/alacritty/alacritty.toml",
           'import = ["~/.config/alacritty/fonts.toml"]\n\n[font]\nnormal = { family = "Menlo" }\n')
    assert collectors.get_term_font(make_host(), Options(), "alacritty") == "Menlo"


def test_get_term_font_alacritty_legacy_yaml(font_home):
    _write(font_home / ".config/alacritty/alacritty.yml",
           "font:\n  normal:\n    family: \"Source Code Pro\" # comment\n    style: Regular\n")
    assert collectors.get_term_font(make_host(), Options(), "alacritty") == "Source Code Pro"


def test_get_term_font_vivido_config(font_home):
    _write(font_home / ".config/vivido/vivido.toml",
           '[font]\nsize = 13.0\n\n[font.normal]\nfamily = "JetBrainsMono Nerd Font Mono"\n')
    assert collectors.get_term_font(make_host(os="macOS"), Options(), "vivido") == "JetBrainsMono Nerd Font Mono"


@pytest.mark.parametrize(
    ("term", "os_name", "expected"),
    [
        ("alacritty", "macOS", "Menlo"),
        ("alacritty", "Linux", "monospace"),
        ("vivido", "macOS", "Menlo"),
        ("ghostty", "macOS", "JetBrains Mono"),
        ("kitty", "Linux", "monospace"),
    ],
)
def test_get_term_font_builtin_default(font_home, term, os_name, expected):
    assert collectors.get_term_font(make_host(os=os_name), Options(), term) == expected


def test_get_term_font_skipped_over_ssh(monkeypatch, font_home):
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.2 50000 10.0.0.1 22")
    assert collectors.get_term_font(make_host(), Options(), "kitty") == ""


def test_get_term_vivido(monkeypatch):
    _fake_term_env(
        monkeypatch,
        {"SHELL": "/bin/zsh"},
        ["-zsh", "/usr/bin/login", "/Applications/Vivido.app/Contents/MacOS/vivido"],
    )
    assert collectors.get_term(make_host(os="macOS"), Options()) == "vivido"
    _fake_term_env(monkeypatch, {"SHELL": "/bin/zsh", "VIVIDO_WINDOW_ID": "3"}, ["zsh", "tmux: server"])
    assert collectors.get_term(make_host(os="macOS"), Options()) == "vivido"


@pytest.mark.parametrize(
    ("env", "tree"),
    [
        ({"SHELL": "/bin/zsh"}, ["-zsh", "/usr/bin/login", "/Applications/Vivida.app/Contents/MacOS/vivida"]),
        ({"SHELL": "/bin/zsh"}, ["-zsh", "/usr/bin/login", "./target/release/vivida"]),
        ({"SHELL": "/bin/zsh", "TERM_PROGRAM": "Vivida"}, ["zsh"]),
    ],
)
def test_get_term_vivida_is_vivido(monkeypatch, env, tree):
    _fake_term_env(monkeypatch, env, tree)
    assert collectors.get_term(make_host(os="macOS"), Options()) == "vivido"


def test_term_binary_falls_back_to_vivida(monkeypatch):
    # Only Vivida is installed: ask `vivida msg get-config`.
    monkeypatch.setattr(util, "which", lambda cmd: "/opt/bin/vivida" if cmd == "vivida" else None)
    monkeypatch.setattr(os.path, "isfile", lambda path: False)
    assert collectors._term_binary(collectors._TERM_FONTS["vivido"]) == "/opt/bin/vivida"
