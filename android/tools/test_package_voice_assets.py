"""Tests the actual packer's integrity and non-publishing failure contracts; no downloads."""
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("van_voice_package", Path(__file__).with_name("package_voice_assets.py"))
PACK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACK)


class VoiceAssetPackageTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.staged = self.root / "staged"
        self.output = self.root / "output"
        self.manifest = self.root / "manifest.json"
        self.pin = self.root / "VoiceBundlePin.kt"
        self.lock = self.root / "lock.json"
        self.keyword = b"HEY VAN\n"
        self.model = b"m" * 16384
        rows = []
        for relative, content, kind, root in [("wake/keywords.txt", self.keyword, "keywords", self.source), ("wake/model.onnx", self.model, "model", self.staged)]:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            rows.append({"path": relative, "kind": kind, "capability": "wake", "size": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        content = json.dumps({"schema": "van-voice-assets/1", "owner_profile_included": False, "files": rows}).encode()
        self.manifest.write_bytes(content)
        self.pin.write_text('const val SHA256 = "' + hashlib.sha256(content).hexdigest() + '"')
        self.lock.write_text(json.dumps({"schema_version": 1, "model_archives": [], "weights": []}))
        self.overrides = patch.multiple(PACK, MANIFEST=self.manifest, SOURCE=self.source, PIN=self.pin, LOCK=self.lock)
        self.overrides.start()

    def tearDown(self):
        self.overrides.stop()
        self.temporary.cleanup()

    def test_exact_pack_verifies_and_repackages(self):
        PACK.package(self.staged, self.output)
        PACK.verify(self.output)
        self.assertEqual((self.output / "voice/voice_asset_manifest.json").read_bytes(), self.manifest.read_bytes())
        self.assertEqual((self.output / "voice/bundle/wake/model.onnx").read_bytes(), self.model)
        PACK.package(self.staged, self.output)
        PACK.verify(self.output)

    def test_failed_preparation_retains_last_complete_pack(self):
        PACK.package(self.staged, self.output)
        (self.staged / "wake/model.onnx").write_bytes(self.model[:-1])
        with self.assertRaises(ValueError):
            PACK.package(self.staged, self.output)
        PACK.verify(self.output)
        self.assertEqual(list(self.root.glob("voice-pack-*")), [])

    def test_corrupt_or_extra_generated_file_refuses(self):
        PACK.package(self.staged, self.output)
        (self.output / "extra.txt").write_text("unexpected")
        with self.assertRaises(ValueError):
            PACK.verify(self.output)
        (self.output / "extra.txt").unlink()
        (self.output / "voice/bundle/wake/model.onnx").write_bytes(b"x" * len(self.model))
        with self.assertRaises(ValueError):
            PACK.verify(self.output)

    def test_source_manifest_must_match_compiled_pin(self):
        self.manifest.write_bytes(self.manifest.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            PACK.package(self.staged, self.output)
        self.assertFalse(self.output.exists())

    def test_paths_and_symlink_escape_are_refused(self):
        for relative in ("../escape", "/absolute", "wake//model", "wake/./model", "wake\\model"):
            with self.assertRaises(ValueError):
                PACK.checked_path(self.source, relative)
        (self.source / "link").symlink_to(self.staged, target_is_directory=True)
        with self.assertRaises(ValueError):
            PACK.checked_path(self.source, "link/wake/model.onnx")

    def test_acquisition_budget_refuses_before_network(self):
        self.lock.write_text(json.dumps({"schema_version": 1, "model_archives": [], "weights": [], "raw_models": [{"size": PACK.MAX_FETCH + 1}]}))
        with patch.object(PACK.urllib.request, "urlopen") as request:
            with self.assertRaises(ValueError):
                PACK.acquire(self.root / "cache")
            request.assert_not_called()

    def test_oversized_download_is_removed_and_never_published(self):
        target = self.root / "download.onnx"
        with patch.object(PACK.urllib.request, "urlopen", return_value=io.BytesIO(b"abcde")):
            with self.assertRaises(ValueError):
                PACK.fetch("https://example.invalid/model", target, 4, hashlib.sha256(b"abcd").hexdigest())
        self.assertFalse(target.exists())
        self.assertFalse(target.with_suffix(".onnx.pending").exists())


if __name__ == "__main__":
    unittest.main()
