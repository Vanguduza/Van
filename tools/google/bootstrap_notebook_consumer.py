#!/usr/bin/env python3
"""One-time owner login bootstrap for VAN's managed NotebookLM browser profile.

This engineering utility may open Chromium only to establish/verify the owner's
managed profile. It is NOT the NotebookLM runtime transport: production reads and
mutations run through Browser Harness + Stagehand. The tool never exports or
prints cookies/tokens, and READY still requires the gateway Browser Fabric canary.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from urllib.parse import urlparse


def ensure_profile(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, stat.S_IRWXU)


def install_browser() -> None:
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)


def open_profile(profile: Path, *, login: bool, verify: bool, base_url: str) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("playwright package missing; install backend/requirements.txt first") from exc

    result = {"profile_present": True, "authenticated": False, "base_host": urlparse(base_url).hostname}
    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile), headless=not login,
            )
        except Exception as exc:
            raise SystemExit(f"Chromium launch failed: {type(exc).__name__}; run with --install-browser") from exc
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(1000)
        signed_out = "accounts.google." in page.url
        if not signed_out:
            try:
                signed_out = page.get_by_text("Sign in", exact=True).count() > 0
            except Exception:
                signed_out = False
        result["authenticated"] = not signed_out
        result["observed_host"] = urlparse(page.url).hostname
        if login:
            print("Complete Google sign-in in the opened Chromium window, then press Enter here.")
            input()
            page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(1000)
            result["authenticated"] = "accounts.google." not in page.url
            result["observed_host"] = urlparse(page.url).hostname
        context.close()
    if verify and not result["authenticated"]:
        raise SystemExit("Notebook consumer profile is not authenticated")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--profile-dir",
        default=os.environ.get(
            "VAN_NOTEBOOK_CONSUMER_PROFILE_DIR",
            "/var/lib/van-trading/browser/profiles/authenticated_owner",
        ),
    )
    ap.add_argument("--base-url", default="https://notebooklm.google.com")
    ap.add_argument("--install-browser", action="store_true")
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    profile = Path(args.profile_dir).expanduser().resolve()
    ensure_profile(profile)
    if args.install_browser:
        install_browser()
    result = open_profile(profile, login=args.login, verify=args.verify, base_url=args.base_url) if (args.login or args.verify) else {
        "profile_present": True,
        "authenticated": None,
        "base_host": urlparse(args.base_url).hostname,
    }
    result["profile_dir"] = str(profile)
    result["profile_mode"] = oct(profile.stat().st_mode & 0o777)
    result["bootstrap_only"] = True
    result["runtime_transport"] = "BrowserHarness+Stagehand"
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())