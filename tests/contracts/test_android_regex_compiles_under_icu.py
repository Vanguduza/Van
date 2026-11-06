"""Android's java.util.regex is ICU4C, not the JDK engine the JVM tests run on.

ICU rejects an unescaped `}` that the JDK accepts, so `Regex("\\{(\\w+)}")` passed 1,273 JVM
tests and then threw PatternSyntaxException in every CommandCentreLaunchTest on the emulator
(van-ci run 39590832158). This compiles every literal regex in the app with the system ICU4C
library, so the class of defect fails here instead of on a device.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import glob
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "android" / "app" / "src"
LITERAL = re.compile(r'(?:Regex|Pattern\.compile)\(\s*(?:"""(.*?)"""|"((?:[^"\\\n]|\\.)*)")', re.S)


class _ParseError(ctypes.Structure):
    _fields_ = [("line", ctypes.c_int32), ("offset", ctypes.c_int32),
                ("pre", ctypes.c_uint16 * 16), ("post", ctypes.c_uint16 * 16)]


def _icu():
    candidates = sorted(glob.glob("/usr/lib/*/libicui18n.so.*") + glob.glob("/usr/lib/libicui18n.so.*"))
    name = ctypes.util.find_library("icui18n") or (candidates[-1] if candidates else None)
    if not name:
        pytest.skip("ICU4C (libicui18n) is not installed on this host")
    lib = ctypes.CDLL(name)
    version = re.search(r"\.so\.(\d+)", name) or re.search(r"(\d+)", Path(name).name)
    for symbol in ([f"uregex_open_{version.group(1)}"] if version else []) + ["uregex_open"]:
        if hasattr(lib, symbol):
            fn = getattr(lib, symbol)
            fn.restype = ctypes.c_void_p
            fn.argtypes = [ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32,
                           ctypes.POINTER(_ParseError), ctypes.POINTER(ctypes.c_int)]
            close = getattr(lib, symbol.replace("uregex_open", "uregex_close"))
            close.restype = None
            close.argtypes = [ctypes.c_void_p]
            return fn, close
    pytest.skip(f"{name} exports no uregex_open")


def _kotlin_literals():
    for path in sorted(SOURCES.rglob("*.kt")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in LITERAL.finditer(text):
            raw, escaped = m.group(1), m.group(2)
            if raw is not None:
                if "${" in raw:
                    continue
                pattern = raw
            else:
                if re.search(r"(?<!\\)\$[{\w]", escaped):
                    continue  # string template: not a constant pattern
                pattern = escaped.encode("utf-8").decode("unicode_escape")
            yield f"{path.relative_to(ROOT)}:{text[:m.start()].count(chr(10)) + 1}", pattern


def test_the_scan_finds_the_app_regexes():
    assert len(list(_kotlin_literals())) >= 20


def test_every_literal_app_regex_compiles_under_icu():
    open_, close = _icu()
    failures = []
    for where, pattern in _kotlin_literals():
        u16 = pattern.encode("utf-16-le")
        buf, error, status = ctypes.create_string_buffer(u16), _ParseError(), ctypes.c_int(0)
        handle = open_(buf, len(u16) // 2, 0, ctypes.byref(error), ctypes.byref(status))
        if status.value > 0:
            failures.append(f"{where}: {pattern!r} (ICU status {status.value} at offset {error.offset})")
        if handle:
            close(handle)
    assert not failures, "patterns Android rejects at runtime:\n" + "\n".join(failures)
