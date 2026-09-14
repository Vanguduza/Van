#!/usr/bin/env python3
"""Generate deterministic platform visual assets (canonical palette)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "visual-authority" / "assets"

# DIAL cyan + silver/white + medium brown skin cues (RGB)
CYAN = (0, 200, 220, 255)
SILVER = (220, 225, 230, 255)
SKIN = (166, 116, 82, 255)
JACKET = (20, 22, 28, 255)
VISOR = (80, 180, 230, 180)
BG = (12, 18, 28, 255)
ORB = (0, 230, 255, 200)


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path: Path, width: int, height: int, rgba_fn) -> None:
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(rgba_fn(x, y, width, height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + _chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def circle(x, y, cx, cy, r):
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def van_pixel(x, y, w, h, mode: str):
    # Simple recognisable silhouette: head, visor, jacket, orb
    cx, cy = w // 2, int(h * 0.42)
    head_r = int(min(w, h) * 0.18)
    if circle(x, y, int(w * 0.78), int(h * 0.30), int(min(w, h) * 0.06)):
        return ORB if mode != "offline" else (80, 90, 100, 180)
    if circle(x, y, cx, cy - int(h * 0.02), head_r):
        # hair band (silver)
        if y < cy - int(head_r * 0.35):
            return (180, 185, 190, 255) if mode != "offline" else (120, 120, 125, 255)
        # visor
        if abs(y - cy) < int(head_r * 0.35) and abs(x - cx) < int(head_r * 0.7):
            return VISOR if mode != "urgent" else (255, 120, 80, 200)
        return SKIN
    # torso / jacket
    if abs(x - cx) < int(w * 0.16) and cy + head_r - 5 < y < int(h * 0.85):
        return JACKET if (x + y) % 7 else (240, 240, 245, 255)
    if mode == "offline":
        return (18, 22, 30, 255)
    if mode == "urgent":
        return (28, 10, 12, 255)
    return BG


ASSETS = {
    "turnaround.png": ("normal", 512, 512),
    "expressions.png": ("normal", 512, 256),
    "gestures.png": ("normal", 512, 256),
    "presentation.png": ("normal", 768, 512),
    "app_icon.png": ("normal", 512, 512),
    "adaptive_fg.png": ("normal", 432, 432),
    "monochrome_icon.png": ("normal", 432, 432),
    "notification_icon.png": ("normal", 128, 128),
    "compact_avatar.png": ("normal", 192, 192),
    "hermes_avatar.png": ("normal", 256, 256),
    "onboarding_hero.png": ("normal", 1024, 640),
    "command_centre.png": ("normal", 1024, 640),
    "offline_degraded.png": ("offline", 512, 512),
    "urgent_decision.png": ("urgent", 512, 512),
}


def main() -> None:
    for name, (mode, w, h) in ASSETS.items():
        path = OUT / name
        if name == "monochrome_icon.png":
            write_png(path, w, h, lambda x, y, ww, hh: (220, 220, 220, 255) if van_pixel(x, y, ww, hh, "normal")[3] > 0 and van_pixel(x, y, ww, hh, "normal") != BG else (0, 0, 0, 0))
        else:
            write_png(path, w, h, lambda x, y, ww, hh, m=mode: van_pixel(x, y, ww, hh, m))
        print("wrote", path)


if __name__ == "__main__":
    main()
