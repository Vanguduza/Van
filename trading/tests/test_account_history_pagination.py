"""BE-006: read-only retained-incarnation history pagination.

Source: AccountRegistry.history_page in trading/vati/accounts/registry.py.
History is built only through the registry's real writers (restriction_update
+ remove/add rotation for restrictions; lifecycle_update rotation for
lifecycles), never by editing the file or the in-memory maps. PAPER metadata
only; no live provider, no mandate, no money.
"""
import copy
import json
import threading

import pytest

from vati.accounts import Account, AccountRegistry
from vati.accounts.registry import (
    AccountRegistryError,
    HISTORY_PAGE_SCHEMA,
    _decode_history_cursor,
    _encode_history_cursor,
)
from vati.accounts.resource_version import resource_snapshot
from vati.accounts.restrictions import initial_record
from vati.core.canonical import canonical_hash
from test_account_restrictions import ALIAS, paper

HEX64 = "1" * 64


def _restrict(registry, alias, operation_id, now):
    value = initial_record(
        alias=alias, operation_id=operation_id, device_id="source-device",
        domain=HEX64, resource_version=resource_snapshot(registry, alias)["resource_version"],
        request_digest="2" * 64, review_digest="3" * 64, admission_digest="4" * 64,
        reason_code="OWNER_REQUEST", now=now,
    )

    def change(current):
        from dataclasses import replace

        current._restrictions[alias] = value
        current.accounts[alias] = replace(current.get(alias), enabled=False)

    registry.restriction_update(alias, change)
    return value


def _rotate_restriction(registry, alias):
    registry.remove(alias)
    registry.add(Account(alias, "PAPER", "DEMO_TRADER", "USD"))


def restriction_history_registry(tmp_path, rows=3):
    """Registry whose restriction history holds ``rows`` rows; returns (registry, history_ids, current_id)."""
    registry = paper(tmp_path)
    ids = []
    for i in range(rows + 1):
        operation_id = f"restriction_original_{i:06d}"
        _restrict(registry, ALIAS, operation_id, 100 + i)
        ids.append(operation_id)
        if i < rows:
            _rotate_restriction(registry, ALIAS)
    return registry, ids[:-1], ids[-1]


def lifecycle_history_registry(tmp_path, rows=3):
    """Registry whose lifecycle history holds ``rows`` rows; returns (registry, history_ids)."""
    from test_account_strategy_detachment import detached

    registry, account, original = detached(tmp_path)
    for i in range(rows):
        operation_id = f"later_lifecycle_{i:08d}"
        incarnation = f"{i + 3}" * 64

        def rotate(current, operation_id=operation_id, incarnation=incarnation):
            old = copy.deepcopy(current._lifecycles[account.alias])
            newer = copy.deepcopy(old)
            newer.update(operation_id=operation_id, incarnation=incarnation)
            current._lifecycle_history[old["operation_id"]] = old
            current._lifecycles[account.alias] = newer

        registry.lifecycle_update(account.alias, rotate)
    history = AccountRegistry(registry.path)._lifecycle_history
    ordered = sorted(history.values(), key=lambda row: (row["created_at_unix"], row["operation_id"]))
    return registry, [row["operation_id"] for row in ordered]


def _walk(registry, alias, kind, limit):
    ids, pages = [], []
    cursor = None
    while True:
        page = registry.history_page(alias, kind=kind, limit=limit, cursor=cursor)
        pages.append(page)
        ids.extend(entry["source_key"] for entry in page["entries"])
        if page["next_cursor"] is None:
            break
        cursor = page["next_cursor"]
    return ids, pages


def test_empty_history_is_an_empty_page_with_no_cursor(tmp_path):
    registry = paper(tmp_path)
    page = registry.history_page(ALIAS, kind="restriction")
    assert page == {
        "schema": HISTORY_PAGE_SCHEMA, "alias": ALIAS, "kind": "restriction",
        "venue": "paper", "source_revision": 1,
        "source_digest": page["source_digest"], "total": 0, "entries": [],
        "has_more": False, "next_cursor": None,
    }
    assert registry.history_page(ALIAS, kind="lifecycle")["total"] == 0


