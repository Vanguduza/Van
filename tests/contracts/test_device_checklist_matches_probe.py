"""The physical checklist the owner fills and the probe that reports it name the same items.

They had drifted apart from the product: the probe still listed only the items written before
provisioning, the wake word and the Candidate B / flame-aura embodiment existed, so a device run
could "complete" the checklist without exercising any of them.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKLIST_MD = ROOT / "docs" / "DEVICE_ACCEPTANCE_CHECKLIST.md"
PROBE = ROOT / "tools" / "certification" / "device_cert_probe.py"


def _probe():
    spec = importlib.util.spec_from_file_location("device_cert_probe", PROBE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows() -> list[str]:
    rows = []
    for line in CHECKLIST_MD.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\|\s*([a-z_0-9]+)\s*\|", line)
        if match:
            rows.append(match.group(1))
    return rows


def test_the_doc_and_the_probe_list_the_same_items_in_the_same_order() -> None:
    assert _rows() == _probe().CHECKLIST


def test_the_checklist_covers_the_features_a_device_run_must_exercise() -> None:
    for item in ("provisioning", "wake_word", "embodiment_candidate_b", "flame_aura",
                 "trading_aura_overlay", "biometric", "offline_queue", "reconnect"):
        assert item in _probe().CHECKLIST


def test_the_probe_only_counts_the_target_handset() -> None:
    assert _probe().TARGET_MODEL_PREFIX == "SM-S928"
