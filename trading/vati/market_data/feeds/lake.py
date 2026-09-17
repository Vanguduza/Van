"""Bar lake (Rev 5 Part E): one directory per symbol/timeframe of gzip CSV
slices with a manifest of sha256 per slice. Parquet arrives with the Phase 1
pyarrow adoption gate; the manifest format does not change. A backtest records
the manifest hash of every slice it consumed, so "which bytes did this run on"
is answerable from the ledger."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from vati.market_data.bars import Bar
from vati.market_data.feeds.csv_source import bars_from_csv, bars_to_csv_bytes

TIMEFRAMES_MS = {"M1": 60_000, "M5": 300_000, "M15": 900_000, "H1": 3_600_000, "H4": 14_400_000, "D1": 86_400_000}


@dataclass(frozen=True)
class LakeSlice:
    symbol: str
    timeframe: str
    start_ms: int
    end_ms: int
    bars: int
    sha256: str
    path: str
    source: str
    provenance: str = "SIMULATED_OR_UNKNOWN"   # VENUE | HISTORICAL_VENDOR | SYNTHETIC


class BarLake:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, symbol: str, timeframe: str) -> Path:
        if timeframe not in TIMEFRAMES_MS:
            raise ValueError(f"timeframe must be one of {sorted(TIMEFRAMES_MS)}")
        d = self.root / symbol.upper() / timeframe
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _manifest_path(self, symbol: str, timeframe: str) -> Path:
        return self._dir(symbol, timeframe) / "manifest.json"

    def manifest(self, symbol: str, timeframe: str) -> list[LakeSlice]:
        p = self._manifest_path(symbol, timeframe)
        if not p.is_file():
            return []
        return [LakeSlice(**s) for s in json.loads(p.read_text()).get("slices", [])]

    def write(self, bars: Iterable[Bar], *, symbol: str, timeframe: str, source: str, provenance: str) -> LakeSlice:
        bars = sorted(bars, key=lambda b: b.start_ms)
        if not bars:
            raise ValueError("no bars to write")
        if any(b.end_ms - b.start_ms != TIMEFRAMES_MS[timeframe] for b in bars):
            raise ValueError(f"bar length does not match timeframe {timeframe}")
        payload = bars_to_csv_bytes(bars)
        import gzip
        blob = gzip.compress(payload, mtime=0)   # deterministic bytes → deterministic hash
        digest = hashlib.sha256(blob).hexdigest()
        d = self._dir(symbol, timeframe)
        fname = f"{bars[0].start_ms}-{bars[-1].end_ms}-{digest[:12]}.csv.gz"
        (d / fname).write_bytes(blob)
        s = LakeSlice(symbol.upper(), timeframe, bars[0].start_ms, bars[-1].end_ms, len(bars), digest, fname, source, provenance)
        slices = [x for x in self.manifest(symbol, timeframe) if not (x.start_ms == s.start_ms and x.end_ms == s.end_ms)] + [s]
        slices.sort(key=lambda x: x.start_ms)
        self._manifest_path(symbol, timeframe).write_text(json.dumps({"symbol": symbol.upper(), "timeframe": timeframe, "slices": [x.__dict__ for x in slices]}, indent=2))
        return s

    def read(self, symbol: str, timeframe: str, *, start_ms: Optional[int] = None, end_ms: Optional[int] = None, verify: bool = True) -> tuple[list[Bar], list[str]]:
        """Returns (bars, slice hashes consumed). Verifies every slice's bytes against the manifest."""
        out: list[Bar] = []
        used: list[str] = []
        d = self._dir(symbol, timeframe)
        for s in self.manifest(symbol, timeframe):
            if end_ms is not None and s.start_ms >= end_ms:
                continue
            if start_ms is not None and s.end_ms <= start_ms:
                continue
            blob = (d / s.path).read_bytes()
            if verify and hashlib.sha256(blob).hexdigest() != s.sha256:
                raise ValueError(f"lake slice {s.path} does not match its manifest hash")
            bars = bars_from_csv(d / s.path)
            out.extend(b for b in bars if (start_ms is None or b.end_ms > start_ms) and (end_ms is None or b.start_ms < end_ms))
            used.append(s.sha256)
        dedup: dict[int, Bar] = {}
        for b in out:
            dedup[b.start_ms] = b
        return [dedup[k] for k in sorted(dedup)], used

    def symbols(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for sym in sorted(p.name for p in self.root.iterdir() if p.is_dir()):
            out[sym] = sorted(t.name for t in (self.root / sym).iterdir() if t.is_dir() and (t / "manifest.json").is_file())
        return out

    def resample(self, bars: list[Bar], *, to: str) -> list[Bar]:
        step = TIMEFRAMES_MS[to]
        groups: dict[int, list[Bar]] = {}
        for b in bars:
            groups.setdefault(b.start_ms - (b.start_ms % step), []).append(b)
        out = []
        for start in sorted(groups):
            g = sorted(groups[start], key=lambda b: b.start_ms)
            out.append(Bar(g[0].symbol, start, start + step, g[0].open, max(b.high for b in g), min(b.low for b in g), g[-1].close, sum((b.volume for b in g), g[0].volume * 0), sum(b.ticks for b in g),
                           (sum((b.avg_spread for b in g), g[0].avg_spread * 0) / len(g))))
        return out
