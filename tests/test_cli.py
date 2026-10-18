"""CLI tests, including the JSON multi-line regression test.

Regression background: neofetch's bash `prin()` returns early in `--json`
mode without setting `prin=1`, so `info()` falls through and reprints the
leftover scalar (e.g. a third "GPU" line for two GPUs). neoinfo must emit
exactly one line per collector entry.
"""

import json as jsonlib

from neoinfo import collectors, display
from neoinfo.cli import gather, main
from neoinfo.collectors import Host
from neoinfo.options import Options
from neoinfo import util


def _host():
    return Host(
        kernel_name="Linux",
        kernel_version="6.8.0-test",
        kernel_machine="x86_64",
        os="Linux",
        distro="Ubuntu 24.04 LTS x86_64",
        machine_arch="x86_64",
    )


def test_json_has_no_duplicate_reprint(monkeypatch, capsys):
    """Two GPUs must produce exactly two JSON lines, not three."""
    lspci = (
        '04:00.0 "VGA compatible controller" "NVIDIA Corporation" '
        '"GA102 [GeForce RTX 3090]" -ra1 -p00 "MSI" "GA102 [GeForce RTX 3090]"\n'
        '2b:00.0 "VGA compatible controller" "NVIDIA Corporation" '
        '"GA102 [GeForce RTX 3090]" -ra1 -p00 "NVIDIA" "GA102 [GeForce RTX 3090]"\n'
    )
    monkeypatch.setattr(util, "run", lambda argv, timeout=10: lspci)
    host = _host()
    pairs, _ = gather(host, Options(), [("GPU", "gpu")], [])
    assert pairs == [("GPU", "NVIDIA GeForce RTX 3090")] * 2
    out = display.to_json(pairs, "0.1.0")
    assert out.count('"GPU": "NVIDIA GeForce RTX 3090"') == 2
    assert len(jsonlib.loads(out)) == 2  # GPU + Version


def test_gather_skips_empty_without_reprint(monkeypatch):
    monkeypatch.setattr(util, "run", lambda argv, timeout=10: None)
    monkeypatch.setattr(util, "read_text", lambda path: None)
    pairs, errors = gather(_host(), Options(), [("GPU", "gpu")], [])
    assert pairs == []
    assert errors == ["Info: Couldn't detect GPU."]


def test_main_version(capsys):
    assert main(["--version"]) == 0
    assert "Neoinfo" in capsys.readouterr().out


def test_main_stdout_smoke(capsys):
    assert main(["--stdout"]) == 0
    out = capsys.readouterr().out
    for label in ("OS:", "Kernel:", "Uptime:", "CPU:", "Memory:"):
        assert label in out


def test_main_disable(capsys):
    assert main(["--stdout", "--disable", "gpu", "memory"]) == 0
    out = capsys.readouterr().out
    assert "GPU:" not in out
    assert "Memory:" not in out
    assert "CPU:" in out


def test_main_positional_funcs(capsys):
    assert main(["uptime", "memory"]) == 0
    out = capsys.readouterr().out
    assert "uptime:" in out
    assert "memory:" in out
    assert "OS:" not in out


def test_main_unknown_func():
    try:
        main(["frobnicate"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse error exit")


def test_main_json_valid(capsys):
    assert main(["--json"]) == 0
    out = capsys.readouterr().out
    parsed = jsonlib.loads(out)
    assert parsed["OS"]
    assert "Version" in parsed


def test_main_ascii_distro_override(capsys):
    assert main(["--stdout", "--ascii_distro", "Arch"]) == 0
    assert main(["--logo", "--ascii_distro", "Arch"]) == 0
    logo = capsys.readouterr().out
    assert "-`" in logo  # first line of the Arch logo
