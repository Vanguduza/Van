"""The audit tool's own comment stripper, which was silently wrong.

`kotlin_reachability.py` decides which Kotlin files nothing production reaches. Its first
step is removing comments and string literals, so that a symbol named in a KDoc paragraph
does not count as a call site.

It did that with a sequence of regular expressions, comments first. A Kotlin *string*
containing comment punctuation therefore closed a block comment that a KDoc had opened
hundreds of lines earlier, and everything between them disappeared from the analysis. The
string that did it is `"*/*"` — the MIME wildcard any `ACTION_OPEN_DOCUMENT` call passes —
and the result was the gate reporting a live class as referenced by nothing.

That is the one direction this tool must not be wrong in: an over-report of deadness gets
acted on, and the action is deleting something that is running.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "audit"))

from kotlin_reachability import _strip_noise  # noqa: E402


def test_a_mime_wildcard_does_not_swallow_the_rest_of_the_file():
    """The exact shape that broke it."""
    source = """
        /** Some documentation. */
        fun choose() {
            picker.launch(arrayOf("*/*"))
        }
        fun later() { BrowserSurfaceView(context) }
    """
    stripped = _strip_noise(source)
    assert "BrowserSurfaceView" in stripped
    assert "documentation" not in stripped


def test_comment_punctuation_inside_any_string_is_just_text():
    for literal in ('"/*"', '"*/"', '"a /* b */ c"'):
        source = f"val x = {literal}\nfun after() {{ Marker() }}"
        assert "Marker" in _strip_noise(source), literal


def test_a_quote_inside_a_comment_does_not_open_a_string():
    """The failure the naive fix has: swapping the order so strings go first means a
    comment containing an apostrophe or a quote eats the code after it."""
    source = '/* the owner\'s "browser" window */\nfun after() { Marker() }'
    assert "Marker" in _strip_noise(source)


def test_nested_block_comments_close_where_kotlin_says_they_do():
    """Kotlin's block comments nest and Java's do not. A stripper that ended the comment
    at the first `*/` would treat the rest of the outer comment as code, and every symbol
    named in it would count as a call site — the exact confusion this tool exists to
    remove."""
    source = "/* outer /* inner */ still comment */\nfun after() { Marker() }"
    stripped = _strip_noise(source)
    assert "Marker" in stripped
    assert "still" not in stripped


def test_documentation_still_does_not_count_as_a_call_site():
    """The property the stripper exists for, which the fix must not lose."""
    source = "/** Calls [SomethingDead] when asked. */\nfun alive() { Marker() }"
    stripped = _strip_noise(source)
    assert "SomethingDead" not in stripped
    assert "Marker" in stripped


def test_a_raw_string_is_removed_whole():
    source = 'val q = """\nSELECT * FROM t /* not a comment */\n"""\nfun after() { Marker() }'
    stripped = _strip_noise(source)
    assert "SELECT" not in stripped
    assert "Marker" in stripped


def test_an_escaped_quote_does_not_end_the_string_early():
    source = 'val s = "a \\" DeadSymbol b"\nfun after() { Marker() }'
    stripped = _strip_noise(source)
    assert "DeadSymbol" not in stripped
    assert "Marker" in stripped


def test_an_unterminated_string_does_not_eat_the_file():
    """A malformed source file should make the sweep report less, not report nothing.

    Kotlin string literals do not span lines, so the scan stops at the newline rather
    than running to the end of the file looking for a closing quote.
    """
    source = 'val broken = "oops\nfun after() { Marker() }'
    assert "Marker" in _strip_noise(source)


def test_the_real_browser_activity_still_references_its_renderer():
    """The regression, against the actual file.

    A unit test over a snippet proves the scanner; this proves the thing the scanner is
    used for. `BrowserActivity` constructs `BrowserSurfaceView`, and for one commit the
    gate could not see it.
    """
    activity = (
        ROOT / "android/app/src/main/java/com/dial/van/browser/BrowserActivity.kt"
    ).read_text(encoding="utf-8")
    assert "BrowserSurfaceView" in _strip_noise(activity)
