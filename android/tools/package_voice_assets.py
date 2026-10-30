#!/usr/bin/env python3
"""Package measured generic acoustic files. Gradle verification performs no network access.

--staged ROOT uses an independently qualified local staging directory.
--acquire downloads only the source-locked official artifacts, with TLS and exact digests.
--verify refuses absent, extra, corrupt, or source-pin-inconsistent generated files.
No command creates an owner embedding, owner signing key, or enrollment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ANDROID = Path(__file__).resolve().parents[1]
MANIFEST = ANDROID / "voice/voice_asset_manifest.json"
SOURCE = ANDROID / "voice/source"
LOCK = ANDROID / "voice/acquisition-lock.json"
PIN = ANDROID / "app/src/main/java/com/dial/van/voice/VoiceBundlePin.kt"
OUTPUT = ANDROID / "app/build/generated/voice-assets"
MAX_FETCH = 1024 * 1024 * 1024


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def checked_path(root: Path, relative: str) -> Path:
    if not relative or any(part in ("", ".", "..") for part in relative.split("/")) or any(c in relative for c in "\\:") or relative.startswith("/"):
        raise ValueError("unsafe acoustic path")
    result = root / relative
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError("acoustic path escapes root")
    return result


def expected() -> tuple[bytes, list[dict]]:
    content = MANIFEST.read_bytes()
    if not 1 <= len(content) <= 256 * 1024:
        raise ValueError("manifest size invalid")
    pin = re.search(r'const val SHA256 = "([0-9a-f]{64})"', PIN.read_text())
    if pin is None or hashlib.sha256(content).hexdigest() != pin[1]:
        raise ValueError("source manifest does not match compiled APK pin")
    data = json.loads(content)
    if data.get("schema") != "van-voice-assets/1" or data.get("owner_profile_included") is not False:
        raise ValueError("generic asset manifest contract invalid")
    files = data["files"]
    if not files or len(files) > 2048 or sum(row["size"] for row in files) > MAX_FETCH:
        raise ValueError("bundle bounds invalid")
    paths = [row["path"] for row in files]
    if len(set(paths)) != len(paths):
        raise ValueError("duplicate acoustic path")
    for row in files:
        checked_path(SOURCE, row["path"])
        if not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) or row["size"] <= 0:
            raise ValueError("unbound acoustic file")
    return content, files


def check_file(path: Path, row: dict) -> None:
    if not path.is_file() or path.stat().st_size != row["size"] or digest(path) != row["sha256"]:
        raise ValueError(f"acoustic file absent or integrity mismatch: {row['path']}")


def verify(output: Path) -> None:
    content, rows = expected()
    manifest = output / "voice/voice_asset_manifest.json"
    if not manifest.is_file() or manifest.read_bytes() != content:
        raise ValueError("generated manifest differs from signed APK source manifest")
    paths = {"voice/voice_asset_manifest.json"}
    for row in rows:
        relative = "voice/bundle/" + row["path"]
        check_file(checked_path(output, relative), row)
        paths.add(relative)
    actual = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    if actual != paths:
        raise ValueError("unexpected generated acoustic files")
    print(json.dumps({"status": "VERIFIED", "manifest_sha256": hashlib.sha256(content).hexdigest(), "file_count": len(rows), "file_bytes": sum(row["size"] for row in rows), "owner_profile_included": False}, sort_keys=True))


def package(staged: Path, output: Path) -> None:
    content, rows = expected()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="voice-pack-", dir=output.parent))
    try:
        for row in rows:
            source = checked_path(SOURCE if row["kind"] != "model" else staged, row["path"])
            check_file(source, row)
            target = checked_path(temporary, "voice/bundle/" + row["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        (temporary / "voice/voice_asset_manifest.json").write_bytes(content)
        verify(temporary)
        if output.exists():
            shutil.rmtree(output)
        temporary.rename(output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def fetch(url: str, target: Path, size: int, sha256: str) -> None:
    if not url.startswith("https://") or size <= 0 or size > MAX_FETCH:
        raise ValueError("unbound public artifact")
    if target.is_file() and target.stat().st_size == size and digest(target) == sha256:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_suffix(target.suffix + ".pending")
    try:
        with urllib.request.urlopen(url, timeout=60) as source, pending.open("wb") as destination:
            total = 0
            for block in iter(lambda: source.read(65536), b""):
                total += len(block)
                if total > size:
                    raise ValueError("artifact exceeds source-locked size")
                destination.write(block)
        if total != size or digest(pending) != sha256:
            raise ValueError("artifact size/digest mismatch")
        pending.replace(target)
    finally:
        pending.unlink(missing_ok=True)


def acquire(cache: Path) -> Path:
    lock = json.loads(LOCK.read_text())
    if lock.get("schema_version") != 1:
        raise ValueError("acquisition lock schema invalid")
    artifacts = lock["model_archives"] + lock.get("raw_models", [])
    if sum(item.get("archive", item)["size"] for item in artifacts) > MAX_FETCH:
        raise ValueError("public acquisition budget exceeded")
    staged = cache / "selected"
    staged.mkdir(parents=True, exist_ok=True)
    for artifact in lock["model_archives"]:
        metadata = artifact["archive"]
        archive = checked_path(cache, metadata["archive"])
        fetch(artifact["source_url"], archive, metadata["size"], metadata["sha256"])
        wanted = [row for row in lock["weights"] if row["path"].startswith(artifact["capability"] + "/")]
        remaining = {Path(row["path"]).name: row for row in wanted}
        # Only exact model members are streamed out; links and all other archive contents are ignored.
        with tarfile.open(archive, "r|bz2") as contents:
            for member in contents:
                row = remaining.get(Path(member.name).name)
                if row is None:
                    continue
                if not member.isfile() or member.size != row["size"]:
                    raise ValueError("archive model metadata mismatch")
                target = checked_path(staged, row["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                with contents.extractfile(member) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, 65536)
                check_file(target, row)
                del remaining[Path(member.name).name]
        if remaining:
            raise ValueError("source archive missing exact selected model")
    for artifact in lock.get("raw_models", []):
        fetch(artifact["source_url"], checked_path(staged, artifact["path"]), artifact["size"], artifact["sha256"])
    return staged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", type=Path)
    mode.add_argument("--acquire", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--cache", type=Path, default=ANDROID / "app/build/voice-acquisition")
    args = parser.parse_args()
    if args.verify:
        verify(args.output)
    else:
        package(acquire(args.cache) if args.acquire else args.staged, args.output)
        verify(args.output)


if __name__ == "__main__":
    main()
