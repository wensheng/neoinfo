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
