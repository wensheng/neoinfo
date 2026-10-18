"""Display pipeline tests: logo lookup, colors, layout, bars, JSON."""

import json as jsonlib

from neoinfo import display
from neoinfo.display import Palette
from neoinfo.options import Options


def test_color_codes():
    assert display.color("1") == "\033[0m\033[31m"
    assert display.color("7") == "\033[0m\033[37m"
    assert display.color("fg") == "\033[0m\033[37m"
    assert display.color("8") == "\033[38;5;8m"
    assert display.color("255") == "\033[38;5;255m"


def test_find_logo_ubuntu():
    colors, art = display.find_logo("Ubuntu 24.04.5 LTS x86_64", "Linux")
    assert colors == ("1", "7", "3")
    assert "oossssoo" in art


def test_find_logo_arch():
    colors, art = display.find_logo("Arch Linux x86_64", "Linux")
    assert colors == ("6", "6", "7", "1")


def test_find_logo_case_insensitive():
    # neofetch matches with nocasematch, so lookup must ignore case too.
    colors, art = display.find_logo("arch linux x86_64", "Linux")
    assert "ooo" in art


def test_find_logo_small_variant():
    colors, art = display.find_logo("arch_small", "Linux")
    assert 0 < len(art.splitlines()) < 12


def test_find_logo_kernel_fallback():
    colors, art = display.find_logo("Some Unknown Distro 1.0", "Linux")
    assert "#####" in art  # generic Tux


def test_find_logo_bsd_kernel_fallback():
    colors, art = display.find_logo("Some Unknown Distro 1.0", "FreeBSD")
    assert "( (_" in art or "M" in art


def test_ascii_width_ignores_placeholders():
    assert display.ascii_width("{c1}abc{c2}de") == 5


def test_layout_zips_logo_and_info():
    out = display.layout(["aa", "bbbb", "c"], ["1", "2"], gap=3, plain=True)
    assert out == ["aa     1", "bbbb   2", "c"]


def test_layout_no_logo():
    assert display.layout([], ["a"], gap=3, plain=True) == ["a"]


def test_format_info_line_stdout():
    opts = Options(stdout="on")
    pal = Palette(opts, ())
    assert display.format_info_line("OS", "Linux", opts, pal) == "OS: Linux"


def test_format_info_line_separator():
    opts = Options(stdout="on", separator="=")
    pal = Palette(opts, ())
    assert display.format_info_line("OS", "Linux", opts, pal) == "OS= Linux"


def test_render_bar():
    opts = Options()
    opts._palette = Palette(opts, ("1", "7"))
    bar = display.render_bar(5, 10, opts)
    assert bar.startswith("\033[0m\033[37m[")
    assert bar.count("-") == 7  # 5 * 15 // 10
    assert bar.count("=") == 8


def test_render_bar_plain_has_no_escapes():
    opts = Options(stdout="on")
    opts._palette = Palette(opts, ())
    bar = display.render_bar(5, 10, opts)
    assert bar == "[-------========]"
    assert "\033" not in bar


def test_to_json_shape():
    out = display.to_json([("OS", "X"), ("GPU", "Y"), ("GPU", "Y")], "0.1.0")
    parsed = jsonlib.loads(out)
    assert parsed["OS"] == "X"
    assert out.count('"GPU": "Y"') == 2
    assert '"Version": "0.1.0"' in out


def test_color_blocks_off():
    assert display.color_block_lines(Options(color_blocks="off"), 0) == []


def test_color_blocks_on():
    lines = display.color_block_lines(Options(stdout="on"), 0)
    assert len(lines) == 1
    assert "38;5;15" in lines[0]
