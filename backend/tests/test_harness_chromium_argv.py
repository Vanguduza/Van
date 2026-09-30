"""Review I7 minor 4 (unit G11) — the Harness-owned Chromium's command line, as launched.

The network-effect guard depends on two Chromium features being off (KeepAliveInBrowserMigration:
keepalive requests from a service-worker-controlled page bypassed every Fetch session;
SharedWorker: a shared worker's requests escaped). Chromium honours only the *last*
``--disable-features``, so a second one anywhere in the launch silently switches both back on.
Review I7 induced exactly that (and dropping the flags altogether) and every test still passed:
the tests launched their own Chromium, never the argv ``ChromeSession.ensure()`` builds. This
captures that argv.
"""
from __future__ import annotations

import subprocess

import pytest

import test_harness_elements as he


class _Launched(Exception):
    pass


def _ensure_argv(module, monkeypatch, tmp_path) -> list[str]:
    chrome = tmp_path / "chrome"
    chrome.write_text("#!/bin/sh\n")
    monkeypatch.setattr(module, "CHROMIUM", str(chrome))
    monkeypatch.setattr(module, "PROFILE_ROOT", tmp_path / "profiles")
    monkeypatch.setattr(module, "RUNTIME_ROOT", tmp_path / "run")
    seen: list[list[str]] = []

    def popen(argv, *args, **kwargs):
        seen.append(list(argv))
        raise _Launched

    monkeypatch.setattr(subprocess, "Popen", popen)
    with pytest.raises(_Launched):
        module.ChromeSession("public_research").ensure()
    assert len(seen) == 1
    return seen[0]


def _one_disable_features(argv: list[str]) -> set[str]:
    flags = [a for a in argv if a.startswith("--disable-features")]
    assert len(flags) == 1, flags  # Chromium honours only the last one
    return set(flags[0].split("=", 1)[1].split(","))


def test_ensure_launches_one_merged_disable_features_with_the_guards_features(monkeypatch, tmp_path):
    module = he._load(monkeypatch, tmp_path)
    argv = _ensure_argv(module, monkeypatch, tmp_path)
    assert argv[0].endswith("chrome") and argv[-1] == "about:blank"
    assert {"KeepAliveInBrowserMigration", "SharedWorker"} <= _one_disable_features(argv)
    assert "--disable-blink-features=SharedWorker" in argv
    assert "--remote-debugging-address=127.0.0.1" in argv and "--headless=new" in argv


def test_a_flag_added_later_is_merged_not_appended(monkeypatch, tmp_path):
    """Unit G12 will add ``--proxy-server`` (the owner's egress proxy); any flag added through
    ``chromium_argv`` keeps the single merged --disable-features."""
    module = he._load(monkeypatch, tmp_path)
    argv = module.chromium_argv(tmp_path / "p", ("--proxy-server=http://127.0.0.1:3128", "--disable-features=Translate"))
    assert "--proxy-server=http://127.0.0.1:3128" in argv
    assert _one_disable_features(argv) == {"KeepAliveInBrowserMigration", "SharedWorker", "Translate"}


def test_merge_keeps_order_and_drops_duplicates(monkeypatch, tmp_path):
    module = he._load(monkeypatch, tmp_path)
    assert module.merge_disable_features(
        ["--a", "--disable-features=X,Y", "--b", "--disable-features=Y,Z", "--c"]
    ) == ["--a", "--disable-features=X,Y,Z", "--b", "--c"]
