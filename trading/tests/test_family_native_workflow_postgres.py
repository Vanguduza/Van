"""Real PostgreSQL boundaries; synthetic SOURCE policy/native-owner fixtures."""
import pytest
from test_postgres_ledger_isolation import pg_dsn
from vati.core.ledger_pg import PostgresLedger


@pytest.mark.parametrize('case',[
    'governed_add_partial_full','mark_stop_loss','cold_open','cold_flat',
    'unknown_independent_leg','committed_peer_revoke','pending_first_fact','late_source_owner_fact',
    'explicit_signed_targets','cold_optional_expiry','cold_independent_stops','independent_stop_fence',
    'venue_unavailable','preexisting_unknown_applied','preexisting_unknown_unobserved','partial_writer_race'])
def test_actual_family_workflow_uses_postgres_original_writer_and_committed_readers(pg_dsn,tmp_path,monkeypatch,case):
    import test_active_trade_e2e as runtime_fixture
    # Storage changes before the actual entry/risk/ADD producer executes.
    monkeypatch.setattr(runtime_fixture,'Ledger',lambda path:PostgresLedger(pg_dsn,ledger_name='source-family-workflow'))
    import test_family_governed_workflow as governed
    import test_family_native_supervision as supervisor
    import test_family_unknown_independence as unknown
    import test_family_outcome_restatements as economics
    cases={
        'partial_writer_race':lambda:unknown.test_partial_dispatch_rereads_new_other_leg_unknown_under_current_writer(tmp_path,monkeypatch),
        'venue_unavailable':lambda:unknown.test_optional_native_identity_read_unavailable_does_not_gate_actual_protective_close(tmp_path,monkeypatch),
        'preexisting_unknown_applied':lambda:unknown.test_preexisting_independent_unknown_cannot_block_new_mandatory_other_leg_close(tmp_path,monkeypatch,True),
        'preexisting_unknown_unobserved':lambda:unknown.test_preexisting_independent_unknown_cannot_block_new_mandatory_other_leg_close(tmp_path,monkeypatch,False),
        'explicit_signed_targets':lambda:governed.test_explicit_original_targets_need_distinct_exact_signed_authority_and_replay_once(tmp_path),
        'cold_optional_expiry':lambda:supervisor.test_cold_optional_policy_expiry_does_not_disable_existing_mandatory_family_protection(tmp_path),
        'cold_independent_stops':lambda:supervisor.test_cold_expired_optional_policy_keeps_independent_native_stops_in_one_original_trial(tmp_path),
        'independent_stop_fence':lambda:supervisor.test_independent_tighten_rechecks_current_lease_before_each_native_effect(tmp_path,monkeypatch),
        'governed_add_partial_full':lambda:governed.test_real_add_then_proportional_residual_then_all_native_legs_close_once(tmp_path),
        'mark_stop_loss':lambda:supervisor.test_missing_native_stop_forces_full_family_close_without_partial_policy_admission(tmp_path),
        'cold_open':lambda:supervisor.test_cold_recovery_restores_original_membership_and_full_native_targets(tmp_path),
        'cold_flat':lambda:supervisor.test_cold_flat_recovery_reduces_original_receipts_and_consumes_once_after_policy_expiry(tmp_path,monkeypatch),
        'unknown_independent_leg':lambda:unknown.test_original_unknown_full_target_is_not_resent_and_other_full_leg_executes(tmp_path,monkeypatch),
        'committed_peer_revoke':lambda:unknown.test_committed_other_writer_revocation_refuses_next_target_but_native_stop_survives(tmp_path,monkeypatch),
        'pending_first_fact':lambda:economics.test_pending_actual_owner_read_then_first_qualified_outcome_one_trial(tmp_path),
        'late_source_owner_fact':lambda:economics.test_source_owner_late_cash_revision_replaces_same_parent_without_new_trial(tmp_path)}
    if case=='committed_peer_revoke':
        monkeypatch.setattr(unknown,'Ledger',lambda path:PostgresLedger(pg_dsn,ledger_name='source-family-workflow'))
    cases[case]()
