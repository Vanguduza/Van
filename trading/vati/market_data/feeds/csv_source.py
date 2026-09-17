from __future__ import annotations

import csv
import gzip
import io
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from vati.market_data.bars import Bar

COLUMNS = ["symbol", "start_ms", "end_ms", "open", "high", "low", "close", "volume", "ticks", "avg_spread"]


def _open(path: Path, mode: str):
    return gzip.open(path, mode + "t", encoding="utf-8", newline="") if str(path).endswith(".gz") else open(path, mode, newline="", encoding="utf-8")


def bars_from_csv(path: str | Path) -> list[Bar]:
    out = []
    with _open(Path(path), "r") as f:
        for r in csv.DictReader(f):
            out.append(Bar(r["symbol"], int(r["start_ms"]), int(r["end_ms"]), Decimal(r["open"]), Decimal(r["high"]), Decimal(r["low"]), Decimal(r["close"]),
                           Decimal(r.get("volume") or "0"), int(r.get("ticks") or 1), Decimal(r.get("avg_spread") or "0")))
    return out


def bars_to_csv(bars: Iterable[Bar], path: str | Path) -> int:
    n = 0
    with _open(Path(path), "w") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for b in bars:
            w.writerow([b.symbol, b.start_ms, b.end_ms, b.open, b.high, b.low, b.close, b.volume, b.ticks, b.avg_spread]); n += 1
    return n


def bars_to_csv_bytes(bars: Iterable[Bar]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf); w.writerow(COLUMNS)
    for b in bars:
        w.writerow([b.symbol, b.start_ms, b.end_ms, b.open, b.high, b.low, b.close, b.volume, b.ticks, b.avg_spread])
    return buf.getvalue().encode()
