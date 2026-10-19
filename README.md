<h3 align="center">neoinfo</h3>
<p align="center">A fast, dependency-free command-line system information tool.</p>

<p align="center">
<a href="https://pypi.org/project/neoinfo/"><img src="https://img.shields.io/pypi/v/neoinfo.svg" alt="PyPI version"></a>
<a href="https://pypi.org/project/neoinfo/"><img src="https://img.shields.io/pypi/pyversions/neoinfo.svg" alt="Python versions"></a>
<a href="./LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" alt="License"></a>
</p>

```sh
$ neoinfo
wensheng@Wenshengs-Mac-mini.local
---------------------------------
OS: macOS 27.0.1 26A434 arm64
Host: Mac mini (Mac16,10)
Kernel: 27.0.0
Uptime: 17 days, 6 hours, 32 mins
Packages: 192 (brew)
Shell: zsh 5.9
Resolution: 6016x3384
DE: Aqua
WM: Quartz Compositor
Terminal: claude
CPU: Apple M4 (10)
GPU: Apple M4
Memory: 23252MiB / 32768MiB
```

neoinfo displays information about your operating system, software and
hardware in an aesthetic and visually pleasing way. It is a single command
with zero runtime dependencies — install it and run it, nothing else.

The overall purpose of neoinfo is to be used in screenshots of your system.
neoinfo shows the information other people want to see. There are other tools
available for proper system statistics and diagnostics.

By default the information is displayed alongside your operating system's
ASCII logo — with 260+ distro logos built in, the right one is picked
automatically. Prefer a clean look? Logo-only mode, plain output, or no logo
at all are one flag away.

You can configure neoinfo to display exactly what you want it to. Through
command-line flags and a simple TOML config file you can change the existing
information, reorder it, or show only the parts you care about.

## Install

```sh
pip install neoinfo        # or: pipx install neoinfo / uv tool install neoinfo
```

Python 3.12+, no runtime dependencies, works on Linux and macOS.

## Usage

```sh
neoinfo                    # full report with ASCII logo
neoinfo --stdout           # plain `Label: value` lines, no logo or colors
neoinfo --json             # one JSON object — great for scripts
neoinfo uptime memory cpu  # only these collectors
neoinfo -L                 # logo only
```

## Configure

Print the default config, edit, and make it yours:

```sh
neoinfo --print_config > ~/.config/neoinfo/config.toml
```

Every option can be changed there, including `info_order` — the list of
entries shown and their order. Use `--config PATH` to load a different file,
or `--no_config` to skip configuration entirely.

### More: \[[PyPI](https://pypi.org/project/neoinfo/)\] \[[Issues](https://github.com/wensheng/neoinfo/issues)\]
