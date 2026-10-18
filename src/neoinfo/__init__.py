"""Neoinfo: system information tool. Python port of neofetch 7.1.0."""

__version__ = "0.1.0"


def main() -> None:
    from neoinfo.cli import main as cli_main

    cli_main()