def test_restriction_history_multi_page_walk_is_exact_and_ordered(tmp_path):
    registry, history_ids, current_id = restriction_history_registry(tmp_path, rows=3)
    ids, pages = _walk(registry, ALIAS, "restriction", limit=2)
    assert ids == history_ids
    assert [len(page["entries"]) for page in pages] == [2, 1]
    assert [page["has_more"] for page in pages] == [True, False]
    assert current_id not in ids
    first = pages[0]
    assert first["total"] == 3 and first["source_revision"] >= 1
    assert [entry["restriction_id"] for entry in first["entries"]] == history_ids[:2]
    assert all(entry["entry_permitted"] is False for entry in first["entries"])
    assert all(entry["mode_or_mandate_granted"] is False for entry in first["entries"])


def test_lifecycle_history_pagination_uses_canonical_order(tmp_path):
    registry, history_ids = lifecycle_history_registry(tmp_path, rows=3)
    ids, pages = _walk(registry, ALIAS, "lifecycle", limit=1)
    assert ids == history_ids
    assert len(pages) == 3
    assert all(entry["execution_authority"] is False for page in pages for entry in page["entries"])
    assert all(entry["financial_history_retained"] is True for page in pages for entry in page["entries"])


def test_replaying_a_cursor_returns_the_identical_page(tmp_path):
    registry, history_ids, _ = restriction_history_registry(tmp_path, rows=3)
    first = registry.history_page(ALIAS, kind="restriction", limit=2)
    again = registry.history_page(ALIAS, kind="restriction", limit=2, cursor=first["next_cursor"])
    replay = registry.history_page(ALIAS, kind="restriction", limit=2, cursor=first["next_cursor"])
    assert again == replay
    assert [entry["source_key"] for entry in again["entries"]] == history_ids[2:]
    assert again["next_cursor"] is None
    # Re-walking from the start after the interruption reproduces page one.
    assert registry.history_page(ALIAS, kind="restriction", limit=2) == first


@pytest.mark.parametrize("limit", [0, -1, 101, 1000, "2", 2.0, True, None])
def test_invalid_limit_refuses(tmp_path, limit):
    registry = paper(tmp_path)
    with pytest.raises(AccountRegistryError, match="limit is invalid"):
        registry.history_page(ALIAS, kind="restriction", limit=limit)


@pytest.mark.parametrize("kind", ["all", "account", "", None, 1])
def test_invalid_kind_refuses(tmp_path, kind):
    registry = paper(tmp_path)
    with pytest.raises(AccountRegistryError, match="kind is invalid"):
        registry.history_page(ALIAS, kind=kind)


def test_unknown_or_malformed_alias_refuses(tmp_path):
    registry = paper(tmp_path)
    for alias in ["unknown_alias", "BAD", "x", "", None, 42]:
        with pytest.raises(AccountRegistryError):
            registry.history_page(alias, kind="restriction")


@pytest.mark.parametrize("cursor", ["", "not-a-cursor", "aaaa.bbbb", "!!!.0123456789abcdef0123456789abcdef", None.__class__ and 123])
def test_malformed_cursor_refuses(tmp_path, cursor):
    registry, _, _ = restriction_history_registry(tmp_path, rows=2)
    with pytest.raises(AccountRegistryError, match="cursor is malformed, foreign or stale"):
        registry.history_page(ALIAS, kind="restriction", limit=1, cursor=cursor)


def test_tampered_cursor_refuses(tmp_path):
    registry, _, _ = restriction_history_registry(tmp_path, rows=3)
    page = registry.history_page(ALIAS, kind="restriction", limit=1)
    body, check = page["next_cursor"].rsplit(".", 1)
    tampered = body + "." + ("0" * 32 if check != "0" * 32 else "1" * 32)
    with pytest.raises(AccountRegistryError, match="cursor is malformed, foreign or stale"):
        registry.history_page(ALIAS, kind="restriction", limit=1, cursor=tampered)


def test_foreign_cursor_from_another_alias_or_kind_refuses(tmp_path):
    registry, _, _ = restriction_history_registry(tmp_path, rows=3)
    registry.add(Account("other_owner", "PAPER", "OBSERVE", "USD"))
    page = registry.history_page(ALIAS, kind="restriction", limit=1)
    with pytest.raises(AccountRegistryError, match="cursor is malformed, foreign or stale"):
        registry.history_page("other_owner", kind="restriction", limit=1, cursor=page["next_cursor"])
    with pytest.raises(AccountRegistryError, match="cursor is malformed, foreign or stale"):
        registry.history_page(ALIAS, kind="lifecycle", limit=1, cursor=page["next_cursor"])


