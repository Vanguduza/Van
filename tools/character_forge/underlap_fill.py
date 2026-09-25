"""CF-D-09 — generative fill for the parts of a raster layer that other layers hide.

A raster layer set is cut from one flat painting, so what lies beneath a part (the torso under
an arm, the forehead under the fringe) was never painted. Propagating edge colour into it gave
flat blobs and streaks that showed as soon as a part moved. Instead, each hidden region is
painted by LaMa (big-lama), an inpainting network, from the layer's own visible pixels only, so
it continues that layer's texture and nothing from the parts in front of it.

The fill is AI-generated and is labelled so: every layer records which method filled its
underlap, and the fills are cached, with the model's SHA-256 and a key over exactly what went
in, in the ``02-ai-working`` lane. A build without torch uses the cached fills; a cache entry
whose key no longer matches (the cut changed) is not used, and the layer falls back to
propagation and says so. Neutral-pose pixels are never touched: fills go only where a higher
layer covers them.

    python3 -m tools.character_forge.build_raster_layers --inpaint   # on a host with torch
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "visual-authority" / "character-forge" / "02-ai-working" / "raster-underlap" / "candidate_b_front"
MODEL_NAME = "big-lama"
MODEL_URL = "https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt"
MODEL_SHA256 = "7ba7aa7ac37a4d41fdbbeba3a2af7ead18058552997e3a3cd1a3b2210c9e6b4c"
DEFAULT_MODEL = Path(os.environ.get("VAN_FORGE_LAMA", "/var/lib/dial-character-forge/models/big-lama.pt"))
#: Context kept around a region, in native pixels, so the network sees the texture it continues.
MARGIN = 24


def fill_key(name: str, rgb: np.ndarray, known: np.ndarray, hidden: np.ndarray) -> str:
    """A digest of exactly what the fill depends on: the layer, its visible pixels and the hole."""
    digest = hashlib.sha256()
    digest.update(f"{MODEL_SHA256}:{name}:{rgb.shape}".encode())
    digest.update(np.packbits(known).tobytes())
    digest.update(np.packbits(hidden).tobytes())
    digest.update(np.round(np.where(known[..., None], rgb, 0) * 255).astype(np.uint8).tobytes())
    return digest.hexdigest()


class Inpainter:
    """big-lama as TorchScript, loaded once and pinned by SHA-256."""

    def __init__(self, model: Path = DEFAULT_MODEL) -> None:
        import torch  # a forge-host dependency, never needed in CI

        data = Path(model).read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != MODEL_SHA256:
            raise ValueError(f"{model}: sha256 {actual} is not the pinned {MODEL_NAME} {MODEL_SHA256}")
        torch.manual_seed(0)
        self._torch = torch
        self._net = torch.jit.load(str(model), map_location="cpu").eval()

    def __call__(self, rgb: np.ndarray, known: np.ndarray, hidden: np.ndarray) -> np.ndarray:
        torch = self._torch
        ys, xs = np.nonzero(known | hidden)
        h, w = known.shape
        y0, y1 = max(0, ys.min() - MARGIN), min(h, ys.max() + 1 + MARGIN)
        x0, x1 = max(0, xs.min() - MARGIN), min(w, xs.max() + 1 + MARGIN)
        ch, cw = y1 - y0, x1 - x0
        ph, pw = -ch % 8, -cw % 8
        img = np.zeros((ch + ph, cw + pw, 3), np.float32)
        hole = np.ones((ch + ph, cw + pw), np.float32)
        k = known[y0:y1, x0:x1]
        img[:ch, :cw][k] = rgb[y0:y1, x0:x1][k]
        hole[:ch, :cw][k] = 0.0
        with torch.inference_mode():
            out = self._net(torch.from_numpy(img).permute(2, 0, 1)[None], torch.from_numpy(hole)[None, None])
        painted = out[0].permute(1, 2, 0).numpy()[:ch, :cw]
        result = rgb.copy()
        region = hidden[y0:y1, x0:x1]
        result[y0:y1, x0:x1][region] = np.clip(painted[region], 0.0, 1.0)
        return result


class FillCache:
    """Fills keyed by :func:`fill_key`, stored as one RGBA PNG per layer (alpha marks the fill)."""

    def __init__(self, directory: Path = CACHE_DIR) -> None:
        self.directory = directory
        self.index_path = directory / "FILLS.json"
        try:
            self.index = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.index = {"model": MODEL_NAME, "model_url": MODEL_URL, "model_sha256": MODEL_SHA256, "fills": {}}

    def get(self, name: str, key: str, hidden: np.ndarray) -> np.ndarray | None:
        row = (self.index.get("fills") or {}).get(name)
        if not row or row.get("key") != key or self.index.get("model_sha256") != MODEL_SHA256:
            return None
        path = self.directory / row["file"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row.get("sha256"):
            return None
        x0, y0 = row["offset_px"]
        tile = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32) / 255.0
        out = np.zeros(hidden.shape + (3,), np.float32)
        out[y0:y0 + tile.shape[0], x0:x0 + tile.shape[1]] = tile[..., :3]
        return out

    def put(self, name: str, key: str, filled: np.ndarray, hidden: np.ndarray) -> np.ndarray:
        """Store the fill and return it exactly as a later build will read it back (8-bit)."""
        ys, xs = np.nonzero(hidden)
        y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
        tile = np.zeros((y1 - y0, x1 - x0, 4), np.uint8)
        region = hidden[y0:y1, x0:x1]
        tile[..., :3][region] = (np.clip(filled[y0:y1, x0:x1][region], 0, 1) * 255 + 0.5).astype(np.uint8)
        tile[..., 3][region] = 255
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{name}.png"
        Image.fromarray(tile, "RGBA").save(path, format="PNG", optimize=True)
        self.index.setdefault("fills", {})[name] = {
            "key": key, "file": path.name, "offset_px": [x0, y0], "size_px": [x1 - x0, y1 - y0],
            "pixels": int(hidden.sum()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        self.index.update({"model": MODEL_NAME, "model_url": MODEL_URL, "model_sha256": MODEL_SHA256})
        self.index_path.write_text(json.dumps(self.index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return self.get(name, key, hidden)
