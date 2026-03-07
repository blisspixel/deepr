"""Tests for interactive main-menu input parsing."""

from deepr.cli.commands.interactive import _parse_main_menu_choice


def test_parse_main_menu_exit_aliases():
    assert _parse_main_menu_choice("q") == 0
    assert _parse_main_menu_choice("quit") == 0
    assert _parse_main_menu_choice("exit") == 0
    assert _parse_main_menu_choice("0") == 0


def test_parse_main_menu_numeric():
    assert _parse_main_menu_choice("1") == 1
    assert _parse_main_menu_choice("6") == 6


def test_parse_main_menu_aliases():
    assert _parse_main_menu_choice("?") == 6
    assert _parse_main_menu_choice("help") == 6
    assert _parse_main_menu_choice("r") == 1
    assert _parse_main_menu_choice("research") == 1
    assert _parse_main_menu_choice("e") == 2
    assert _parse_main_menu_choice("experts") == 2
    assert _parse_main_menu_choice("j") == 3
    assert _parse_main_menu_choice("jobs") == 3
    assert _parse_main_menu_choice("c") == 4
    assert _parse_main_menu_choice("costs") == 4
    assert _parse_main_menu_choice("g") == 5
    assert _parse_main_menu_choice("config") == 5


def test_parse_main_menu_invalid():
    assert _parse_main_menu_choice("") == -1
    assert _parse_main_menu_choice("not-an-option") == -1
