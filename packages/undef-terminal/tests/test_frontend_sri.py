# SPDX-License-Identifier: MIT
"""Verify SRI integrity attributes on CDN resources in frontend HTML files."""

import re
from pathlib import Path

FRONTEND_DIR = Path("packages/undef-terminal/src/undef/terminal/frontend")


def test_terminal_html_scripts_have_integrity() -> None:
    html = (FRONTEND_DIR / "terminal.html").read_text()
    scripts = re.findall(r"<script[^>]+cdn\.jsdelivr\.net[^>]+>", html)
    assert scripts, "Expected CDN script tags in terminal.html"
    for tag in scripts:
        assert 'integrity="sha384-' in tag, f"Missing SRI integrity: {tag}"
        assert 'crossorigin="anonymous"' in tag, f"Missing crossorigin: {tag}"


def test_terminal_html_stylesheets_have_integrity() -> None:
    html = (FRONTEND_DIR / "terminal.html").read_text()
    links = re.findall(r"<link[^>]+cdn\.jsdelivr\.net[^>]+>", html)
    assert links, "Expected CDN stylesheet link tags in terminal.html"
    for tag in links:
        assert 'integrity="sha384-' in tag, f"Missing SRI integrity: {tag}"
        assert 'crossorigin="anonymous"' in tag, f"Missing crossorigin: {tag}"


def test_terminal_html_google_fonts_no_integrity() -> None:
    html = (FRONTEND_DIR / "terminal.html").read_text()
    fonts_links = re.findall(r"<link[^>]+fonts\.googleapis\.com[^>]+>", html)
    for tag in fonts_links:
        assert "integrity=" not in tag, f"Google Fonts should not have SRI: {tag}"


def test_hijack_html_scripts_have_integrity() -> None:
    html = (FRONTEND_DIR / "hijack.html").read_text()
    scripts = re.findall(r"<script[^>]+cdn\.jsdelivr\.net[^>]+>", html)
    assert scripts, "Expected CDN script tags in hijack.html"
    for tag in scripts:
        assert 'integrity="sha384-' in tag, f"Missing SRI integrity: {tag}"
        assert 'crossorigin="anonymous"' in tag, f"Missing crossorigin: {tag}"


def test_hijack_html_stylesheets_have_integrity() -> None:
    html = (FRONTEND_DIR / "hijack.html").read_text()
    links = re.findall(r"<link[^>]+cdn\.jsdelivr\.net[^>]+>", html)
    assert links, "Expected CDN stylesheet link tags in hijack.html"
    for tag in links:
        assert 'integrity="sha384-' in tag, f"Missing SRI integrity: {tag}"
        assert 'crossorigin="anonymous"' in tag, f"Missing crossorigin: {tag}"


def test_hijack_html_google_fonts_no_integrity() -> None:
    html = (FRONTEND_DIR / "hijack.html").read_text()
    fonts_links = re.findall(r"<link[^>]+fonts\.googleapis\.com[^>]+>", html)
    for tag in fonts_links:
        assert "integrity=" not in tag, f"Google Fonts should not have SRI: {tag}"
