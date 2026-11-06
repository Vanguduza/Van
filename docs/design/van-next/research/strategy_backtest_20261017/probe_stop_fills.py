"""Measure how far paper STOP fills land beyond their trigger, in R (London breakout, EURUSD, 8,000 H1 bars)."""
import sys, json, statistics
from decimal import Decimal as D
sys.argv = ["x"]
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))   # harness.py, van/trading and data/ beside this file
import harness
from vati.core import EventKind
import vati.core.ledger as L
made = []
orig = L.Ledger.__init__
def init(self, *a, **k):
    orig(self, *a, **k); made.append(self)
L.Ledger.__init__ = init
harness.Ledger = L.Ledger
sym = "EURUSD"
bars = harness.load_bars(sym, "H1", "2018-07-01", "2025-03-22")[:8000]
out = harness.run(sym, "FX-LONDON-BREAKOUT-01", bars, 400, raw=True)
led = made[-1]
cmds = {e.correlation_id: e.payload for e in led.iter(EventKind.ORDER_COMMAND)}
gaps = []
for e in led.iter(EventKind.EXECUTION_RECEIPT):
    p = e.payload
    if p.get("reject_reason") == "PENDING_FILLED":
        c = cmds[e.correlation_id]
        trig, fill, stop = D(c["entry_price"]), D(p["average_fill"]), D(c["protective_stop"])
        risk = abs(trig - stop)
        gaps.append(float(abs(fill - trig) / risk))
print("trades", out["metrics"]["trades"], "expR", out["metrics"]["expectancy_r"])
print("stop fills", len(gaps), "fill beyond trigger, in R: median", round(statistics.median(gaps), 3), "mean", round(statistics.mean(gaps), 3), "p90", round(sorted(gaps)[int(.9*len(gaps))], 3))
