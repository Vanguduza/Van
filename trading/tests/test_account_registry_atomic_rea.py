"""Regression tests for financial account registry mutation safety.

Local registration is not broker account creation; removing a record does not close
a broker account. Never assert a broker-side effect from registry mutations.
"""
from __future__ import annotations

import json
import os

import pytest

from vati.accounts.registry import Account, AccountRegistry, AccountRegistryError


def paper(alias: str = "paper_demo", label: str = "Paper demo") -> Account:
    return Account(alias=alias, broker="PAPER", mode="DEMO_TRADER", currency="USD", label=label)


def test_replace_validates_before_any_registry_mutation(tmp_path):
    path = tmp_path / "accounts.json"
    registry = AccountRegistry(path)
    registry.add(paper())
    before = path.read_bytes()

    with pytest.raises(AccountRegistryError, match="unknown broker"):
        registry.replace(Account(alias="paper_demo", broker="NOT_A_BROKER", mode="DEMO_TRADER", currency="USD"))
    assert path.read_bytes() == before
    assert registry.get("paper_demo").label == "Paper demo"

    registry.replace(paper(label="Renamed locally"))
    assert registry.get("paper_demo").label == "Renamed locally"
    assert json.loads(path.read_text())["accounts"][0]["label"] == "Renamed locally"


def test_failed_atomic_swap_does_not_destroy_old_registry(tmp_path, monkeypatch):
    path = tmp_path / "accounts.json"
    registry = AccountRegistry(path)
    registry.add(paper())
    original = path.read_bytes()

    def fail_replace(*_args):
        raise OSError("simulated interrupted persistent write")

    monkeypatch.setattr("vati.accounts.registry.os.replace", fail_replace)
    with pytest.raises(OSError, match="interrupted"):
        registry.replace(paper(label="Must not persist"))
    assert registry.get("paper_demo").label == "Paper demo"
    assert path.read_bytes() == original
    assert list(tmp_path.glob(".accounts.json.*.tmp")) == []

    with pytest.raises(OSError, match="interrupted"):
        registry.remove("paper_demo")
    assert registry.get("paper_demo").label == "Paper demo"
    assert path.read_bytes() == original


def test_new_registry_file_is_owner_only_and_is_valid_json(tmp_path):
    path = tmp_path / "accounts.json"
    registry = AccountRegistry(path)
    registry.add(paper())
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert AccountRegistry(path).get("paper_demo").label == "Paper demo"


def test_upsert_alternative_is_explicit_replace_only(tmp_path):
    path = tmp_path / "accounts.json"
    registry = AccountRegistry(path)
    with pytest.raises(AccountRegistryError, match="unknown account alias"):
        registry.replace(paper())
    registry.add(paper())
    with pytest.raises(AccountRegistryError, match="already registered"):
        registry.add(paper(label="Should not overwrite"))
    assert registry.get("paper_demo").label == "Paper demo"
