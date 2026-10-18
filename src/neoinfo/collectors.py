"""Info collectors. Python port of neofetch's get_* functions.

Each collector takes (host, opts) and returns a string ("" when undetected)
or, for multi-line printers (gpu/disk/battery/local_ip/song-shorthand), a
list of (suffix, value) tuples where the display layer prepends the label.
"""

from __future__ import annotations

import functools
import glob as _glob
import json
import os
import re
import shutil
import socket
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field

from neoinfo import util
from neoinfo.options import Options


@dataclass
class Host:
    kernel_name: str = ""
    kernel_version: str = ""
    kernel_machine: str = ""
    os: str = ""
    distro: str = ""
    machine_arch: str = ""


def detect_os(kernel_name: str, darwin_name: str = "") -> str:
    """Map `uname -s` output to neofetch's $os value."""
    if kernel_name == "Darwin":
        return darwin_name or "macOS"
    if kernel_name == "SunOS":
        return "Solaris"
    if kernel_name == "Haiku":
        return "Haiku"
    if kernel_name == "MINIX":
        return "MINIX"
    if kernel_name == "AIX":
        return "AIX"
    if kernel_name.startswith("IRIX"):
        return "IRIX"
    if kernel_name == "FreeMiNT":
        return "FreeMiNT"
    if kernel_name in ("Linux",) or kernel_name.startswith("GNU"):
        return "Linux"
    if (
        kernel_name.endswith("BSD")
        or kernel_name in ("DragonFly", "Bitrig")
    ):
        return "BSD"
    if kernel_name.startswith(("CYGWIN", "MSYS", "MINGW")):
        return "Windows"
    return ""


def build_host(opts: Options) -> Host:
    uname = os.uname()
    host = Host(
        kernel_name=uname.sysname,
        kernel_version=uname.release,
        kernel_machine=uname.machine,
    )
    host.os = detect_os(host.kernel_name)
    host.distro = get_distro(host, opts)
    if host.os in ("Solaris", "AIX", "Haiku", "IRIX", "FreeMiNT"):
        out = util.run(["uname", "-p"])
        host.machine_arch = util.trim(out) if out else ""
    else:
        host.machine_arch = host.kernel_machine
    return host


# ---------------------------------------------------------------------------
# macOS helpers
# ---------------------------------------------------------------------------

def _sysctl(name: str) -> str:
    out = util.run(["sysctl", "-n", name])
    return out.strip() if out else ""


def _sysctl_int(name: str) -> int:
    value = _sysctl(name)
    return int(value) if value.isdigit() else 0


@functools.cache
def _system_profiler() -> str:
    """Hardware + display report, shared by Host, GPU and Resolution.

    One call for both data types: system_profiler takes ~0.25s per run.
    """
    out = util.run(["system_profiler", "SPHardwareDataType", "SPDisplaysDataType"], timeout=15)
    return out or ""


# ---------------------------------------------------------------------------
# distro
# ---------------------------------------------------------------------------

def _parse_os_release(text: str) -> dict[str, str]:
    info: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        info[key.strip()] = util.trim_quotes(value.strip())
    return info


# (version, family, release name). Matches "<version>" or "<version>.*".
_MACOS_RELEASES = (
    ("10.4", "Mac OS X", "Tiger"),
    ("10.5", "Mac OS X", "Leopard"),
    ("10.6", "Mac OS X", "Snow Leopard"),
    ("10.7", "Mac OS X", "Lion"),
    ("10.8", "OS X", "Mountain Lion"),
    ("10.9", "OS X", "Mavericks"),
    ("10.10", "OS X", "Yosemite"),
    ("10.11", "OS X", "El Capitan"),
    ("10.12", "macOS", "Sierra"),
    ("10.13", "macOS", "High Sierra"),
    ("10.14", "macOS", "Mojave"),
    ("10.15", "macOS", "Catalina"),
    ("10.16", "macOS", "Big Sur"),
    ("11", "macOS", "Big Sur"),
    ("12", "macOS", "Monterey"),
    ("13", "macOS", "Ventura"),
    ("14", "macOS", "Sonoma"),
    ("15", "macOS", "Sequoia"),
    ("26", "macOS", "Tahoe"),
)


def _macos_distro(shorthand: str) -> str:
    """"macOS Sequoia 15.6 24G84"; newer releases not in the table show as "macOS 27.0 26A434"."""
    version = util.trim(util.run(["sw_vers", "-productVersion"]) or "")
    build = util.trim(util.run(["sw_vers", "-buildVersion"]) or "")
    if not version:
        return ""
    family, name = "macOS", ""
    for prefix, fam, release in _MACOS_RELEASES:
        if version == prefix or version.startswith(prefix + "."):
            family, name = fam, release
            break
    if shorthand == "tiny":
        return f"{family} {version}"
    distro = util.trim(f"{family} {name} {version}")
    if shorthand != "on":
        distro = util.trim(f"{distro} {build}")
    return distro


def get_distro(host: Host, opts: Options) -> str:
    """Detect the distro name. Mirrors neofetch's get_distro()."""
    if host.os not in ("Linux", "BSD", "MINIX", "Mac OS X", "macOS"):
        return {"Windows": ""}.get(host.os, host.os or "Unknown")

    distro = ""
    shorthand = opts.distro_shorthand

    if host.os in ("Mac OS X", "macOS"):
        distro = _macos_distro(shorthand)

    def _read(path: str) -> str | None:
        return util.read_text(path)

    if host.os == "Linux":
        if _read("/bedrock/etc/bedrock-release") is not None and not util.env(
            "BEDROCK_RESTRICT"
        ):
            distro = (
                "Bedrock Linux"
                if shorthand in ("on", "tiny")
                else util.trim(_read("/bedrock/etc/bedrock-release") or "")
            )
        elif _read("/etc/redstar-release") is not None:
            if shorthand in ("on", "tiny"):
                distro = "Red Star OS"
            else:
                m = re.search(r"[0-9.]+", _read("/etc/redstar-release") or "")
                distro = f"Red Star OS {m.group(0) if m else ''}".strip()
        elif _read("/etc/armbian-release") is not None:
            rel = _parse_os_release(_read("/etc/armbian-release") or "")
            distro = f"Armbian {rel.get('DISTRIBUTION_CODENAME', '')} ({rel.get('VERSION', '')})"
        elif _read("/etc/siduction-version") is not None:
            if shorthand in ("on", "tiny"):
                distro = "Siduction"
            else:
                out = util.run(["lsb_release", "-sic"]) or ""
                distro = f"Siduction ({util.trim(out)})"
        elif _read("/etc/mcst_version") is not None:
            distro = (
                "OS Elbrus"
                if shorthand in ("on", "tiny")
                else f"OS Elbrus {util.trim(_read('/etc/mcst_version') or '')}"
            )
        elif util.which("pveversion"):
            if shorthand in ("on", "tiny"):
                distro = "Proxmox VE"
            else:
                out = util.trim(util.run(["pveversion"]) or "")
                out = out[len("pve-manager/") :] if out.startswith("pve-manager/") else out
                distro = f"Proxmox VE {out.rsplit('/', 1)[0] if '/' in out else out}"
        elif util.which("lsb_release"):
            flags = "-si" if shorthand in ("on", "tiny") else "-sd"
            distro = util.trim(util.run(["lsb_release", flags]) or "")
        else:
            for path in (
                "/etc/lsb-release",
                "/usr/lib/os-release",
                "/etc/os-release",
                "/etc/openwrt_release",
            ):
                text = _read(path)
                if text is not None:
                    rel = _parse_os_release(text)
                    if shorthand == "on":
                        distro = (
                            f"{rel.get('NAME', rel.get('DISTRIB_ID', ''))} "
                            f"{rel.get('VERSION_ID', rel.get('DISTRIB_RELEASE', ''))}"
                        )
                    elif shorthand == "tiny":
                        distro = rel.get(
                            "NAME",
                            rel.get("DISTRIB_ID", rel.get("TAILS_PRODUCT_NAME", "")),
                        )
                    else:
                        distro = (
                            f"{rel.get('PRETTY_NAME', rel.get('DISTRIB_DESCRIPTION', ''))} "
                            f"{rel.get('UBUNTU_CODENAME', '')}"
                        )
                    break
            if not distro and _read("/etc/GoboLinuxVersion") is not None:
                distro = (
                    "GoboLinux"
                    if shorthand in ("on", "tiny")
                    else f"GoboLinux {util.trim(_read('/etc/GoboLinuxVersion') or '')}"
                )
            if not distro and _read("/etc/SDE-VERSION") is not None:
                distro = util.trim(_read("/etc/SDE-VERSION") or "")
                if shorthand in ("on", "tiny"):
                    distro = distro.split(" ")[0]
            if not distro and util.which("crux"):
                out = util.trim(util.run(["crux"]) or "")
                if shorthand == "on":
                    out = out.replace("version", "")
                elif shorthand == "tiny":
                    out = out.split("version")[0]
                distro = out
            if not distro and util.which("tazpkg"):
                distro = f"SliTaz {util.trim(_read('/etc/slitaz-release') or '')}"
            if not distro and util.which("kpt") and util.which("kpm"):
                distro = "KSLinux"
            if not distro and os.path.isdir("/system/app") and os.path.isdir(
                "/system/priv-app"
            ):
                out = util.run(["getprop", "ro.build.version.release"]) or ""
                distro = f"Android {util.trim(out)}"
            if not distro:
                lsb = _read("/etc/lsb-release") or ""
                if "CHROMEOS" in lsb:
                    distro = "Chrome OS"
            if not distro and util.which("guix"):
                if shorthand in ("on", "tiny"):
                    distro = "Guix System"
                else:
                    out = util.run(["guix", "-V"]) or ""
                    parts = out.split()
                    distro = f"Guix System {parts[3] if len(parts) > 3 else ''}".strip()

        if not distro:
            blobs = []
            for path in _glob.glob("/etc/*-release"):
                text = _read(path)
                if text:
                    blobs.append(text)
            distro = "".join(blobs)

        version_text = _read("/proc/version") or ""
        if "Microsoft" in version_text or "Microsoft" in host.kernel_version:
            out = util.trim(util.run(["wmic.exe", "os", "get", "Version"]) or "")
            windows_version = util.trim(out.replace("Version", ""))
            if shorthand == "on":
                distro += f" [Windows {windows_version}]"
            elif shorthand == "tiny":
                distro = f"Windows {windows_version[:2]}"
            else:
                distro += f" on Windows {windows_version}"
        elif "chrome-bot" in version_text or os.path.exists("/dev/cros_ec"):
            if "Chrome" not in distro:
                if shorthand == "on":
                    distro += " [Chrome OS]"
                elif shorthand == "tiny":
                    distro = "Chrome OS"
                else:
                    distro += " on Chrome OS"
                if distro.startswith(" on "):
                    distro = distro[len(" on ") :]

        distro = util.trim_quotes(util.trim(distro)).replace("NAME=", "")

        if distro.startswith("Ubuntu"):
            config_dirs = util.env("XDG_CONFIG_DIRS")
            for needle, flavor in (
                ("studio", "Ubuntu Studio"),
                ("plasma", "Kubuntu"),
                ("mate", "Ubuntu MATE"),
                ("xubuntu", "Xubuntu"),
                ("Lubuntu", "Lubuntu"),
                ("budgie", "Ubuntu Budgie"),
                ("cinnamon", "Ubuntu Cinnamon"),
            ):
                if needle in config_dirs:
                    distro = distro.replace("Ubuntu", flavor, 1)
                    break

    distro = distro.replace("Enterprise Server", "")
    if not distro:
        distro = f"{host.os} (Unknown)"
    if opts.os_arch == "on":
        distro += f" {host.machine_arch or host.kernel_machine}"
    return util.trim(distro)


# ---------------------------------------------------------------------------
# model / title / kernel / uptime
# ---------------------------------------------------------------------------

_DUMMY_OEM = (
    "To be filled by O.E.M.",
    "To Be Filled",
    "OEM",
    "Not Applicable",
    "System Product Name",
    "System Version",
    "Undefined",
    "Default string",
    "Not Specified",
    "Type1ProductConfigId",
    "INVALID",
    "All Series",
    "\ufffd",
)