def test_cursor_with_unknown_last_key_refuses(tmp_path):
    registry, _, _ = restriction_history_registry(tmp_path, rows=2)
    page = registry.history_page(ALIAS, kind="restriction", limit=1)
    forged = _encode_history_cursor({
        "schema": HISTORY_PAGE_SCHEMA, "alias": ALIAS, "kind": "restriction",
        "venue": "paper", "source_revision": page["source_revision"],
        "source_digest": page["source_digest"], "index": 99, "last_key": "restriction_original_999999",
    })
    with pytest.raises(AccountRegistryError, match="cursor is malformed, foreign or stale"):
        registry.history_page(ALIAS, kind="restriction", limit=1, cursor=forged)


def test_stale_cursor_after_a_writer_appends_refuses(tmp_path):
    registry, history_ids, _ = restriction_history_registry(tmp_path, rows=3)
    first = registry.history_page(ALIAS, kind="restriction", limit=1)
    # A genuine writer rotation appends a new historical incarnation.
    _rotate_restriction(registry, ALIAS)
    _restrict(registry, ALIAS, "restriction_original_000099", 200)
    with pytest.raises(AccountRegistryError, match="cursor is malformed, foreign or stale"):
        registry.history_page(ALIAS, kind="restriction", limit=1, cursor=first["next_cursor"])
    # A fresh walk sees the new snapshot, in order, with no duplicates.
    ids, _ = _walk(registry, ALIAS, "restriction", limit=2)
    assert ids == history_ids + ["restriction_original_000003"]


def test_cold_restart_returns_identical_pages_and_cursors(tmp_path):
    registry, history_ids, _ = restriction_history_registry(tmp_path, rows=3)
    first = registry.history_page(ALIAS, kind="restriction", limit=2)
    cold = AccountRegistry(registry.path)
    assert cold.history_page(ALIAS, kind="restriction", limit=2) == first
    assert cold.history_page(ALIAS, kind="restriction", limit=2, cursor=first["next_cursor"]) == registry.history_page(
        ALIAS, kind="restriction", limit=2, cursor=first["next_cursor"]
    )
    assert cold._restriction_history == registry._restriction_history


def test_paging_is_read_only_and_cannot_mutate_returned_entries(tmp_path):
    registry, history_ids, _ = restriction_history_registry(tmp_path, rows=3)
    before = registry.path.read_bytes()
    page = registry.history_page(ALIAS, kind="restriction", limit=2)
    page["entries"][0]["restriction_id"] = "forged"
    page["entries"][0]["phase"] = "LINKED_READ_ONLY"
    assert registry.path.read_bytes() == before
    again = registry.history_page(ALIAS, kind="restriction", limit=2)
    assert [entry["source_key"] for entry in again["entries"]] == history_ids[:2]
    assert again["entries"][0]["phase"] == "RESTRICTED"
    assert AccountRegistry(registry.path).get(ALIAS).enabled is False


def test_concurrent_readers_get_identical_walks(tmp_path):
    registry, history_ids, _ = restriction_history_registry(tmp_path, rows=3)
    results, errors = [], []

    def walk():
        try:
            ids, _ = _walk(AccountRegistry(registry.path), ALIAS, "restriction", limit=1)
            results.append(ids)
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=walk) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
        assert not thread.is_alive()
    assert not errors
    assert results == [history_ids] * 4


def test_page_contains_no_secrets_and_no_grant(tmp_path):
    registry, _, _ = restriction_history_registry(tmp_path, rows=2)
    page = registry.history_page(ALIAS, kind="restriction", limit=2)
    blob = json.dumps(page)
    for forbidden in ("password", "token", "api_key", "api-key", "secret", "mandate_ref", "credential"):
        assert forbidden not in blob.lower()
    assert all(entry["entry_permitted"] is False for entry in page["entries"])
    assert all(entry["account_control_domain"] == HEX64 for entry in page["entries"])
    assert page["venue"] == "paper"
    rows = sorted(
        registry._restriction_history.values(),
        key=lambda row: (row["created_at_unix"], row["restriction_id"]),
    )
    assert page["source_digest"] == canonical_hash({
        "alias": ALIAS, "kind": "restriction",
        "revision": page["source_revision"], "rows": rows,
    })
