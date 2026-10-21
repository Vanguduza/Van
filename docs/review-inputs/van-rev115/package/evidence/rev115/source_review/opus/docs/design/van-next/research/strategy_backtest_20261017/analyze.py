"""Score backtest runs with VAN's own validation functions (vati.backtest.metrics,
vati.validation.policy). Usage: python3 analyze.py runs2/*.json"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "van" / "trading"))

from vati.backtest.metrics import _moments, deflated_sharpe, pbo_cscv  # noqa: E402
from vati.validation.policy import ValidationStatistics, evaluate  # noqa: E402


def year(ms: int) -> int:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).year


def month(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m")


runs = [json.loads(Path(p).read_text()) for p in sys.argv[1:]]
for r in runs:
    assert len(r["r_multiples"]) == len(r["trades"]), (r["symbol"], r["strategy"], len(r["r_multiples"]), len(r["trades"]))
    r["R"] = [float(x) for x in r["r_multiples"]]
    r["T"] = [t["t"] for t in r["trades"]]

# Trials: every strategy/instrument configuration tested in this study.
srs = []
for r in runs:
    m, sd, _, _ = _moments(r["R"]) if len(r["R"]) > 1 else (0.0, 0.0, 0.0, 3.0)
    srs.append(m / sd if sd else 0.0)
sr_var = statistics.pvariance(srs) if len(srs) > 1 else 0.0

# PBO over the trial set: monthly R sums on the common month grid.
months = sorted({month(t) for r in runs for t in r["T"]})
matrix = []
for r in runs:
    by = defaultdict(float)
    for t, x in zip(r["T"], r["R"]):
        by[month(t)] += x
    matrix.append([by.get(mo, 0.0) for mo in months])
pbo = pbo_cscv(matrix, partitions=8) if len(runs) > 1 else 1.0

report = []
for r, sr in zip(runs, srs):
    R = r["R"]
    n = len(R)
    mean, sd, skew, kurt = _moments(R) if n > 1 else (0.0, 0.0, 0.0, 3.0)
    by_year = defaultdict(list)
    for t, x in zip(r["T"], R):
        by_year[year(t)].append(x)
    years = {y: {"trades": len(v), "expectancy_r": round(sum(v) / len(v), 3), "total_r": round(sum(v), 1)} for y, v in sorted(by_year.items())}
    wf_windows = len(years)
    wf_positive = sum(1 for v in years.values() if v["expectancy_r"] > 0)
    dsr = deflated_sharpe(sr, n_obs=n, skew=skew, kurtosis=kurt, n_trials=len(runs), sr_variance_across_trials=sr_var)
    stats = ValidationStatistics(observed_sharpe=sr, dsr_probability=dsr, pbo_probability=pbo, n_trials=len(runs), n_observations=n, walk_forward_windows=wf_windows)
    verdict = evaluate(stats)
    oos = [x for t, x in zip(r["T"], R) if year(t) >= 2025]
    report.append({
        "strategy": r["strategy"], "symbol": r["symbol"], "tf": r.get("tf"), "raw_lockout_disabled": r.get("raw"), "chain_ok": r.get("chain_ok"),
        "period": f"{months[0]}..{months[-1]}" if months else None, "bars": r["bars"], "seconds": r.get("seconds"),
        "trades": n, "win_rate": round(r["metrics"]["win_rate"], 3), "expectancy_r": round(mean, 3), "total_r": round(sum(R), 1),
        "profit_factor": round(r["metrics"]["profit_factor"], 2), "max_drawdown_pct": round(r["metrics"]["max_drawdown_pct"] * 100, 1),
        "net_pnl_usd_on_10k": round(r["metrics"]["net_pnl"], 0), "sharpe_per_trade": round(sr, 3),
        "dsr_probability": round(dsr, 4), "pbo_probability": round(pbo, 3),
        "years_positive": f"{wf_positive}/{wf_windows}", "by_year": years,
        "oos_2025_q1": {"trades": len(oos), "expectancy_r": round(sum(oos) / len(oos), 3) if oos else None},
        "validation_passed": verdict.passed, "validation_reasons": list(verdict.reasons), "policy": verdict.policy_version,
        "decisions": r["decisions"],
    })
print(json.dumps(report, indent=1))