def get_model(host: Host, opts: Options) -> str:
    model = ""
    if host.os == "Linux":
        if os.path.isdir("/system/app") and os.path.isdir("/system/priv-app"):
            brand = util.trim(util.run(["getprop", "ro.product.brand"]) or "")
            prod = util.trim(util.run(["getprop", "ro.product.model"]) or "")
            model = util.trim(f"{brand} {prod}")
        else:
            vendor = util.read_line(
                "/sys/devices/virtual/dmi/id/board_vendor"
            )
            board = util.read_line("/sys/devices/virtual/dmi/id/board_name")
            if vendor or board:
                model = util.trim(f"{vendor or ''} {board or ''}")
            else:
                name = util.read_line(
                    "/sys/devices/virtual/dmi/id/product_name"
                )
                ver = util.read_line(
                    "/sys/devices/virtual/dmi/id/product_version"
                )
                if name or ver:
                    model = util.trim(f"{name or ''} {ver or ''}")
                else:
                    model = util.trim(
                        util.read_text(
                            "/sys/firmware/devicetree/base/model"
                        )
                        or ""
                    ) or util.trim(util.read_text("/tmp/sysinfo/model") or "")
    elif host.os == "BSD":
        out = util.run(["sysctl", "-n", "hw.vendor", "hw.product"]) or ""
        model = util.trim(out.replace("\n", " "))
    elif host.os in ("Mac OS X", "macOS"):
        # "Mac mini (Mac16,10)"; neofetch shows only the identifier.
        identifier = _sysctl("hw.model")
        m = re.search(r"^\s*Model Name:\s*(.+?)\s*$", _system_profiler(), re.M)
        if m and identifier:
            model = f"{m.group(1)} ({identifier})"
        else:
            model = identifier or (m.group(1) if m else "")
    if model.startswith("To Be Filled"):
        model = ""
    for dummy in _DUMMY_OEM:
        model = model.replace(dummy, "")
    model = util.trim(model)
    if model.startswith("Standard PC"):
        model = f"KVM/QEMU ({model})"
    elif model.startswith("OpenBSD"):
        model = f"vmm ({model})"
    return model


def get_title(host: Host, opts: Options) -> tuple[str, str]:
    user = util.env("USER")
    if not user:
        out = util.run(["id", "-un"])
        user = util.trim(out) if out else os.path.expanduser("~").split("/")[-1]
    if opts.title_fqdn == "on":
        hostname = socket.getfqdn()
    else:
        hostname = util.env("HOSTNAME") or socket.gethostname()
    return user, hostname


def get_kernel(host: Host, opts: Options) -> str:
    if host.os in ("AIX", "IRIX"):
        return ""
    if host.os == "Haiku":
        out = util.run(["uname", "-v"]) or ""
        return util.trim(out)
    if host.os == "Windows":
        out = util.run(["wmic", "os", "get", "Version"]) or ""
        return util.trim(out.replace("Version", ""))
    if opts.kernel_shorthand == "on":
        return host.kernel_version
    return util.trim(f"{host.kernel_name} {host.kernel_version}")


