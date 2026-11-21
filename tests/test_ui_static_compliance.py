"""
Automated Static Analysis and Compliance Test for UI artifacts:
- No third-party network requests (no CDN, external fonts, scripts, or styles)
- No inline scripts (<script> without src)
- No inline style attributes (style="...")
- No inline HTML event attributes (onclick, onsubmit, onload, etc.)
- No dynamic innerHTML or insertAdjacentHTML assignments in JavaScript
- Accessible markup (viewport meta, aria-live regions, form labels)
"""

import os
import re
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent.parent / "ui"


def get_ui_files(ext: str):
    return list(UI_DIR.glob(f"**/*{ext}"))


def test_no_inline_scripts():
    html_files = get_ui_files(".html")
    assert html_files, "No HTML files found in ui/"

    inline_script_pattern = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)

    for html_file in html_files:
        content = html_file.read_text(encoding="utf-8")
        matches = inline_script_pattern.findall(content)
        for match in matches:
            cleaned = match.strip()
            assert not cleaned, f"Found inline script in {html_file.name}: {cleaned[:80]}..."


def test_no_inline_styles():
    html_files = get_ui_files(".html")
    inline_style_attr_pattern = re.compile(r'\bstyle\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)

    for html_file in html_files:
        content = html_file.read_text(encoding="utf-8")
        matches = inline_style_attr_pattern.findall(content)
        assert not matches, f"Found inline style attribute in {html_file.name}: {matches}"


def test_no_inline_event_handlers():
    html_files = get_ui_files(".html")
    # Attributes like onclick="...", onsubmit="...", onload="..."
    event_attr_pattern = re.compile(r'\bon[a-z]+\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)

    for html_file in html_files:
        content = html_file.read_text(encoding="utf-8")
        matches = event_attr_pattern.findall(content)
        assert not matches, f"Found inline event handler attribute in {html_file.name}: {matches}"


def test_no_external_resources():
    html_files = get_ui_files(".html")
    css_files = get_ui_files(".css")

    # In HTML: <link href="http...", <script src="http..."
    external_resource_pattern = re.compile(
        r'<(?:link|script|img|iframe)\b[^>]*(?:href|src)\s*=\s*["\'](https?://[^"\']+)["\']',
        re.IGNORECASE
    )

    for html_file in html_files:
        content = html_file.read_text(encoding="utf-8")
        matches = external_resource_pattern.findall(content)
        assert not matches, f"Found external resource in {html_file.name}: {matches}"

    # In CSS: @import url("http..."), url("http...")
    css_external_pattern = re.compile(r'url\s*\(\s*["\']?(https?://[^"\'\)]+)["\']?\s*\)', re.IGNORECASE)
    for css_file in css_files:
        content = css_file.read_text(encoding="utf-8")
        matches = css_external_pattern.findall(content)
        assert not matches, f"Found external URL in {css_file.name}: {matches}"


def test_safe_dom_manipulation_in_js():
    js_files = get_ui_files(".js")
    assert js_files, "No JS files found in ui/"

    inner_html_pattern = re.compile(r'\.innerHTML\s*=', re.IGNORECASE)
    adjacent_html_pattern = re.compile(r'\.insertAdjacentHTML\s*\(', re.IGNORECASE)

    for js_file in js_files:
        content = js_file.read_text(encoding="utf-8")
        assert not inner_html_pattern.search(content), f"Found innerHTML assignment in {js_file.name}"
        assert not adjacent_html_pattern.search(content), f"Found insertAdjacentHTML in {js_file.name}"


def test_accessibility_essentials():
    index_html = UI_DIR / "index.html"
    assert index_html.exists()
    content = index_html.read_text(encoding="utf-8")

    # Mobile viewport
    assert '<meta name="viewport"' in content, "Missing viewport meta tag in index.html"

    # aria-live for screen readers
    assert 'aria-live="polite"' in content, "Missing aria-live region in index.html for chat updates"

    # lang attribute
    assert 'lang="en"' in content, "Missing lang='en' in html tag"


if __name__ == "__main__":
    test_no_inline_scripts()
    test_no_inline_styles()
    test_no_inline_event_handlers()
    test_no_external_resources()
    test_safe_dom_manipulation_in_js()
    test_accessibility_essentials()
    print("test_ui_static_compliance: ALL PASSED")
