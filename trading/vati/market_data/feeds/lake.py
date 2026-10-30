"""Bar lake (Rev 5 Part E): one directory per symbol/timeframe of gzip CSV
slices with a manifest of sha256 per slice. Parquet arrives with the Phase 1
pyarrow adoption gate; the manifest format does not change. A backtest records
the manifest hash of every slice it consumed, so "which bytes did this run on"
is answerable from the ledger."""

from __future__ import annotations

import hashlib
import json
import gzip
import os
import re
import tempfile
from decimal import InvalidOperation
from urllib.parse import quote, unquote
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from vati.market_data.bars import Bar
from vati.market_data.feeds.csv_source import bars_from_csv_bytes, bars_to_csv_bytes
from vati.core.file_lock import exclusive_state_lock

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
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _symbol(symbol: str) -> str:
        if not isinstance(symbol, str) or not symbol or symbol in {".", ".."} or "\x00" in symbol or len(symbol) > 256:
            raise ValueError("invalid lake symbol")
        return symbol.upper()

    def _dir(self, symbol: str, timeframe: str) -> Path:
        if timeframe not in TIMEFRAMES_MS:
            raise ValueError(f"timeframe must be one of {sorted(TIMEFRAMES_MS)}")
        # Preserve historical plain-symbol paths; encode separators rather than
        # letting provider identifiers become directory traversal instructions.
        d = self.root / quote(self._symbol(symbol), safe="") / timeframe
        if not d.resolve().is_relative_to(self.root):
            raise ValueError("lake partition escapes root")
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _manifest_path(self, symbol: str, timeframe: str) -> Path:
        return self._dir(symbol, timeframe) / "manifest.json"

    def manifest(self, symbol: str, timeframe: str) -> list[LakeSlice]:
        p = self._manifest_path(symbol, timeframe)
        if not p.is_file():
            return []
        if p.is_symlink():
            raise ValueError("lake manifest must not be a symlink")
        try:
            data = json.loads(p.read_text())
            canonical = self._symbol(symbol)
            if data["symbol"] != canonical or data["timeframe"] != timeframe or not isinstance(data["slices"], list):
                raise ValueError("lake manifest identity mismatch")
            slices = [LakeSlice(**row) for row in data["slices"]]
            for item in slices:
                if (item.symbol != canonical or item.timeframe != timeframe
                    or any(type(v) is not int for v in [item.start_ms, item.end_ms, item.bars])
                    or item.end_ms <= item.start_ms or item.bars < 1
                    or not isinstance(item.path, str) or Path(item.path).name != item.path
                    or not re.fullmatch(r"-?[0-9]+--?[0-9]+-[0-9a-f]{12,64}\.csv\.gz", item.path)
                    or not isinstance(item.sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", item.sha256)
                    or not isinstance(item.source, str) or not item.source
                    or not isinstance(item.provenance, str) or not item.provenance):
                    raise ValueError("lake slice manifest is invalid")
            if len({item.path for item in slices}) != len(slices):
                raise ValueError("duplicate lake slice identity")
            return slices
        except (KeyError, TypeError) as exc:
            raise ValueError("lake manifest is invalid") from exc

    @staticmethod
    def _validate_bars(bars: list[Bar], symbol: str, timeframe: str) -> None:
        if not bars:
            raise ValueError("no bars to write")
        seen = set()
        for bar in bars:
            if bar.symbol.upper() != symbol:
                raise ValueError("bar instrument differs from lake symbol")
            if type(bar.start_ms) is not int or type(bar.end_ms) is not int or bar.end_ms-bar.start_ms != TIMEFRAMES_MS[timeframe]:
                raise ValueError(f"bar length does not match timeframe {timeframe}")
            if bar.start_ms in seen:
                raise ValueError("duplicate bar interval")
            seen.add(bar.start_ms)
            values = [bar.open, bar.high, bar.low, bar.close, bar.volume, bar.avg_spread]
            if any(not value.is_finite() for value in values):
                raise ValueError("bar values must be finite")
            if (bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close)
                or bar.high < bar.low or bar.volume < 0 or bar.avg_spread < 0
                or type(bar.ticks) is not int or bar.ticks < 0):
                raise ValueError("bar market values are inconsistent")

    @staticmethod
    def _atomic_write(path: Path, payload: bytes) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".lake-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            if os.name != "nt":
                fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def write(self, bars: Iterable[Bar], *, symbol: str, timeframe: str, source: str, provenance: str) -> LakeSlice:
        canonical = self._symbol(symbol)
        if timeframe not in TIMEFRAMES_MS:
            raise ValueError(f"timeframe must be one of {sorted(TIMEFRAMES_MS)}")
        bars = sorted(bars, key=lambda bar: bar.start_ms)
        self._validate_bars(bars, canonical, timeframe)
        if not isinstance(source, str) or not source or not isinstance(provenance, str) or not provenance:
            raise ValueError("source and provenance are required")
        blob = gzip.compress(bars_to_csv_bytes(bars), mtime=0)
        digest = hashlib.sha256(blob).hexdigest()
        d = self._dir(canonical, timeframe)
        manifest = self._manifest_path(canonical, timeframe)
        # Reuse the existing cross-process state-file lock; atomic replacement
        # protects readers, while the lock protects concurrent appenders.
        if manifest.is_symlink():
            raise ValueError("lake manifest must not be a symlink")
        with exclusive_state_lock(manifest):
            slices = self.manifest(canonical, timeframe)
            fname = f"{bars[0].start_ms}-{bars[-1].end_ms}-{digest}.csv.gz"
            self._atomic_write(d / fname, blob)
            item = LakeSlice(canonical, timeframe, bars[0].start_ms, bars[-1].end_ms, len(bars), digest, fname, source, provenance)
            slices = [old for old in slices if (old.start_ms,old.end_ms) != (item.start_ms,item.end_ms)] + [item]
            slices.sort(key=lambda old: (old.start_ms, old.end_ms, old.path))
            self._atomic_write(manifest, json.dumps({"symbol": canonical, "timeframe": timeframe, "slices": [old.__dict__ for old in slices]}, indent=2).encode())
            return item

    def read(self, symbol: str, timeframe: str, *, start_ms: Optional[int] = None, end_ms: Optional[int] = None, verify: bool = True) -> tuple[list[Bar], list[str]]:
        """Read one manifest snapshot; hash and parse each exact captured blob.

        ``verify=False`` skips only the digest comparison, never identity, path
        or market-value checks. It does not qualify data for research or trading.
        """
        out: list[Bar] = []
        used: list[str] = []
        d = self._dir(symbol, timeframe)
        for item in self.manifest(symbol, timeframe):
            if end_ms is not None and item.start_ms >= end_ms:
                continue
            if start_ms is not None and item.end_ms <= start_ms:
                continue
            path = d / item.path
            if path.is_symlink() or not path.resolve().is_relative_to(d.resolve()):
                raise ValueError("lake slice escapes partition")
            blob = path.read_bytes()
            if verify and hashlib.sha256(blob).hexdigest() != item.sha256:
                raise ValueError(f"lake slice {item.path} does not match its manifest hash")
            try:
                bars = bars_from_csv_bytes(gzip.decompress(blob))
                self._validate_bars(bars, self._symbol(symbol), timeframe)
                if (len(bars), bars[0].start_ms, bars[-1].end_ms) != (item.bars,item.start_ms,item.end_ms):
                    raise ValueError("lake slice metadata differs from captured bars")
                if bars != sorted(bars, key=lambda bar: bar.start_ms):
                    raise ValueError("lake slice bars are not ordered")
            except (KeyError, TypeError, InvalidOperation) as exc:
                raise ValueError("lake slice data is invalid") from exc
            out.extend(bar for bar in bars if (start_ms is None or bar.end_ms > start_ms) and (end_ms is None or bar.start_ms < end_ms))
            used.append(item.sha256)
        dedup: dict[int, Bar] = {}
        for bar in out:
            previous = dedup.get(bar.start_ms)
            if previous is not None and previous != bar:
                raise ValueError("conflicting overlapping lake slices require reconciliation")
            dedup[bar.start_ms] = bar
        return [dedup[key] for key in sorted(dedup)], used

    def symbols(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for path in sorted(self.root.iterdir()):
            if not path.is_dir() or path.is_symlink():
                continue
            symbol = unquote(path.name)
            if quote(self._symbol(symbol), safe="") != path.name:
                continue
            out[symbol] = sorted(t.name for t in path.iterdir() if t.is_dir() and not t.is_symlink() and t.name in TIMEFRAMES_MS and (t / "manifest.json").is_file())
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
