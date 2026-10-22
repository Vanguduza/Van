"""Repacked upstream tarballs must not change the bytes acquired for the voice bundle."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_asr_acquisition_uses_immutable_files_matching_the_shipping_manifest():
    lock = json.loads((ROOT / "android/voice/acquisition-lock.json").read_text())
    manifest = json.loads((ROOT / "android/voice/voice_asset_manifest.json").read_text())
    expected = {f["path"]: f for f in manifest["files"] if f["capability"] == "asr" and f["kind"] == "model"}
    acquired = {f["path"]: f for f in lock["raw_models"] if f["path"].startswith("asr/")}
    assert set(acquired) == set(expected)
    assert not any(a["capability"] == "asr" for a in lock["model_archives"])
    for path, artifact in acquired.items():
        assert artifact["size"] == expected[path]["size"]
        assert artifact["sha256"] == expected[path]["sha256"]
        assert re.fullmatch(r"[0-9a-f]{40}", artifact["source_revision"])
        assert artifact["source_revision"] == artifact["license"]["model_card_revision"]
        assert artifact["source_url"] == (artifact["license"]["model_card_url"] + "/resolve/" +
            artifact["source_revision"] + "/" + Path(path).name)
