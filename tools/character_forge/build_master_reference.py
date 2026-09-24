from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, __version__ as pillow_version

CANONICAL_GIT_BLOB = "fc18bbe0b91e5b85d8cf8211314a69cb90b8bc0b"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(source: Path, output: Path, receipt: Path, scale: int = 2) -> dict:
    if scale < 2:
        raise ValueError("reference upscale must be at least 2x")
    with Image.open(source) as image:
        image = image.convert("RGBA")
        source_size = image.size
        target = (source_size[0] * scale, source_size[1] * scale)
        derived = image.resize(target, Image.Resampling.LANCZOS)
        output.parent.mkdir(parents=True, exist_ok=True)
        derived.save(output, format="PNG", optimize=False, compress_level=9)

    record = {
        "schema_version": 1,
        "status": "EXACT_DERIVED_REFERENCE_NOT_APPROVED_MASTER",
        "provenance": "DERIVED_VISIBLE",
        "source_path": source.as_posix(),
        "source_git_blob_sha": CANONICAL_GIT_BLOB,
        "source_sha256": sha256_file(source),
        "source_dimensions": list(source_size),
        "scale": scale,
        "resampler": "Pillow.Image.Resampling.LANCZOS",
        "pillow_version": pillow_version,
        "output_path": output.as_posix(),
        "output_dimensions": list(target),
        "output_sha256": sha256_file(output),
        "adds_new_identity_detail": False,
        "owner_approval_required_for_master_promotion": True,
    }
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--scale", type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output, args.receipt, args.scale), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
