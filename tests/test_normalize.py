from tether.normalize import normalize


def test_identical_bytes_normalize_equal():
    a = b"hello\nworld\n"
    assert normalize(a) == normalize(a)


def test_crlf_folds_to_lf():
    assert normalize(b"a\r\nb\r\n") == normalize(b"a\nb\n")


def test_lone_cr_folds_to_lf():
    assert normalize(b"a\rb\r") == normalize(b"a\nb\n")


def test_bom_stripped():
    assert normalize("﻿hello\n".encode()) == normalize(b"hello\n")


def test_trailing_whitespace_stripped():
    assert normalize(b"hello   \nworld\t\n") == normalize(b"hello\nworld\n")


def test_trailing_blank_lines_collapsed():
    assert normalize(b"hello\n\n\n\n") == normalize(b"hello\n")


def test_missing_final_newline_added():
    assert normalize(b"hello") == normalize(b"hello\n")


def test_leading_tabs_expanded_default_tabstop():
    assert normalize(b"\tfoo\n") == b" " * 8 + b"foo\n"


def test_leading_tabs_expanded_custom_tabstop():
    assert normalize(b"\tfoo\n", tabstop=4) == b"    foo\n"


def test_internal_whitespace_preserved():
    assert normalize(b"a + b\n") != normalize(b"a+b\n")


def test_binary_returns_none():
    assert normalize(b"\x00\x01\x02\xff") is None


def test_empty_input():
    assert normalize(b"") == b""