def format_uptime(total_seconds: int, shorthand: str) -> str:
    days = total_seconds // 86400
    hours = (total_seconds // 3600) % 24
    minutes = (total_seconds // 60) % 60
    d = f"{days} day{'s' if days != 1 else ''}" if days else ""
    h = f"{hours} hour{'s' if hours != 1 else ''}" if hours else ""
    m = f"{minutes} minute{'s' if minutes != 1 else ''}" if minutes else ""
    uptime = ", ".join(part for part in (d, h, m) if part)
    if not uptime:
        uptime = f"{total_seconds} seconds"
    if shorthand == "on":
        uptime = uptime.replace("minutes", "mins").replace("minute", "min")
        uptime = uptime.replace("seconds", "secs")
    elif shorthand == "tiny":
        for long, short in (
            (" days", "d"),
            (" day", "d"),
            (" hours", "h"),
            (" hour", "h"),
            (" minutes", "m"),
            (" minute", "m"),
            (" seconds", "s"),
        ):
            uptime = uptime.replace(long, short)
        uptime = uptime.replace(",", "")
    return uptime


def get_uptime(host: Host, opts: Options) -> str:
    seconds: int | None = None
    if host.os in ("Linux", "Windows", "MINIX"):
        text = util.read_text("/proc/uptime")
        if text:
            try:
                seconds = int(float(text.split()[0]))
            except (ValueError, IndexError):
                seconds = None
    elif host.os in ("Mac OS X", "macOS", "BSD"):
        # kern.boottime: "{ sec = 1790886054, usec = 385528 } Thu Oct  1 15:20:54 2026"
        m = re.search(r"sec\s*=\s*(\d+)", _sysctl("kern.boottime"))
        if m:
            import time

            seconds = int(time.time()) - int(m.group(1))
    if seconds is None:
        out = util.run(["uptime", "-s"])
        if out:
            import time
            from datetime import datetime

            try:
                boot = int(
                    datetime.strptime(util.trim(out), "%Y-%m-%d %H:%M:%S").timestamp()
                )
                seconds = int(time.time()) - boot
            except ValueError:
                seconds = None
    if seconds is None:
        return ""
    return format_uptime(seconds, opts.uptime_shorthand)


# ---------------------------------------------------------------------------
# packages
# ---------------------------------------------------------------------------

def _count_lines(output: str | None, header: int = 0) -> int:
    if not output:
        return 0
    lines = [line for line in output.splitlines() if line.strip()]
    return max(0, len(lines) - header)


def _count_glob(patterns: list[str]) -> int:
    count = 0
    for pattern in patterns:
        for chunk in pattern.split():
            count += len(_glob.glob(chunk))
    return count


def _snapd_running() -> bool:
    out = util.run(["ps", "-e", "-o", "comm="])
    if out is None:
        return False
    return any(line.strip() == "snapd" for line in out.splitlines())


def get_packages(host: Host, opts: Options) -> str:
    """Count installed packages per manager. Mirrors get_packages()."""
    packages = 0
    managers: list[str] = []
    manager_names: list[str] = []

    def pac(count: int, name: str) -> None:
        if count > 0:
            managers.append(f"{count} ({name})")
            manager_names.append(name)

    def tot(argv: list[str], name: str | None = None, header: int = 0) -> None:
        nonlocal packages
        mgr = name or argv[0]
        n = _count_lines(util.run(argv, timeout=30), header)
        packages += n
        pac(n, mgr)

    def count_brew() -> None:
        # Formulae and casks together, as one "brew" entry like neofetch.
        nonlocal packages
        n = 0
        for flag in ("--cellar", "--caskroom"):
            out = util.run(["brew", flag])
            if out and util.trim(out):
                n += len(_glob.glob(os.path.join(util.trim(out), "*")))
        packages += n
        pac(n, "brew")

    def count_nix(include_default: bool) -> None:
        nonlocal packages
        n = _count_lines(util.run(["nix-store", "-qR", "/run/current-system/sw"], timeout=60))
        packages += n
        pac(n, "nix-system")
        user_pkgs = ""
        for path in (
            os.path.expanduser("~/.nix-profile"),
            f"/etc/profiles/per-user/{util.env('USER')}",
        ):
            user_pkgs += util.run(["nix-store", "-qR", path], timeout=60) or ""
        n = _count_lines(user_pkgs)
        packages += n
        pac(n, "nix-user")
        if include_default:
            n = _count_lines(
                util.run(["nix-store", "-qR", "/nix/var/nix/profiles/default"], timeout=60)
            )
            packages += n
            pac(n, "nix-default")

    if host.os in ("Mac OS X", "macOS", "MINIX"):
        if util.which("port"):
            # First line is "The following ports are currently installed:".
            tot(["port", "installed"], "port", header=1)
        if util.which("brew"):
            count_brew()
        if util.which("pkgin"):
            tot(["pkgin", "list"], "pkgin")
        if util.which("dpkg"):
            tot(["dpkg-query", "-f", ".\n", "-W"], "dpkg")
        if util.which("nix-store"):
            count_nix(include_default=False)

    if host.os in ("Linux", "BSD", "Solaris"):
        if util.which("kiss"):
            tot(["kiss", "l"])
        if util.which("cpt-list"):
            tot(["cpt-list"])
        if util.which("pacman-key"):
            tot(["pacman", "-Qq", "--color", "never"], "pacman")
        if util.which("dpkg"):
            tot(["dpkg-query", "-f", ".\n", "-W"], "dpkg")
        if util.which("xbps-query"):
            tot(["xbps-query", "-l"])
        if util.which("apk"):
            tot(["apk", "info"], "apk")
        if util.which("opkg"):
            tot(["opkg", "list-installed"], "opkg")
        if util.which("pacman-g2"):
            tot(["pacman-g2", "-Q"])
        if util.which("lvu"):
            tot(["lvu", "installed"], "lvu")
        if util.which("tce-status"):
            tot(["tce-status", "-i"], "tce-status")
        if util.which("pkg_info"):
            tot(["pkg_info"])
        if util.which("pkgin"):
            tot(["pkgin", "list"], "pkgin")
        if util.which("tazpkg"):
            tot(["tazpkg", "list"], "tazpkg", header=6)
        if util.which("gaze"):
            tot(["gaze", "installed"], "sorcery")
        if util.which("alps"):
            tot(["alps", "showinstalled"], "alps")
        if util.which("butch"):
            tot(["butch", "list"], "butch")
        if util.which("swupd"):
            tot(["swupd", "bundle-list", "--quiet"], "swupd")
        if util.which("pisi"):
            tot(["pisi", "li"], "pisi")
        if util.which("pacstall"):
            tot(["pacstall", "-L"], "pacstall")

        if (
            util.which("dnf")
            and util.which("sqlite3")
            and os.path.isfile("/var/cache/dnf/packages.db")
        ):
            out = util.run(
                [
                    "sqlite3",
                    "/var/cache/dnf/packages.db",
                    "SELECT count(pkg) FROM installed",
                ],
                timeout=30,
            )
            try:
                pac(int(util.trim(out or "")), "dnf")
            except ValueError:
                pass
        elif util.which("rpm"):
            tot(["rpm", "-qa"], "rpm")

        if os.path.isfile("/etc/SDE-VERSION") and util.which("mine"):
            tot(["mine", "-q"], "mine")

        if util.which("brew"):
            count_brew()
        if _glob.glob("/var/db/pkg/*/*") or util.which("emerge"):
            n = _count_glob(["/var/db/pkg/*/*"])
            packages += n
            pac(n, "emerge")
        if util.which("eopkg"):
            n = _count_glob(["/var/lib/eopkg/package/*"])
            packages += n
            pac(n, "eopkg")
        if util.which("pkgtool"):
            n = _count_glob(["/var/log/packages/*"])
            packages += n
            pac(n, "pkgtool")

        if util.which("kpm-pkg"):
            out = util.run(["kpm", "--get-selections"], timeout=30) or ""
            packages += sum(
                1 for line in out.splitlines() if not line.rstrip().endswith("deinstall")
            )

        if util.which("guix"):
            n = _count_lines(
                util.run(
                    ["guix", "package", "-p", "/run/current-system/profile", "-I"],
                    timeout=30,
                )
            )
            packages += n
            pac(n, "guix-system")
            n = _count_lines(util.run(["guix", "package", "-I"], timeout=30))
            packages += n
            pac(n, "guix-user")

        if util.which("nix-store"):
            count_nix(include_default=True)

        if host.os == "Linux" and "FreeBSD" not in host.kernel_name:
            if util.which("pkginfo"):
                tot(["pkginfo", "-i"], "pkginfo")
        if host.kernel_name in ("FreeBSD", "DragonFly") and util.which("pkg"):
            tot(["pkg", "info"], "pkg")

        if util.which("flatpak"):
            tot(["flatpak", "list"], "flatpak")
        if util.which("spm"):
            tot(["spm", "list", "-i"], "spm")
        if util.which("snap") and _snapd_running():
            tot(["snap", "list"], "snap", header=1)

    if packages == 0:
        return ""
    if opts.package_managers == "on":
        return ", ".join(managers).replace("pacman-key", "pacman")
    if opts.package_managers == "tiny":
        return f"{packages} ({', '.join(manager_names)})".replace(
            "pacman-key", "pacman"
        )
    return str(packages)


# ---------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------

def get_shell(host: Host, opts: Options) -> str:
    shell_env = util.env("SHELL")
    shell = f"{shell_env} " if opts.shell_path == "on" else f"{shell_env.split('/')[-1]} "
    if opts.shell_version != "on":
        return util.trim(shell)
    shell_name = shell_env.split("/")[-1]
    version = ""
    if shell_name == "bash":
        version = util.env("BASH_VERSION", "")
        if not version and shell_env:
            out = util.run([shell_env, "-c", 'printf %s "$BASH_VERSION"']) or ""
            version = out.split("-")[0]
        else:
            version = version.split("-")[0]
    elif shell_name in ("sh", "ash", "dash", "es"):
        pass
    elif shell_name.endswith("ksh"):
        out = util.run([shell_env, "-c", 'printf %s "$KSH_VERSION"']) or ""
        version = out.replace(" KSH", "").replace("version", "")
    elif shell_name == "osh":
        version = util.env("OIL_VERSION", "") or (
            util.run([shell_env, "-c", 'printf %s "$OIL_VERSION"']) or ""
        )
    elif shell_name == "tcsh":
        out = util.run([shell_env, "-c", "printf %s $tcsh"]) or ""
        version = out
    elif shell_name == "yash":
        out = util.run([shell_env, "--version"]) or ""
        version = out.replace(f" {shell_name}", "").replace("Yet another shell", "")
        version = version.split("Copyright")[0]
    elif shell_name == "nu":
        out = util.run([shell_env, "-c", "version | get version"]) or ""
        version = out.replace(f" {shell_name}", "")
    elif shell_env:
        out = util.run([shell_env, "--version"]) or ""
        version = out.splitlines()[0] if out else ""
    shell += version
    if shell_name:
        shell = shell.replace(f" {shell_name}", "", 1)
    shell = shell.replace(", version", "")
    shell = shell.replace("xonsh/", "xonsh ")
    shell = re.sub(r"options.*", "", shell)
    shell = re.sub(r"\(.*\)", "", shell)
    return util.trim(shell)


# ---------------------------------------------------------------------------
# desktop environment / window manager
# ---------------------------------------------------------------------------

def _ps_commands() -> list[tuple[int, str]]:
    """Return [(pid, comm)] for all processes."""
    out = util.run(["ps", "-e", "-o", "pid=,comm="])
    result = []
    if not out:
        return result
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            result.append((int(parts[0]), parts[1].strip()))
    return result


def get_wm(host: Host, opts: Options) -> str:
    if host.os in ("macOS", "Mac OS X"):
        procs = {comm for _, comm in _ps_commands()}
        if "chunkwm" in procs:
            return "chunkwm"
        if "kwm" in procs:
            return "Kwm"
        if "yabai" in procs:
            return "yabai"
        if "Amethyst" in procs:
            return "Amethyst"
        if "Spectacle" in procs:
            return "Spectacle"
        if "Rectangle" in procs:
            return "Rectangle"
        return "Quartz Compositor"
    if host.os == "Windows":
        return "DWM.exe"

    runtime_dir = util.env("XDG_RUNTIME_DIR")
    wayland_display = util.env("WAYLAND_DISPLAY", "wayland-0")
    socket_path = os.path.join(runtime_dir, wayland_display) if runtime_dir else ""
    if socket_path and os.path.exists(socket_path):
        candidates = (
            "arcan", "asc", "clayland", "dwc", "fireplace", "gnome-shell",
            "greenfield", "grefsen", "hikari", "kwin", "lipstick", "maynard",
            "mazecompositor", "motorcar", "orbital", "orbment", "perceptia",
            "river", "rustland", "sway", "ulubis", "velox", "wavy",
            "way-cooler", "wayfire", "wayhouse", "westeros", "westford",
            "weston",
        )
        for _, comm in _ps_commands():
            if comm in candidates:
                return comm
        return ""

    if util.env("DISPLAY"):
        for _, comm in _ps_commands():
            if comm in (
                "sowm", "catwm", "fvwm", "dwm", "2bwm", "monsterwm",
                "tinywm", "x11fs", "xmonad",
            ):
                return comm
        if util.which("xprop"):
            out = util.run(["xprop", "-root", "-notype", "_NET_SUPPORTING_WM_CHECK"])
            if out and "=" in out:
                wid = out.split()[-1]
                info = util.run(
                    ["xprop", "-id", wid, "-notype", "-len", "100",
                     "-f", "_NET_WM_NAME", "8t"]
                ) or ""
                wm = info.split("_NET_WM_NAME = ", 1)[-1].strip().strip('"')
                if wm and wm != info.strip():
                    if "WINDOWMAKER" in wm:
                        return "wmaker"
                    if "GNOME" in wm and "Shell" in wm:
                        return "Mutter"
                    return wm
    return ""


def get_de(host: Host, opts: Options, wm: str = "") -> str:
    if host.os in ("macOS", "Mac OS X"):
        return "Aqua"
    if host.os == "Windows":
        return "Fluent"
    de = ""
    if "regolith" in util.env("DESKTOP_SESSION"):
        de = "Regolith"
    elif util.env("XDG_CURRENT_DESKTOP"):
        de = util.env("XDG_CURRENT_DESKTOP").replace("X-", "")
        de = de.replace("Budgie:GNOME", "Budgie").replace(":Unity7:ubuntu", "")
    elif util.env("DESKTOP_SESSION"):
        de = util.env("DESKTOP_SESSION").split("/")[-1]
    elif util.env("GNOME_DESKTOP_SESSION_ID"):
        de = "GNOME"
    elif util.env("MATE_DESKTOP_SESSION_ID"):
        de = "MATE"
    elif util.env("TDE_FULL_SESSION"):
        de = "Trinity"
    if de and de == wm:
        return ""
    if util.env("DISPLAY") and not de and util.which("xprop"):
        out = util.run(["xprop", "-root"]) or ""
        for line in out.splitlines():
            if "KDE_SESSION_VERSION" in line or "_MUFFIN" in line or "xfce" in line.lower():
                de = line.strip()
                break
    if "KDE_SESSION_VERSION" in de:
        de = "KDE" + de.split("=")[-1].strip()
    elif "xfce4" in de:
        de = "Xfce4"
    elif "xfce5" in de:
        de = "Xfce5"
    elif "xfce" in de.lower():
        de = "Xfce"
    elif "mate" in de.lower():
        de = "MATE"
    elif "GNOME" in de:
        de = "GNOME"
    elif "MUFFIN" in de:
        de = "Cinnamon"
    try:
        kde_version = int(util.env("KDE_SESSION_VERSION", "0"))
    except ValueError:
        kde_version = 0
    if kde_version >= 4:
        de = de.replace("KDE", "Plasma")

    if opts.de_version == "on" and de:
        short = de.split(" ")[0]
        lookup = {
            "Plasma": ["plasmashell", "--version"],
            "MATE": ["mate-session", "--version"],
            "Xfce": ["xfce4-session", "--version"],
            "GNOME": ["gnome-shell", "--version"],
            "Cinnamon": ["cinnamon", "--version"],
            "Budgie": ["budgie-desktop", "--version"],
            "LXQt": ["lxqt-session", "--version"],
            "Unity": ["unity", "--version"],
        }
        ver = ""
        if short in lookup and util.which(lookup[short][0]):
            out = util.run(lookup[short]) or ""
            ver = out.split(")")[0].split()[-1].strip('"') if out else ""
        elif short.startswith("Deepin"):
            text = util.read_text("/etc/os-version") or ""
            m = re.search(r"MajorVersion\s*=\s*(\S+)", text)
            ver = m.group(1) if m else ""
        if ver:
            de = f"{de} {ver}"
    if de and util.env("WAYLAND_DISPLAY"):
        de += " (Wayland)"
    return de


def _kde_config_dir() -> str:
    home = os.path.expanduser("~")
    for argv in (
        ["kf5-config", "--path", "config"],
        ["kde4-config", "--path", "config"],
        ["kde-config", "--path", "config"],
    ):
        if util.which(argv[0]):
            out = util.run(argv) or ""
            return out.split(":")[0].strip()
    for candidate in (
        os.path.join(home, ".kde4/share/config"),
        os.path.join(home, ".kde3/share/config"),
    ):
        if os.path.isdir(candidate):
            return candidate
    return ""


def get_wm_theme(host: Host, opts: Options, wm: str = "", de: str = "") -> str:
    """Detect the window-manager theme. Mirrors get_wm_theme()."""
    home = os.path.expanduser("~")
    theme = ""
    if wm == "E16":
        text = util.read_text(os.path.join(home, ".e16/e_config--0.0.cfg")) or ""
        m = re.search(r"theme\.name\s*=\s*(\S+)", text)
        theme = m.group(1) if m else ""
    elif wm == "Sawfish":
        text = util.read_text(os.path.join(home, ".sawfish/custom")) or ""
        m = re.search(r"default-frame-style.*?\(quote\s+(\S+)", text)
        theme = m.group(1) if m else ""
    elif wm in ("Cinnamon", "Muffin", "Mutter (Muffin)"):
        if util.which("gsettings"):
            detheme = util.trim(
                util.run(
                    ["gsettings", "get", "org.cinnamon.theme", "name"]
                )
                or ""
            )
            wmtheme = util.trim(
                util.run(
                    ["gsettings", "get", "org.cinnamon.desktop.wm.preferences", "theme"]
                )
                or ""
            )
            theme = util.trim(f"{detheme} ({wmtheme})")
    elif wm in ("Compiz", "Mutter", "Gala"):
        if util.which("gsettings"):
            theme = util.trim(
                util.run(
                    ["gsettings", "get", "org.gnome.shell.extensions.user-theme", "name"]
                )
                or ""
            ).strip("'")
            if not theme:
                theme = util.trim(
                    util.run(
                        ["gsettings", "get", "org.gnome.desktop.wm.preferences", "theme"]
                    )
                    or ""
                ).strip("'")
        elif util.which("gconftool-2"):
            theme = util.trim(
                util.run(
                    ["gconftool-2", "-g", "/apps/metacity/general/theme"]
                )
                or ""
            )
    elif wm.startswith("Metacity"):
        if de == "Deepin" and util.which("gsettings"):
            theme = util.trim(
                util.run(
                    ["gsettings", "get",
                     "com.deepin.wrap.gnome.desktop.wm.preferences", "theme"]
                )
                or ""
            ).strip("'")
        elif de == "MATE" and util.which("gsettings"):
            theme = util.trim(
                util.run(
                    ["gsettings", "get", "org.mate.Marco.general", "theme"]
                )
                or ""
            ).strip("'")
        elif util.which("gconftool-2"):
            theme = util.trim(
                util.run(
                    ["gconftool-2", "-g", "/apps/metacity/general/theme"]
                )
                or ""
            )
    elif wm in ("E17", "Enlightenment"):
        if util.which("eet"):
            out = util.run(
                ["eet", "-d", os.path.join(home, ".e/e/config/standard/e.cfg"), "config"]
            ) or ""
            m = re.search(r'value "file" string[^"]*"([^"]*\.edj)', out)
            if m:
                theme = m.group(1).split("/")[-1].rsplit(".", 1)[0]
    elif wm == "Fluxbox":
        init = os.path.join(home, ".fluxbox/init")
        if os.path.isfile(init):
            text = util.read_text(init) or ""
            m = re.search(r"styleFile.*/(.+)", text)
            theme = m.group(1).strip() if m else ""
    elif wm.startswith("IceWM"):
        path = os.path.join(home, ".icewm/theme")
        if os.path.isfile(path):
            text = util.read_text(path) or ""
            m = re.search(r'^[^#]*["/,]([^"/,]+)', text, re.M)
            theme = m.group(1).strip() if m else ""
    elif wm == "Openbox":
        config_home = util.env(
            "XDG_CONFIG_HOME", os.path.join(home, ".config")
        )
        if de.startswith("LXDE"):
            ob_file = "lxde-rc"
        elif de.startswith("LXQt"):
            ob_file = "lxqt-rc"
        else:
            ob_file = "rc"
        path = os.path.join(config_home, "openbox", f"{ob_file}.xml")
        if os.path.isfile(path):
            text = util.read_text(path) or ""
            m = re.search(r"<theme>.*?<name>(.*?)</name>", text, re.S)
            theme = m.group(1).strip() if m else ""
    elif wm == "PekWM":
        path = os.path.join(home, ".pekwm/config")
        if os.path.isfile(path):
            text = util.read_text(path) or ""
            m = re.search(r"Theme.*?/([^/\"]+)", text)
            theme = m.group(1).strip() if m else ""
    elif wm == "Xfwm4" and util.which("xfconf-query"):
        theme = util.trim(util.run(["xfconf-query", "-c", "xfwm4", "-p", "/general/theme"]) or "")
    elif wm.startswith("KWin"):
        kde_dir = _kde_config_dir()
        kwinrc = os.path.join(kde_dir, "kwinrc")
        if os.path.isfile(kwinrc):
            text = util.read_text(kwinrc) or ""
            m = re.search(r"^theme=(.*)$", text, re.M)
            if m:
                theme = re.sub(r"theme=.*qml_|theme=.*svg__", "", m.group(0))
            if not theme:
                m = re.search(r"^library=org\.kde\.(.*)$", text, re.M)
                theme = m.group(1) if m else ""
            if not theme:
                m = re.search(r"^PluginLib=kwin3_(.*)$", text, re.M)
                theme = m.group(1) if m else ""
            theme = theme.replace("theme=", "")
    return util.trim_quotes(util.trim(theme))


# ---------------------------------------------------------------------------
# cpu
# ---------------------------------------------------------------------------

_CPU_STRIP_FIRST = (
    "(TM)", "(tm)", "(R)", "(r)", "CPU", "Processor", "Dual-Core",
    "Quad-Core", "Six-Core", "Eight-Core",
)
_CPU_STRIP_RE = (
    r"[1-9][0-9]-Core", r"[0-9]-Core", r", .* Compute Cores",
)
_CPU_STRIP_CORE = ("Core ",)
# (is_regex, pattern) pairs applied after "Core ".
_CPU_STRIP_LAST = (
    (True, r"\(.*AuthenticAMD.*\)"),
    (True, r"with Radeon .* Graphics"),
    (False, ", altivec supported"),
    (True, r"FPU.*"),
    (True, r"Chip Revision.*"),
    (False, "Technologies, Inc"),
)


def _clean_cpu_name(cpu: str) -> str:
    # Order mirrors neofetch: fixed tokens, core-count globs, "Core ",
    # vendor/noise patterns, then the Core2 fixup.
    for token in _CPU_STRIP_FIRST:
        cpu = cpu.replace(token, "")
    for pattern in _CPU_STRIP_RE:
        cpu = re.sub(pattern, "", cpu)
    for token in _CPU_STRIP_CORE:
        cpu = cpu.replace(token, "")
    for is_regex, pattern in _CPU_STRIP_LAST:
        cpu = re.sub(pattern, "", cpu) if is_regex else cpu.replace(pattern, "")
    cpu = cpu.replace("Core2", "Core 2")
    return util.trim(re.sub(r"\s+", " ", cpu))


def _cpu_temp_celsius() -> str:
    for hwmon in _glob.glob("/sys/class/hwmon/*"):
        try:
            with open(os.path.join(hwmon, "name")) as f:
                name = f.read().strip()
        except OSError:
            continue
        if re.search(r"(cpu_thermal|coretemp|fam15h_power|k10temp)", name):
            inputs = sorted(_glob.glob(os.path.join(hwmon, "temp*_input")))
            if inputs:
                try:
                    with open(inputs[0]) as f:
                        return f.read().strip()
                except OSError:
                    return ""
    return ""


def _strip_cpu_brand(cpu: str) -> str:
    for brand in ("AMD ", "Intel ", "Core? Duo ", "Qualcomm "):
        cpu = re.sub(brand, "", cpu, count=1) if "?" in brand else cpu.replace(brand, "", 1)
    return cpu


def _get_cpu_macos(opts: Options) -> str:
    # Intel: "Intel(R) Core(TM) i7-8700B CPU @ 3.20GHz"; Apple Silicon: "Apple M4".
    cpu = _clean_cpu_name(_sysctl("machdep.cpu.brand_string"))
    cores = ""
    if opts.cpu_cores in ("logical", "on"):
        cores = _sysctl("hw.logicalcpu_max")
    elif opts.cpu_cores == "physical":
        cores = _sysctl("hw.physicalcpu_max")

    if opts.cpu_brand == "off":
        cpu = _strip_cpu_brand(cpu)
    if opts.cpu_speed == "off":
        cpu = re.sub(r"\s*@.*", "", cpu)
    if opts.cpu_cores != "off" and cores.isdigit():
        # Cores go before the speed, like neofetch. Apple Silicon names
        # carry no speed, so append them instead.
        if "@" in cpu:
            cpu = cpu.replace("@", f"({cores}) @", 1)
        else:
            cpu = f"{cpu} ({cores})"
    return util.trim(cpu)


def get_cpu(host: Host, opts: Options) -> str:
    if host.os in ("Mac OS X", "macOS"):
        return _get_cpu_macos(opts)
    if host.os not in ("Linux", "MINIX", "Windows"):
        return ""
    cpuinfo = util.read_text("/proc/cpuinfo") or ""
    cpu = ""
    machine = host.kernel_machine
    if machine in ("frv", "hppa", "m68k", "openrisc") or machine.startswith(
        ("or", "powerpc", "ppc", "sparc")
    ):
        m = re.search(r"^(?:cpu\t|CPU).*?:\s*(.+)$", cpuinfo, re.M)
        cpu = m.group(1) if m else ""
    elif machine.startswith("s390"):
        m = re.search(r"^machine.*=\s*(\S+)", cpuinfo, re.M)
        cpu = m.group(3) if m and len(m.groups()) >= 3 else (m.group(1) if m else "")
    elif machine in ("ia64", "m32r"):
        m = re.search(r"^model.*?:\s*(.+)$", cpuinfo, re.M)
        cpu = m.group(1) if m else ""
        if not cpu:
            m = re.search(r"^family.*?:\s*(.+)$", cpuinfo, re.M)
            cpu = m.group(1) if m else ""
    else:
        found = ""
        for line in cpuinfo.splitlines():
            if re.match(r"model name|Hardware|Processor|^cpu model|chip type|^cpu type", line):
                parts = re.split(r"\s*: | @", line, maxsplit=1)
                found = parts[1] if len(parts) > 1 else ""
                if line.startswith("Hardware"):
                    break
        cpu = found

    # Speed.
    speed = ""
    speed_dir = "/sys/devices/system/cpu/cpu0/cpufreq"
    if os.path.isdir(speed_dir):
        for key in (opts.speed_type, "bios_limit", "scaling_max_freq", "cpuinfo_max_freq"):
            text = util.read_text(os.path.join(speed_dir, key))
            if text and text.strip().isdigit():
                speed = str(int(text.strip()) // 1000)
                break
    elif machine.startswith("sparc"):
        text = util.read_text("/sys/devices/system/cpu/cpu0/clock_tick")
        if text and text.strip().isdigit():
            speed = str(int(text.strip()) // 1000000)
    else:
        for line in cpuinfo.splitlines():
            if re.match(r"cpu MHz|^clock", line):
                speed = re.split(r": |\.", line)[1].strip().replace("MHz", "")
                break

    deg = ""
    temp_raw = _cpu_temp_celsius()
    if temp_raw and temp_raw.lstrip("-").isdigit():
        deg = str(int(temp_raw) * 100 // 10000)

    cores = ""
    if opts.cpu_cores in ("logical", "on"):
        if machine.startswith("sparc") and util.which("lscpu"):
            out = util.run(["lscpu"]) or ""
            m = re.search(r"^CPU\(s\):\s*(\S+)", out, re.M)
            cores = m.group(1) if m else ""
        else:
            cores = str(sum(1 for line in cpuinfo.splitlines() if line.startswith("processor")))
    elif opts.cpu_cores == "physical":
        if machine.startswith("sparc") and util.which("lscpu"):
            out = util.run(["lscpu"]) or ""
            m1 = re.search(r"^Core\(s\) per socket:\s*(\S+)", out, re.M)
            m2 = re.search(r"^Socket\(s\):\s*(\S+)", out, re.M)
            if m1 and m2:
                cores = str(int(m1.group(1)) * int(m2.group(1)))
        else:
            seen = set()
            for line in cpuinfo.splitlines():
                if line.startswith("core id"):
                    seen.add(line)
            cores = str(len(seen))

    cpu = _clean_cpu_name(cpu)
    cores = re.sub(r"\s+", "", cores)
    speed = re.sub(r"\s+", "", speed)

    if opts.cpu_brand == "off":
        cpu = _strip_cpu_brand(cpu)

    if opts.cpu_cores != "off" and cores:
        cpu = f"{cpu} ({cores})"
    if opts.cpu_speed != "off" and speed and speed.isdigit():
        mhz = int(speed)
        if mhz < 1000:
            cpu = f"{cpu} @ {mhz}MHz"
        else:
            if opts.speed_shorthand == "on":
                mhz = mhz // 100
            text = str(mhz)
            cpu = f"{cpu} @ {text[0]}.{text[1:]}GHz"
    if opts.cpu_temp != "off" and deg and deg.lstrip("-").isdigit():
        raw = deg.replace(".", "")
        if opts.cpu_temp == "F":
            raw = str(int(raw) * 90 // 50 + 320)
        cpu = f"{cpu} [{raw[:-1]}.{raw[-1:]}\u00b0{opts.cpu_temp.upper() if len(opts.cpu_temp) == 1 else 'C'}]"
    return util.trim(cpu)


# ---------------------------------------------------------------------------
# gpu
# ---------------------------------------------------------------------------

def _lspci_gpu_raw(line: str) -> str:
    """Reproduce neofetch's lspci/awk field surgery for one line.

    awk -F '"|" "|\\(' '/"Display|"3D|"VGA/ {
        a[$0] = $1 " " $3 " " ($(NF-1) ~ /^$|^Device [[:xdigit:]]+$/ ? $4 : $(NF-1))
    }
    NOTE: awk dedupes (`seen`) on this raw value, which still carries the
    PCI slot ($1), so two identical GPUs in different slots are both kept;
    the slot is stripped for display afterwards. Longest-match separator
    first, like gawk.
    """
    fields = re.split(r'" "|\("|"', line)
    nf = len(fields)
    second_last = fields[nf - 2] if nf >= 2 else ""
    if second_last == "" or re.fullmatch(r"Device [0-9a-fA-F]+", second_last):
        tail = fields[3] if nf > 3 else ""
    else:
        tail = second_last
    head = fields[2] if nf > 2 else ""
    return f"{fields[0] if fields else ''} {head} {tail}"


def _get_gpu_macos(opts: Options) -> list[tuple[str, str]]:
    # One line listing every GPU, like neofetch: "AMD Radeon Pro 560X, Intel UHD Graphics 630".
    names = re.findall(r"^\s*Chipset Model:\s*(.+?)\s*$", _system_profiler(), re.M)
    gpu = ", ".join(names)
    if opts.gpu_brand == "off":
        for brand in ("AMD", "NVIDIA", "Intel"):
            gpu = gpu.replace(brand, "", 1)
    gpu = util.trim(gpu)
    return [("", gpu)] if gpu else []


def get_gpu(host: Host, opts: Options) -> list[tuple[str, str]]:
    """Return [(suffix, name)] lines. Mirrors get_gpu()'s prin calls."""
    if host.os in ("Mac OS X", "macOS"):
        return _get_gpu_macos(opts)
    if host.os != "Linux":
        return []
    out = util.run(["lspci", "-mm"], timeout=15) or ""
    seen: dict[str, str] = {}
    for line in out.splitlines():
        if not re.search(r'"Display|"3D|"VGA', line):
            continue
        raw = _lspci_gpu_raw(line)
        if raw not in seen:
            seen[raw] = re.sub(r"^[^ ]+ ", "", raw, count=1)
    gpus = list(seen.values())
    if len(gpus) >= 2 and "Intel" in gpus[0] and "Intel" in gpus[1]:
        gpus = gpus[1:]

    results: list[tuple[str, str]] = []
    for entry in gpus:
        gpu = entry
        if opts.gpu_type == "dedicated" and "Intel" in gpu:
            continue
        if opts.gpu_type == "integrated" and "Intel" not in gpu:
            continue
        if "Advanced" in gpu:
            if "AMD" in gpu and "ATI" in gpu:
                brand = "AMD ATI"
            elif "AMD" in gpu:
                brand = "AMD"
            elif "ATI" in gpu:
                brand = "ATi"
            else:
                brand = ""
            gpu = re.sub(r"\[AMD/ATI\] |\[AMD\] |OEM |Advanced Micro Devices, Inc\. ", "", gpu)
            gpu = re.sub(r".*\[", "", gpu)
            gpu = gpu.replace("]", "")
            gpu = util.trim(f"{brand} {gpu}")
        elif "NVIDIA" in gpu:
            gpu = re.sub(r".*\[", "", gpu).replace("]", "")
            gpu = f"NVIDIA {util.trim(gpu)}"
        elif "Intel" in gpu:
            gpu = re.sub(r".*Intel", "Intel", gpu)
            gpu = gpu.replace("(R)", "").replace("Corporation", "")
            gpu = re.sub(r" \(.*", "", gpu)
            gpu = gpu.replace("Integrated Graphics Controller", "")
            gpu = re.sub(r".*Xeon.*", "Intel HD Graphics", gpu)
            if not util.trim(gpu):
                gpu = "Intel Integrated Graphics"
        elif "MCST" in gpu:
            gpu = re.sub(r".*MCST.*MGA2.*", "MCST MGA2", gpu)
        elif "VirtualBox" in gpu:
            gpu = "VirtualBox Graphics Adapter"
        else:
            continue
        if opts.gpu_brand == "off":
            for brand in ("AMD ", "NVIDIA ", "Intel "):
                gpu = gpu.replace(brand, "", 1)
        results.append(("", util.trim(gpu)))
    return results


# ---------------------------------------------------------------------------
# memory
# ---------------------------------------------------------------------------

def _memory_macos() -> tuple[int, int]:
    """Return (used MiB, total MiB): app + wired + compressed, as Activity Monitor counts it."""
    pagesize = _sysctl_int("hw.pagesize")
    total_mib = _sysctl_int("hw.memsize") // 1024 // 1024
    app_pages = _sysctl_int("vm.page_pageable_internal_count") - _sysctl_int("vm.page_purgeable_count")
    vm_stat = util.run(["vm_stat"]) or ""
    wired = re.search(r"Pages wired down:\s*(\d+)", vm_stat)
    compressed = re.search(r"Pages occupied by compressor:\s*(\d+)", vm_stat)
    pages = app_pages + (int(wired.group(1)) if wired else 0) + (int(compressed.group(1)) if compressed else 0)
    used_mib = pages * pagesize // 1024 // 1024
    return used_mib, total_mib


def _memory_proc_meminfo() -> tuple[int, int]:
    """Return (used MiB, total MiB) from /proc/meminfo."""
    mem_total = 0
    mem_used = 0
    mem_avail: int | None = None
    text = util.read_text("/proc/meminfo") or ""
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        try:
            value = int(rest.strip().split()[0])
        except (ValueError, IndexError):
            continue
        if key == "MemTotal":
            mem_used += value
            mem_total = value
        elif key == "Shmem":
            mem_used += value
        elif key in ("MemFree", "Buffers", "Cached", "SReclaimable"):
            mem_used -= value
        elif key == "MemAvailable":
            mem_avail = value
    if mem_avail is not None:
        used_mib = (mem_total - mem_avail) // 1024
    else:
        used_mib = mem_used // 1024
    return used_mib, mem_total // 1024


def get_memory(host: Host, opts: Options) -> str:
    if host.os in ("Mac OS X", "macOS"):
        used_mib, total_mib = _memory_macos()
    elif host.os in ("Linux", "Windows"):
        used_mib, total_mib = _memory_proc_meminfo()
    else:
        return ""
    if not total_mib:
        return ""

    percent = ""
    if opts.memory_percent == "on" and total_mib:
        percent = f" ({used_mib * 100 // total_mib}%)"

    label = "MiB"
    if opts.memory_unit == "gib":
        used = f"{used_mib / 1024:.2f}"
        total = f"{total_mib / 1024:.2f}"
        label = "GiB"
    elif opts.memory_unit == "kib":
        used = str(used_mib * 1024)
        total = str(total_mib * 1024)
        label = "KiB"
    else:
        used = str(used_mib)
        total = str(total_mib)

    memory = f"{used}{label} / {total}{label}{percent}"
    if opts.memory_display in ("bar", "infobar", "barinfo"):
        from neoinfo.display import render_bar

        bar = render_bar(used_mib, total_mib, opts)
        if opts.memory_display == "bar":
            memory = bar
        elif opts.memory_display == "infobar":
            memory = f"{memory} {bar}"
        else:
            memory = f"{bar} {memory}"
    return memory


# ---------------------------------------------------------------------------
# song
# ---------------------------------------------------------------------------

_MPRIS_PLAYERS = {
    "gnome-music": "GnomeMusic",
    "lollypop": "Lollypop",
    "clementine": "clementine",
    "cmus": "cmus",
    "juk": "juk",
    "bluemindo": "Bluemindo",
    "guayadeque": "guayadeque",
    "yarock": "yarock",
    "deepin-music": "DeepinMusic",
    "tomahawk": "tomahawk",
    "elisa": "elisa",
    "sayonara": "sayonara",
    "audacious": "audacious",
    "vlc": "vlc",
    "gmusicbrowser": "gmusicbrowser",
    "pragha": "pragha",
    "amarok": "amarok",
    "dragon": "dragonplayer",
    "smplayer": "smplayer",
    "rhythmbox": "rhythmbox",
    "strawberry": "strawberry",
    "gogglesmm": "gogglesmm",
    "xnoise": "xnoise",
    "tauonmb": "tauon",
    "olivia": "olivia",
    "exaile": "exaile",
    "netease-cloud-music": "netease-cloud-music",
    "plasma-browser-integration": "plasma-browser-integration",
    "io.elementary.music": "Music",
    "mellowplayer": "MellowPlayer3",
    "spotify": "spotify",
}

_PLAYER_NAMES = (
    "amarok", "audacious", "banshee", "bluemindo", "clementine", "cmus",
    "deadbeef", "deepin-music", "dragon", "elisa", "exaile", "gnome-music",
    "gmusicbrowser", "gogglesmm", "guayadeque", "io.elementary.music",
    "iTunes", "Music", "juk", "lollypop", "MellowPlayer", "mocp", "mopidy",
    "mpd", "muine", "netease-cloud-music", "olivia",
    "plasma-browser-integration", "playerctl", "pogo", "pragha", "qmmp",
    "quodlibet", "rhythmbox", "sayonara", "smplayer", "spotify", "Spotify",
    "strawberry", "tauonmb", "tomahawk", "vlc", "xmms2d", "xnoise", "yarock",
)


def _mpris_song(bus_name: str) -> tuple[str, str, str]:
    out = util.run(
        [
            "dbus-send", "--print-reply",
            f"--dest=org.mpris.MediaPlayer2.{bus_name}",
            "/org/mpris/MediaPlayer2",
            "org.freedesktop.DBus.Properties.Get",
            "string:org.mpris.MediaPlayer2.Player",
            "string:Metadata",
        ]
    ) or ""
    artist = album = title = ""
    for chunk in out.split(" entry"):
        m = re.search(r'"xesam:artist"\s+.*?string\s+"([^"]*)"', chunk, re.S)
        if m:
            artist = m.group(1)
        m = re.search(r'"xesam:album"\s+.*?string\s+"([^"]*)"', chunk, re.S)
        if m:
            album = m.group(1)
        m = re.search(r'"xesam:title"\s+.*?string\s+"([^"]*)"', chunk, re.S)
        if m:
            title = m.group(1)
    return artist, album, title


def get_song(host: Host, opts: Options) -> list[tuple[str, str]] | str:
    player = ""
    for _, comm in _ps_commands():
        base = comm.split("/")[-1]
        for known in _PLAYER_NAMES:
            if base == known or base.lower() == known.lower():
                player = base
                break
        if player:
            break
    if opts.music_player and opts.music_player != "auto":
        player = opts.music_player
    if not player:
        if util.which("mpc"):
            out = util.run(["mpc", "-f", "%artist%\n%album%\n%title%", "current"] + list(opts.mpc_args)) or ""
            parts = (out.splitlines() + ["", "", ""])[:3]
            artist, album, title = (util.trim(p) for p in parts)
        else:
            return ""
    else:
        short = player.split("/")[-1]
        low = short.lower()
        artist = album = title = ""
        if low.startswith("mocp"):
            out = util.run(["mocp", "-Q", "%artist \n%album \n%song"]) or ""
            artist, album, title = (out.split("\n") + ["", "", ""])[:3]
        elif low.startswith("deadbeef"):
            out = util.run(["deadbeef", "--nowplaying-tf", "%artist% \\n%album% \\n%title%"]) or ""
            artist, album, title = (out.replace("\\n", "\n").split("\n") + ["", "", ""])[:3]
        elif low.startswith("qmmp"):
            out = util.run(["qmmp", "--nowplaying", "%p \\n%a \\n%t"]) or ""
            artist, album, title = (out.replace("\\n", "\n").split("\n") + ["", "", ""])[:3]
        elif low.startswith("banshee"):
            out = util.run(["banshee", "--query-artist", "--query-album", "--query-title"]) or ""
            for line in out.splitlines():
                if line.startswith("artist"):
                    artist = line.split(":", 1)[-1]
                elif line.startswith("album"):
                    album = line.split(":", 1)[-1]
                elif line.startswith("title"):
                    title = line.split(":", 1)[-1]
        elif low.startswith("playerctl"):
            out = util.run(["playerctl", "metadata", "--format", "{{ artist }} \\n{{ album }} \\n{{ title }}"]) or ""
            artist, album, title = (out.replace("\\n", "\n").split("\n") + ["", "", ""])[:3]
        elif low.startswith("mpd") or low.startswith("mopidy"):
            out = util.run(["mpc", "-f", "%artist% \\n%album% \\n%title%", "current"] + list(opts.mpc_args)) or ""
            artist, album, title = (out.replace("\\n", "\n").split("\n") + ["", "", ""])[:3]
        elif low.startswith("xmms2d"):
            out = util.run(["xmms2", "current", "-f", "${artist}\n${album}\n${title}"]) or ""
            artist, album, title = (out.split("\n") + ["", "", ""])[:3]
        elif low in _MPRIS_PLAYERS:
            artist, album, title = _mpris_song(_MPRIS_PLAYERS[low])
        else:
            if util.which("mpc"):
                out = util.run(["mpc", "-f", "%artist% \\n%album% \\n%title%", "current"]) or ""
                artist, album, title = (out.replace("\\n", "\n").split("\n") + ["", "", ""])[:3]
            else:
                return ""
        artist, album, title = util.trim(artist), util.trim(album), util.trim(title)
    artist = artist or "Unknown Artist"
    album = album or "Unknown Album"
    title = title or "Unknown Song"
    if opts.song_shorthand == "on":
        return [("", artist), ("", album), ("", title)]
    song = opts.song_format.replace("%artist%", artist)
    song = song.replace("%album%", album).replace("%title%", title)
    return song


# ---------------------------------------------------------------------------
# resolution
# ---------------------------------------------------------------------------

def _resolution_macos(opts: Options) -> str:
    """Physical pixels of each display, e.g. "6016x3384, 2560x1440".

    system_profiler prints, per display:
        Resolution: 6016 x 3384            (older macOS: "... @ 60Hz")
        UI Looks like: 3008 x 1692 @ 30.00Hz
    """
    displays: list[list[str]] = []  # [[pixels, refresh rate], ...]
    for line in _system_profiler().splitlines():
        m = re.search(r"^\s*Resolution:\s*(\d+)\s*x\s*(\d+)(?:.*?@\s*([\d.]+)\s*Hz)?", line)
        if m:
            displays.append([f"{m.group(1)}x{m.group(2)}", m.group(3) or ""])
            continue
        m = re.search(r"^\s*UI Looks like:.*@\s*([\d.]+)\s*Hz", line)
        if m and displays and not displays[-1][1]:
            displays[-1][1] = m.group(1)
    parts = []
    for pixels, rate in displays:
        rate = rate.rstrip("0").rstrip(".") if "." in rate else rate
        if opts.refresh_rate == "on" and rate and rate != "0":
            pixels = f"{pixels} @ {rate}Hz"
        parts.append(pixels)
    return ", ".join(parts)


def get_resolution(host: Host, opts: Options) -> str:
    resolution = ""
    if host.os in ("Mac OS X", "macOS"):
        return _resolution_macos(opts)
    if host.os in ("Linux", "BSD", "Solaris", "AIX", "IRIX"):
        if (
            util.which("xrandr")
            and util.env("DISPLAY")
            and not util.env("WAYLAND_DISPLAY")
        ):
            out = util.run(["xrandr", "--nograb", "--current"]) or ""
            if opts.refresh_rate == "on":
                parts = []
                for m in re.finditer(r"(\S+)\s+[0-9.]+\*", out):
                    rate = re.search(r"([0-9]+\.[0-9]+)\*", m.group(0))
                    parts.append(f"{m.group(1)} @ {rate.group(1) if rate else ''}Hz")
                resolution = ", ".join(parts)
            else:
                parts = []
                for line in out.splitlines():
                    if " connected" in line:
                        m = re.search(r"connected.*?(\d+x\d+)\+", line)
                        if m and "primary" not in line.split("connected")[0]:
                            parts.append(m.group(1))
                        elif m:
                            parts.insert(0, m.group(1))
                # drop the word primary if it leaked in
                resolution = ", ".join(p.replace("primary, ", "").replace("primary ", "") for p in parts)
                resolution = resolution.replace("*", "")
            resolution = resolution.rstrip(", ")
        elif (
            util.which("xwininfo")
            and util.env("DISPLAY")
            and not util.env("WAYLAND_DISPLAY")
        ):
            out = util.run(["xwininfo", "-root"]) or ""
            w = re.search(r"Width:\s*(\d+)", out)
            h = re.search(r"Height:\s*(\d+)", out)
            if w and h:
                resolution = f"{w.group(1)}x{h.group(1)}"
        elif (
            util.which("xdpyinfo")
            and util.env("DISPLAY")
            and not util.env("WAYLAND_DISPLAY")
        ):
            out = util.run(["xdpyinfo"]) or ""
            m = re.search(r"dimensions:\s*(\S+)", out)
            resolution = m.group(1) if m else ""
        else:
            parts = []
            for mode_path in sorted(_glob.glob("/sys/class/drm/*/modes")):
                text = util.read_text(mode_path) or ""
                first = text.split()[0] if text.split() else ""
                if first:
                    parts.append(first)
            if parts:
                resolution = ", ".join(parts)
    return resolution


# ---------------------------------------------------------------------------
# gtk theme / icons / font
# ---------------------------------------------------------------------------

def _get_style(host: Host, opts: Options, name: str, gsettings: str, xfconf: str, kde_key: str) -> str:
    gtk2_theme = gtk3_theme = kde_theme = ""
    if util.env("DISPLAY") or util.env("WAYLAND_DISPLAY"):
        de = get_de(host, opts)
        if opts.de_version == "on":
            de = de.split(" ")[0]
        if de.startswith(("KDE", "Plasma")):
            kde_dir = _kde_config_dir()
            path = os.path.join(kde_dir, "kdeglobals")
            if os.path.isfile(path):
                text = util.read_text(path) or ""
                m = re.search(rf"^{kde_key}=(.*)$", text, re.M)
                if m:
                    kde_theme = m.group(1)
                    if kde_key == "font":
                        bits = kde_theme.split(",")
                        kde_theme = f"{bits[0]} {bits[-1]} {bits[1] if len(bits) > 1 else ''}".strip()
                    kde_theme = f"{kde_theme} [{de}], "
        elif "Cinnamon" in de:
            if util.which("gsettings"):
                theme = util.trim_quotes(util.trim(util.run(["gsettings", "get", "org.cinnamon.desktop.interface", gsettings]) or ""))
                gtk3_theme = gtk2_theme = theme
        elif de.startswith(("Gnome", "Unity", "Budgie")):
            if util.which("gsettings"):
                theme = util.trim_quotes(util.trim(util.run(["gsettings", "get", "org.gnome.desktop.interface", gsettings]) or ""))
                gtk3_theme = gtk2_theme = theme
        elif de.startswith("Mate"):
            if util.which("gsettings"):
                theme = util.trim_quotes(util.trim(util.run(["gsettings", "get", "org.mate.interface", gsettings]) or ""))
                gtk3_theme = gtk2_theme = theme
        elif de.startswith("Xfce") and util.which("xfconf-query"):
            gtk2_theme = util.trim(util.run(["xfconf-query", "-c", "xsettings", "-p", xfconf]) or "")

        if not gtk2_theme:
            home = os.path.expanduser("~")
            searched = False
            gtkrc_files = []
            if util.env("GTK2_RC_FILES"):
                gtkrc_files = util.env("GTK2_RC_FILES").split(":")
                searched = True
            else:
                for candidate in (
                    os.path.join(home, ".gtkrc-2.0"),
                    "/etc/gtk-2.0/gtkrc",
                    "/usr/share/gtk-2.0/gtkrc",
                ):
                    if os.path.isfile(candidate):
                        gtkrc_files.append(candidate)
                        break
            for path in gtkrc_files:
                text = util.read_text(path) or ""
                for line in text.splitlines():
                    if line.startswith("#"):
                        continue
                    if name in line:
                        gtk2_theme = line.split(name, 1)[-1].lstrip("= ").strip()
                        break
                if gtk2_theme:
                    break

        if not gtk3_theme:
            home = os.path.expanduser("~")
            config_home = util.env("XDG_CONFIG_HOME", os.path.join(home, ".config"))
            for candidate in (
                os.path.join(config_home, "gtk-3.0/settings.ini"),
                "/etc/gtk-3.0/settings.ini",
                "/usr/share/gtk-3.0/settings.ini",
            ):
                if os.path.isfile(candidate):
                    text = util.read_text(candidate) or ""
                    for line in text.splitlines():
                        if line.startswith("#"):
                            continue
                        if name in line:
                            gtk3_theme = line.split(name, 1)[-1].lstrip("= ").strip()
                            break
                if gtk3_theme:
                    break
            if not gtk3_theme and util.which("gsettings"):
                gtk3_theme = util.trim_quotes(
                    util.trim(
                        util.run(["gsettings", "get", "org.gnome.desktop.interface", gsettings]) or ""
                    )
                )

        gtk2_theme = util.trim_quotes(util.trim(gtk2_theme))
        gtk3_theme = util.trim_quotes(util.trim(gtk3_theme))
        if opts.gtk2 == "off":
            gtk2_theme = ""
        if opts.gtk3 == "off":
            gtk3_theme = ""
        if gtk2_theme and gtk2_theme == gtk3_theme:
            gtk3_theme += " [GTK2/3]"
            gtk2_theme = ""
        elif gtk2_theme and gtk3_theme:
            gtk2_theme += " [GTK2], "
            gtk3_theme += " [GTK3] "
        else:
            if gtk2_theme:
                gtk2_theme += " [GTK2] "
            if gtk3_theme:
                gtk3_theme += " [GTK3] "
        theme = f"{kde_theme}{gtk2_theme}{gtk3_theme}".rstrip(", ")
        if opts.gtk_shorthand == "on":
            theme = re.sub(r" '\[GTK[0-9]\]'", "", theme)
            theme = theme.replace(" '[GTK2/3]'", "").replace(" '[KDE]'", "").replace(" '[Plasma]'", "")
        return util.trim(theme)
    return ""


def get_theme(host: Host, opts: Options) -> str:
    return _get_style(host, opts, "gtk-theme-name", "gtk-theme", "/Net/ThemeName", "Name")


def get_icons(host: Host, opts: Options) -> str:
    return _get_style(host, opts, "gtk-icon-theme-name", "icon-theme", "/Net/IconThemeName", "Theme")


def get_font(host: Host, opts: Options) -> str:
    return _get_style(host, opts, "gtk-font-name", "font-name", "/Gtk/FontName", "font")


# ---------------------------------------------------------------------------
# terminal / terminal font
# ---------------------------------------------------------------------------

def _ppid(pid: int) -> int | None:
    status = util.read_text(f"/proc/{pid}/status")
    if status:
        m = re.search(r"^PPid:\s*(\d+)", status, re.M)
        if m:
            return int(m.group(1))
        return None
    out = util.run(["ps", "-p", str(pid), "-o", "ppid="])
    if out and out.strip().isdigit():
        return int(out.strip())
    return None


def _process_name(pid: int) -> str:
    comm = util.read_text(f"/proc/{pid}/comm")
    if comm is not None:
        return comm.strip()
    out = util.run(["ps", "-p", str(pid), "-o", "comm="])
    return util.trim(out) if out else ""


# Processes that sit between neoinfo and the terminal: shells, screen and
# the launchers people use to run Python tools. Names ending in "sh"
# (bash, zsh, fish, ...) are skipped as well.
_PASS_THROUGH_PROCS = frozenset({
    "screen", "newgrp", "nu", "elvish", "xonsh", "ion", "env",
    "uv", "uvx", "pipx", "poetry", "pdm", "hatch", "rye",
})

# Variables a terminal exports to its shells. Used when the process tree
# doesn't reach the terminal (SSH, tmux, sandboxes).
_TERM_ENV_VARS = (
    ("VIVIDO_WINDOW_ID", "vivido"),
    ("KITTY_WINDOW_ID", "kitty"),
    ("KITTY_PID", "kitty"),
    ("ALACRITTY_WINDOW_ID", "alacritty"),
    ("ALACRITTY_SOCKET", "alacritty"),
    ("GHOSTTY_RESOURCES_DIR", "ghostty"),
    ("WEZTERM_PANE", "WezTerm"),
    ("KONSOLE_VERSION", "konsole"),
    ("TILIX_ID", "tilix"),
    ("TERMINATOR_UUID", "terminator"),
    ("GNOME_TERMINAL_SCREEN", "gnome-terminal"),
    ("TERMINOLOGY", "terminology"),
    ("XTERM_VERSION", "xterm"),
    ("MLTERM", "mlterm"),
)

# $TERM values that name one terminal. SSH always forwards $TERM, so this
# still works on the remote side. Matches "<value>" or "<value>-<suffix>".
_TERM_BY_TERMINFO = (
    ("xterm-kitty", "kitty"),
    ("xterm-ghostty", "ghostty"),
    ("xterm-termite", "termite"),
    ("alacritty", "alacritty"),
    ("vivido", "vivido"),
    ("foot", "foot"),
    ("wezterm", "WezTerm"),
    ("rxvt-unicode", "urxvt"),
    ("st", "st"),
    ("konsole", "konsole"),
    ("terminology", "terminology"),
    ("mlterm", "mlterm"),
    ("contour", "contour"),
    ("rio", "rio"),
    ("mintty", "mintty"),
)


def _term_from_env() -> str:
    for var, name in _TERM_ENV_VARS:
        if util.env(var):
            return name
    # iTerm2 sets LC_TERMINAL, and ssh forwards LC_* by default.
    lc_terminal = util.env("LC_TERMINAL")
    if lc_terminal:
        return lc_terminal
    term_var = util.env("TERM")
    for value, name in _TERM_BY_TERMINFO:
        if term_var == value or term_var.startswith(value + "-"):
            return name
    return ""


def _term_from_process_tree(host: Host) -> tuple[str, bool]:
    """Walk up from neoinfo's parent to the first terminal-like process.

    Returns the terminal name ("" if none) and whether the walk ended on a
    bare console (a `login` or `init` with no terminal above it).
    """
    shell_name = os.path.basename(util.env("SHELL", ""))
    saw_login = False
    try:
        parent = _ppid(os.getpid())
    except (ValueError, OSError):
        parent = None
    while parent:
        raw = _process_name(parent)
        # macOS `ps` gives full paths ("/usr/bin/login") and marks login
        # shells with a dash ("-zsh").
        name = os.path.basename(raw.replace(" ", "")).lstrip("-")
        if (
            (shell_name and name.startswith(shell_name))
            or name.endswith("sh")
            or name.startswith("su")
            or name in _PASS_THROUGH_PROCS
        ):
            pass
        elif name.startswith("login") or "Login" in name:
            # On macOS the terminal starts the shell through login, so keep
            # going: the terminal is login's parent.
            saw_login = True
        elif name in ("init", "(init)"):
            return "", True
        elif name in ("ruby", "1", "systemd") or name.startswith(
            ("tmux", "sshd", "python", "kdeinit", "launchd", "bwrap")
        ) or ("USER" in name and "PID" in name):
            break
        elif name == "gnome-terminal-":
            return "gnome-terminal", False
        elif name == "urxvtd":
            return "urxvt", False
        elif "nvim" in name:
            return "Neovim Terminal", False
        elif "NeoVimServer" in name:
            return "VimR Terminal", False
        else:
            term = name
            if host.os == "Linux":
                exe = f"/proc/{parent}/exe"
                try:
                    real = os.path.realpath(exe)
                except OSError:
                    real = exe
                # realpath hands back the link itself when it can't read it.
                if real != exe:
                    term = os.path.basename(real)
            if term.startswith(".") and term.endswith("-wrapped"):
                term = term[1: -len("-wrapped")]
            if term:
                return term, False
        parent = _ppid(parent)
    return "", saw_login


def get_term(host: Host, opts: Options) -> str:
    term = ""
    term_program = util.env("TERM_PROGRAM")
    if term_program == "iTerm.app":
        term = "iTerm2"
    elif term_program == "Terminal.app":
        term = "Apple Terminal"
    elif term_program == "Hyper":
        term = "HyperTerm"
    elif term_program:
        term = term_program.replace(".app", "")
    if util.env("TERM") in ("tw52", "tw100"):
        term = "TosWin2"
    if util.env("WT_SESSION"):
        term = "Windows Terminal"
    if term:
        return term

    term, on_console = _term_from_process_tree(host)
    if term:
        return term
    term = _term_from_env()
    if term:
        return term

    # Nothing names the terminal. Show the tty as a last resort: an SSH
    # session from an unidentifiable client, or a bare console login.
    if util.env("SSH_CONNECTION") and util.env("SSH_TTY"):
        return util.env("SSH_TTY")
    if on_console:
        out = util.run(["tty"])
        return util.trim(out) if out else ""
    return ""


# ---------------------------------------------------------------------------
# terminal font: kitty, Ghostty, Alacritty, Vivido
#
# Terminals don't expose their font in any common way, so each one gets an
# entry in _TERM_FONTS and _detect_term_font() tries, in order:
#   1. asking the terminal: its CLI prints the effective config, with
#      includes, imports and live changes applied;
#   2. reading its config file(s);
#   3. the terminal's built-in default font.
# ---------------------------------------------------------------------------

def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _dig(data: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _kitty_font_family(spec: str) -> str:
    """Name from a kitty font_family value.

    kitty 0.36+ writes `family="JetBrainsMono Nerd Font Mono" style=...` or
    `postscript_name=...`; older configs use a bare name.
    """
    spec = util.trim(spec)
    for key in ("family", "postscript_name"):
        m = re.search(rf"""\b{key}\s*=\s*(?:"([^"]*)"|'([^']*)'|(\S+))""", spec)
        if m:
            return next(g for g in m.groups() if g is not None)
    return spec


def _kitty_conf_font(paths: list[str]) -> str:
    # The last font_family line wins.
    spec = ""
    for path in paths:
        for line in (util.read_text(path) or "").splitlines():
            m = re.match(r"\s*font_family\s+(.+)", line)
            if m:
                spec = m.group(1)
    return _kitty_font_family(spec) if spec else ""


def _ghostty_font(text: str) -> str:
    """Primary font from Ghostty `font-family = X` lines (config or +show-config).

    Repeated lines build a fallback list; an empty value clears the list.
    """
    families: list[str] = []
    for line in text.splitlines():
        m = re.match(r"\s*font-family\s*=(.*)$", line)
        if m:
            value = _unquote(m.group(1))
            families = [*families, value] if value else []
    return families[0] if families else ""


def _ghostty_conf_font(paths: list[str]) -> str:
    # Later files override earlier ones, so read them as one config.
    return _ghostty_font("\n".join(util.read_text(path) or "" for path in paths))


def _alacritty_json_font(text: str) -> str:
    """font.normal.family from `alacritty msg get-config` (Vivido: `vivido msg get-config`)."""
    try:
        family = _dig(json.loads(text), "font", "normal", "family")
    except ValueError:
        return ""
    return family if isinstance(family, str) else ""


def _alacritty_toml_font(path: str, depth: int = 0) -> str:
    """font.normal.family from an Alacritty-style TOML file.

    Imported files load first and the file itself overrides them.
    """
    try:
        data = tomllib.loads(util.read_text(path) or "")
    except tomllib.TOMLDecodeError:
        return ""
    family = ""
    imports = _dig(data, "general", "import") or data.get("import") or []
    if isinstance(imports, list) and depth < 5:
        for item in imports:
            if isinstance(item, str):
                # join() keeps an absolute import as is.
                imported = os.path.join(os.path.dirname(path), os.path.expanduser(item))
                family = _alacritty_toml_font(imported, depth + 1) or family
    own = _dig(data, "font", "normal", "family")
    return own if isinstance(own, str) and own else family


def _alacritty_yaml_font(text: str) -> str:
    """font.normal.family from a pre-0.13 alacritty.yml."""
    in_normal = False
    for line in text.splitlines():
        if re.match(r"\s*normal\s*:", line):
            in_normal = True
        elif in_normal and "family" in line and not line.strip().startswith("#"):
            return line.split("family:", 1)[-1].split("#")[0].replace('"', "").strip()
        elif in_normal and re.match(r"\S", line):
            break
    return ""


def _alacritty_conf_font(paths: list[str]) -> str:
    # Alacritty loads only the first config file it finds.
    for path in paths:
        text = util.read_text(path)
        if text is None:
            continue
        if path.endswith((".yml", ".yaml")):
            return _alacritty_yaml_font(text)
        return _alacritty_toml_font(path)
    return ""


def _alacritty_paths(name: str, config_home: str, home: str) -> list[str]:
    """Alacritty's config search order. Vivido, a fork, uses the same with its own name."""
    paths = [
        os.path.join(config_home, name, f"{name}.toml"),
        os.path.join(config_home, f"{name}.toml"),
        os.path.join(home, ".config", name, f"{name}.toml"),
        os.path.join(home, f".{name}.toml"),
        f"/etc/{name}/{name}.toml",
    ]
    if name == "alacritty":
        paths += [
            os.path.join(config_home, "alacritty", "alacritty.yml"),
            os.path.join(home, ".alacritty.yml"),
        ]
    return paths


def _ghostty_paths(config_home: str, home: str) -> list[str]:
    """Ghostty's config files in load order. The second directory only exists on macOS."""
    dirs = [
        os.path.join(config_home, "ghostty"),
        os.path.join(home, "Library", "Application Support", "com.mitchellh.ghostty"),
    ]
    return [os.path.join(d, name) for d in dirs for name in ("config", "config.ghostty")]


@dataclass(frozen=True)
class _TermFont:
    binary: str  # CLI name, also the executable inside the macOS app
    app: str  # macOS app bundle
    query: tuple[str, ...]  # CLI arguments that print the effective config
    parse_query: Callable[[str], str]
    config_paths: Callable[[str, str], list[str]]  # (config_home, home) -> files
    parse_config: Callable[[list[str]], str]
    defaults: dict[str, str]  # built-in font by host.os; "" = any other OS


_TERM_FONTS = {
    "kitty": _TermFont(
        binary="kitty",
        app="kitty.app",
        query=("+runpy", "from kitty.cli import *; print(create_default_opts().font_family)"),
        parse_query=_kitty_font_family,
        config_paths=lambda config_home, home: [os.path.join(
            util.env("KITTY_CONFIG_DIRECTORY") or os.path.join(config_home, "kitty"), "kitty.conf"
        )],
        parse_config=_kitty_conf_font,
        defaults={"": "monospace"},
    ),
    "ghostty": _TermFont(
        binary="ghostty",
        app="Ghostty.app",
        query=("+show-config",),
        parse_query=_ghostty_font,
        config_paths=_ghostty_paths,
        parse_config=_ghostty_conf_font,
        defaults={"": "JetBrains Mono"},  # embedded in Ghostty
    ),
    "alacritty": _TermFont(
        binary="alacritty",
        app="Alacritty.app",
        query=("msg", "get-config"),
        parse_query=_alacritty_json_font,
        config_paths=lambda config_home, home: _alacritty_paths("alacritty", config_home, home),
        parse_config=_alacritty_conf_font,
        defaults={"macOS": "Menlo", "Windows": "Consolas", "": "monospace"},
    ),
    "vivido": _TermFont(
        binary="vivido",
        app="Vivido.app",
        query=("msg", "get-config"),
        parse_query=_alacritty_json_font,
        config_paths=lambda config_home, home: _alacritty_paths("vivido", config_home, home),
        parse_config=_alacritty_conf_font,
        defaults={"macOS": "Menlo", "Windows": "Consolas", "": "monospace"},
    ),
}


def _term_binary(source: _TermFont) -> str:
    found = util.which(source.binary)
    if found:
        return found
    for apps in ("/Applications", os.path.expanduser("~/Applications")):
        path = os.path.join(apps, source.app, "Contents", "MacOS", source.binary)
        if os.path.isfile(path):
            return path
    return ""


def _detect_term_font(host: Host, source: _TermFont, config_home: str, home: str) -> str:
    binary = _term_binary(source)
    if binary:
        out = util.run([binary, *source.query], timeout=3)
        font = source.parse_query(out) if out else ""
        if font:
            return util.trim(font)
    font = source.parse_config(source.config_paths(config_home, home))
    if font:
        return util.trim(font)
    return source.defaults.get(host.os, source.defaults.get("", ""))


def get_term_font(host: Host, opts: Options, term: str = "") -> str:
    if not term:
        term = get_term(host, opts)
    home = os.path.expanduser("~")
    config_home = util.env("XDG_CONFIG_HOME", os.path.join(home, ".config"))
    source = next((s for name, s in _TERM_FONTS.items() if term.lower().startswith(name)), None)
    if source:
        # Over SSH the terminal, and its font, are on the other machine.
        if util.env("SSH_CONNECTION"):
            return ""
        return _detect_term_font(host, source, config_home, home)
    font = ""
    if term == "Apple_Terminal":
        out = util.run(
            ["osascript", "-e", 'tell application "Terminal" to font name of window frontmost']
        )
        font = util.trim(out) if out else ""
    elif term == "iTerm2":
        font = ""  # requires macOS plist inspection; not portable
    elif term.startswith("deepin-terminal"):
        text = util.read_text(os.path.join(config_home, "deepin/deepin-terminal/config.conf")) or ""
        name = size = ""
        for line in text.splitlines():
            if re.match(r"\s*font\s*=", line):
                name = line.split("=", 1)[-1].strip()
            elif re.match(r"\s*font_size", line):
                size = line.split("=", 1)[-1].strip()
        font = util.trim(f"{name} {size}")
    elif term.startswith("Hyper"):
        text = util.read_text(os.path.join(home, ".hyper.js")) or ""
        m = re.search(r"fontFamily\s*:\s*['\"]?([^'\",]+)", text)
        font = util.trim_quotes(util.trim(m.group(1))) if m else ""
    elif term.startswith("lxterminal"):
        text = util.read_text(os.path.join(config_home, "lxterminal/lxterminal.conf")) or ""
        for line in text.splitlines():
            if line.startswith("fontname="):
                font = line.split("=", 1)[-1].strip()
                break
    elif term == "qterminal":
        text = util.read_text(os.path.join(config_home, "qterminal.org/qterminal.ini")) or ""
        family = size = ""
        for line in text.splitlines():
            if re.match(r"\s*fontFamily\s*=", line):
                family = line.split("=", 1)[-1].strip()
            elif re.match(r"\s*fontSize\s*=", line):
                size = line.split("=", 1)[-1].strip()
        font = util.trim(f"{family} {size}")
    elif term.startswith("sakura"):
        text = util.read_text(os.path.join(config_home, "sakura/sakura.conf")) or ""
        for line in text.splitlines():
            if line.startswith("font="):
                font = line.split("=", 1)[-1].strip()
                break
    elif term == "st":
        parent = _ppid(os.getpid())
        out = util.run(["ps", "-o", "command=", "-p", str(parent or "")]) or ""
        if "-f" in out:
            font = out.split("-f", 1)[-1].split("-")[0].strip()
        else:
            binary = None
            if parent and os.path.islink(f"/proc/{parent}/exe"):
                binary = f"/proc/{parent}/exe"
            elif util.which("st"):
                binary = util.which("st")
            if binary:
                out = util.run(["strings", binary]) or ""
                for line in out.splitlines():
                    if "font" in line and "font2" not in line:
                        font = line.strip()
                        break
        font = font.replace("xft:", "").split("=")[-1].split(":")[0]
    elif term == "terminology":
        out = util.run(
            ["strings", os.path.join(config_home, "terminology/config/standard/base.cfg")]
        ) or ""
        prev = ""
        for line in out.splitlines():
            if line.strip() == "font.name":
                font = prev
                break
            prev = line.strip()
        font = font.replace(".pcf", "").split(":")[0]
    elif term == "termite":
        candidates = [
            os.path.join(config_home, "termite/config"),
            "/etc/xdg/termite/config",
        ]
        for path in candidates:
            text = util.read_text(path)
            if not text:
                continue
            in_options = False
            for line in text.splitlines():
                if line.strip() == "[options]":
                    in_options = True
                elif in_options and re.match(r"\s*font\s*=", line):
                    font = line.split("=", 1)[-1].strip()
                    break
            if font:
                break
    elif term in ("urxvt", "urxvtd", "rxvt-unicode", "xterm"):
        out = util.run(["xrdb", "-query"]) or ""
        for line in out.splitlines():
            short = "urxvt" if term.startswith("u") else term
            if re.match(rf"^{re.escape(short)}\*.*font:|^\\*font:", line, re.I):
                font = line.split("font:", 1)[-1].strip()
                break
        if not font and term == "xterm":
            for line in out.splitlines():
                if line.startswith("XTerm.vt100.faceName"):
                    font = line.split("faceName:", 1)[-1].strip()
                    break
        if font and not font.startswith("-") and not font.startswith("xft:"):
            font = f"xft:{font}"
        if font.startswith("xft:"):
            font = font[len("xft:"):].split(":")[0]
        elif font.startswith("-"):
            bits = font.split("-")
            font = bits[2] if len(bits) > 2 else font
    elif term == "xfce4-terminal":
        text = util.read_text(os.path.join(config_home, "xfce4/terminal/terminalrc")) or ""
        for line in text.splitlines():
            if line.startswith("FontName"):
                font = line.split("=", 1)[-1].strip()
            elif line.strip() == "FontUseSystem=TRUE":
                font = "FontUseSystem=TRUE"
        if font == "FontUseSystem=TRUE" and util.which("gsettings"):
            font = util.trim_quotes(util.trim(
                util.run(["gsettings", "get", "org.gnome.desktop.interface", "monospace-font-name"]) or ""
            ))
        font = util.trim_quotes(font)
        if not font:
            font = "Monospace 12"
    elif term.startswith("pantheon") and util.which("gsettings"):
        font = util.trim_quotes(util.trim(
            util.run(["gsettings", "get", "org.pantheon.terminal.settings", "font"]) or ""
        ))
        if not font.strip("'"):
            font = util.trim_quotes(util.trim(
                util.run(["gsettings", "get", "org.gnome.desktop.interface", "monospace-font-name"]) or ""
            ))
    elif term == "mintty":
        text = util.read_text(os.path.join(home, ".minttyrc")) or ""
        for line in text.splitlines():
            if re.match(r"\s*Font\s*=", line) and not line.strip().startswith(("(", "#")):
                font = line.split("=", 1)[-1].strip()
                break
    return util.trim(font)


# ---------------------------------------------------------------------------
# disk
# ---------------------------------------------------------------------------

def get_disk(host: Host, opts: Options) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for target in opts.disk_show:
        try:
            usage = shutil.disk_usage(target)
        except OSError:
            continue
        total, used = usage.total, usage.used
        percent = used * 100 // total if total else 0
        text = f"{util.human_size(used)} / {util.human_size(total)}"
        if opts.disk_percent != "off":
            text += f" ({percent}%)"
        if opts.disk_display in ("bar", "infobar", "barinfo"):
            from neoinfo.display import render_bar

            bar = render_bar(percent, 100, opts)
            if opts.disk_display == "bar":
                text = bar
            elif opts.disk_display == "infobar":
                text = f"{text} {bar}"
            else:
                text = f"{bar} {text}"
        if opts.disk_subtitle == "name":
            sub = f" ({os.path.basename(os.path.realpath(target)) or target})"
        elif opts.disk_subtitle == "dir":
            base = os.path.basename(target.rstrip("/")) or target
            sub = f" ({base})"
        elif opts.disk_subtitle == "none":
            sub = ""
        else:
            sub = f" ({target})"
        results.append((sub, text))
    return results


# ---------------------------------------------------------------------------
# battery
# ---------------------------------------------------------------------------

def get_battery(host: Host, opts: Options) -> list[tuple[str, str]]:
    from neoinfo.display import render_bar

    results: list[tuple[str, str]] = []
    if host.os == "Linux":
        paths = sorted(
            _glob.glob("/sys/class/power_supply/BAT*")
            + _glob.glob("/sys/class/power_supply/axp288_fuel_gauge*")
            + _glob.glob("/sys/class/power_supply/CMB*")
        )
        for bat in paths:
            capacity = util.read_line(os.path.join(bat, "capacity"))
            status = util.read_line(os.path.join(bat, "status"))
            if not capacity:
                continue
            battery = f"{capacity}% [{status}]"
            if opts.battery_display in ("bar", "infobar", "barinfo"):
                try:
                    bar = render_bar(int(capacity), 100, opts)
                except ValueError:
                    bar = ""
                if opts.battery_display == "bar":
                    battery = bar
                elif opts.battery_display == "infobar":
                    battery = f"{battery} {bar}"
                else:
                    battery = f"{bar} {battery}"
            suffix = "" if "axp288_fuel_gauge" in bat else bat[-1:]
            results.append((suffix, battery))
    return results


# ---------------------------------------------------------------------------
# ip / users / locale / gpu driver
# ---------------------------------------------------------------------------

def get_local_ip(host: Host, opts: Options) -> list[tuple[str, str]] | str:
    ifaces = list(opts.local_ip_interface)
    if ifaces == ["auto"]:
        for argv in (["ip", "route", "get", "1"], ["ip", "route", "get", "1.1.1.1"]):
            if util.which("ip"):
                out = util.run(argv) or ""
                m = re.search(r"\bsrc\s+(\S+)", out)
                if m:
                    return m.group(1).split("/")[0].split()[0]
        if util.which("ifconfig"):
            out = util.run(["ifconfig", "-a"]) or ""
            m = re.search(r"broadcast\s+(\S+)", out)
            if not m:
                m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out)
            if m:
                return m.group(1)
        # Last resort: UDP socket trick (no traffic sent).
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2)
            sock.connect(("8.8.8.8", 80))
            addr = sock.getsockname()[0]
            sock.close()
            if addr and not addr.startswith("127."):
                return addr
        except OSError:
            pass
        return ""
    results: list[tuple[str, str]] = []
    for iface in ifaces:
        ip = ""
        if util.which("ip"):
            out = util.run(["ip", "addr", "show", iface]) or ""
            m = re.search(r"\binet\s+(\S+)", out)
            if m:
                ip = m.group(1).split("/")[0]
        if not ip and util.which("ifconfig"):
            out = util.run(["ifconfig", iface]) or ""
            m = re.search(r"broadcast\s+(\S+)", out)
            if m:
                ip = m.group(1)
        if ip:
            results.append((iface, ip))
    return results


def get_public_ip(host: Host, opts: Options) -> str:
    import urllib.request

    if opts.public_ip_host:
        try:
            with urllib.request.urlopen(
                opts.public_ip_host, timeout=opts.public_ip_timeout
            ) as response:
                return util.trim(response.read().decode("utf-8", "replace"))
        except Exception:
            pass
    else:
        if util.which("dig"):
            out = util.run(
                ["dig", "+time=1", "+tries=1", "+short",
                 "myip.opendns.com", "@resolver1.opendns.com"]
            ) or ""
            if out and not out.startswith(";"):
                return util.trim(out)
        if util.which("drill"):
            out = util.run(
                ["drill", "myip.opendns.com", "@resolver1.opendns.com"]
            ) or ""
            m = re.search(r"^myip\..*\sIN\s+(\S+)", out, re.M)
            if m:
                return m.group(1)
    if util.which("curl"):
        out = util.run(
            ["curl", "-L", "--max-time", str(opts.public_ip_timeout),
             "-w", "\n", opts.public_ip_host or "http://ident.me"]
        )
        if out:
            return util.trim(out)
    if util.which("wget"):
        out = util.run(
            ["wget", "-T", str(opts.public_ip_timeout), "-qO-",
             opts.public_ip_host or "http://ident.me"]
        )
        if out:
            return util.trim(out)
    return ""


def get_users(host: Host, opts: Options) -> str:
    out = util.run(["who"]) or ""
    seen: list[str] = []
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[0] not in seen:
            seen.append(parts[0])
    return ", ".join(seen)


def get_locale(host: Host, opts: Options) -> str:
    return util.env("LANG", "C")


def get_gpu_driver(host: Host, opts: Options) -> str:
    if host.os == "Linux":
        out = util.run(["lspci", "-nnk"], timeout=15) or ""
        driver = ""
        lines = out.splitlines()
        for i, line in enumerate(lines):
            if re.search(r"Display|3D|VGA", line):
                for follow in lines[i + 1: i + 3]:
                    m = re.search(r":\s*(.+)$", follow)
                    if m and "driver" in follow.lower():
                        driver = m.group(1)
                        break
                    elif m and not driver:
                        driver = m.group(1)
                if driver:
                    break
        driver = util.trim(driver.rstrip(","))
        if "nvidia" in driver.lower():
            text = util.read_text("/proc/driver/nvidia/version") or ""
            m = re.search(r"Module\s+(\S+)", text)
            if m:
                rest = text[m.end():].split()
                driver = f"NVIDIA {rest[0] if rest else ''}".strip()
        return driver
    return ""


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

def collect(
    name: str, host: Host, opts: Options, cache: dict
) -> str | list[tuple[str, str]]:
    """Run collector `name`, memoizing display-independent parts."""
    if name == "title":
        user, hostname = get_title(host, opts)
        return f"{user}@{hostname}"
    if name == "distro":
        return host.distro
    if name == "model":
        return get_model(host, opts)
    if name == "kernel":
        return get_kernel(host, opts)
    if name == "uptime":
        return get_uptime(host, opts)
    if name == "packages":
        return get_packages(host, opts)
    if name == "shell":
        return get_shell(host, opts)
    if name == "resolution":
        return get_resolution(host, opts)
    if name == "de":
        wm = cache.get("wm")
        if wm is None:
            wm = get_wm(host, opts)
            cache["wm"] = wm
        return get_de(host, opts, wm)
    if name == "wm":
        wm = cache.get("wm")
        if wm is None:
            wm = get_wm(host, opts)
            cache["wm"] = wm
        return wm
    if name == "wm_theme":
        wm = cache.get("wm")
        if wm is None:
            wm = get_wm(host, opts)
            cache["wm"] = wm
        de = cache.get("de")
        if de is None:
            de = get_de(host, opts, wm)
            cache["de"] = de
        return get_wm_theme(host, opts, wm, de)
    if name == "theme":
        return get_theme(host, opts)
    if name == "icons":
        return get_icons(host, opts)
    if name == "font":
        return get_font(host, opts)
    if name == "term":
        term = cache.get("term")
        if term is None:
            term = get_term(host, opts)
            cache["term"] = term
        return term
    if name == "term_font":
        term = cache.get("term")
        if term is None:
            term = get_term(host, opts)
            cache["term"] = term
        return get_term_font(host, opts, term)
    if name == "cpu":
        return get_cpu(host, opts)
    if name == "gpu":
        return get_gpu(host, opts)
    if name == "memory":
        return get_memory(host, opts)
    if name == "song":
        return get_song(host, opts)
    if name == "disk":
        return get_disk(host, opts)
    if name == "battery":
        return get_battery(host, opts)
    if name == "local_ip":
        return get_local_ip(host, opts)
    if name == "public_ip":
        return get_public_ip(host, opts)
    if name == "users":
        return get_users(host, opts)
    if name == "locale":
        return get_locale(host, opts)
    if name == "gpu_driver":
        return get_gpu_driver(host, opts)
    return ""
