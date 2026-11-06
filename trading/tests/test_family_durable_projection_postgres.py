"""Original family history and publication across disposable PostgreSQL owners.

These cases require the existing explicit PostgreSQL fixture opt-in. Source
collection or a skipped fixture is not execution of the database assertions.
"""
from contextlib import ExitStack, closing
from decimal import Decimal as D

import pytest

from test_postgres_ledger_isolation import pg_dsn
from test_account_lifecycle import _lifecycle
from test_family_original_accounting import recorded_paper_partial
from test_family_durable_projection import opened, recorded_scale
from vati.core import EventKind
from vati.core.ledger_pg import PostgresLedger
from vati.lifecycle.family import (
    FamilyError, FamilyMember, FamilyRegistry, FamilyState, MemberRole,
)
from vati.risk.contracts import Direction


@pytest.mark.parametrize('netted', [False, True], ids=['original-partial', 'netted-child'])
def test_pg_cold_family_keeps_original_members_budget_and_native_protection(pg_dsn, netted):
    scope = 'original-family-recovery'
    with closing(PostgresLedger(pg_dsn, ledger_name=scope)) as writer:
        if netted:
            life, adapter, command, child, entry, _ = recorded_scale(writer, netted=True)
            expected_net, expected_gross, expected_scales = D('.11'), D('.15'), 1
        else:
            life, adapter, command, entry = recorded_paper_partial(writer)
            child = None
            expected_net, expected_gross, expected_scales = D('.06'), D('.10'), 0
        original = life.families.for_intent(command.trade_intent_id)
        members = [member.body() for member in original.members]
        count, head = writer.count(), writer.head()
        assert writer.verify_chain()[0]

    # The producing connection has closed. These are independent native owners,
    # including another ledger namespace in the same disposable database.
    with ExitStack() as stack:
        reader = stack.enter_context(closing(PostgresLedger(pg_dsn, ledger_name=scope)))
        other = stack.enter_context(closing(PostgresLedger(pg_dsn, ledger_name='foreign-family')))
        recovered = _lifecycle(reader, adapter)
        assert recovered.recover_from_venue() == ((command.trade_intent_id,), ())
        family = recovered.families.for_intent(command.trade_intent_id)
        assert family.net_quantity == expected_net
        assert family.gross_added == expected_gross and family.scale_ins == expected_scales
        assert [member.body() for member in family.members] == members
        assert recovered.entries[command.trade_intent_id]['scale_ins_used'] == expected_scales
        assert recovered.entries[command.trade_intent_id]['family_history_known'] is True
        assert not recovered.preservation_blocks_new_risk
        assert recovered.protection.stop_of(entry.broker_position_id) == command.protective_stop
        if child is not None:
            assert recovered.families.for_intent(child.trade_intent_id) is family
        assert reader.count() == count and reader.head() == head and reader.verify_chain()[0]

        foreign = _lifecycle(other, adapter)
        restored, unresolved = foreign.recover_from_venue()
        assert restored == () and unresolved == (entry.broker_position_id,)
        assert foreign.families.for_intent(command.trade_intent_id) is None
        assert foreign.preservation_blocks_new_risk and other.count() == 0
        assert reader.count() == count and reader.head() == head


def test_pg_committed_lost_ack_is_read_back_and_replay_keeps_one_add(pg_dsn, monkeypatch):
    with ExitStack() as stack:
        writer = stack.enter_context(closing(PostgresLedger(pg_dsn, ledger_name='family-lost-ack')))
        reader = stack.enter_context(closing(PostgresLedger(pg_dsn, ledger_name='family-lost-ack')))
        other = stack.enter_context(closing(PostgresLedger(pg_dsn, ledger_name='foreign-lost-ack')))
        registry, family = opened(writer)
        append = writer.append

        def committed_then_reply_lost(event):
            append(event)
            raise OSError('source fixture: PostgreSQL committed, acknowledgement lost')

        monkeypatch.setattr(writer, 'append', committed_then_reply_lost)
        member = FamilyMember('original-add', MemberRole.SCALE_IN, D(1), D(2), 2000)
        registry.apply(family.family_id, member, now_ms=2000)
        registry.apply(family.family_id, member, now_ms=2000)
        assert family.gross_added == D(2) and family.scale_ins == 1
        assert family.state is FamilyState.OPEN
        rows = list(reader.iter(EventKind.POSITION_FAMILY, correlation_id=family.family_id))
        assert len(rows) >= 2
        for event in rows[1:]:
            assert event.payload['gross_added'] == '2' and event.payload['scale_ins'] == 1
            assert [item['member_id'] for item in event.payload['members']] == ['root', 'original-add']
        assert rows[-1].payload == family.body()
        assert reader.verify_chain()[0] and writer.head() == reader.head()
        assert other.count() == 0


def _reject_family_inserts(dsn):
    """Fail inside real PostgreSQL INSERT, after normal runtime admission."""
    import psycopg
    with psycopg.connect(dsn) as connection:
        connection.execute("""
            CREATE FUNCTION vati.reject_family_publication() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'source fixture rejects family publication';
            END;
            $$
        """)
        connection.execute("""
            CREATE TRIGGER reject_family_publication
            BEFORE INSERT ON vati.events FOR EACH ROW
            WHEN (NEW.kind = 'POSITION_FAMILY')
            EXECUTE FUNCTION vati.reject_family_publication()
        """)


@pytest.mark.parametrize('operation', ['open', 'apply', 'tighten', 'reconcile'])
def test_pg_rejected_publication_cannot_publish_members_or_stop(pg_dsn, operation):
    with ExitStack() as stack:
        writer = stack.enter_context(closing(PostgresLedger(pg_dsn, ledger_name='family-rejection')))
        reader = stack.enter_context(closing(PostgresLedger(pg_dsn, ledger_name='family-rejection')))
        other = stack.enter_context(closing(PostgresLedger(pg_dsn, ledger_name='foreign-rejection')))
        if operation == 'open':
            registry, family = FamilyRegistry(ledger=writer), None
            original_members, original_stop = [], None
        else:
            registry, family = opened(writer)
            original_members = [member.body() for member in family.members]
            original_stop = family.current_stop
        before_count, before_head = reader.count(), reader.head()
        _reject_family_inserts(pg_dsn)
        with pytest.raises(FamilyError, match='persistence unresolved'):
            if operation == 'open':
                registry.open_family(family_id='f', account_alias='acct', symbol='EURUSD',
                    direction=Direction.LONG, root=FamilyMember('root', MemberRole.ROOT,
                        D(1), D(1), 1000, trade_intent_id='root', stop=D('.5')), now_ms=1000)
            elif operation == 'apply':
                registry.apply('f', FamilyMember('add', MemberRole.SCALE_IN,
                    D(1), D(2), 2000, trade_intent_id='child'), now_ms=2000)
            elif operation == 'tighten':
                registry.tighten_stop('f', D('.7'), now_ms=2000)
            else:
                registry.reconcile('f', venue_quantity=D('.5'), now_ms=2000)
        if family is None:
            assert len(registry) == 0 and registry.for_intent('root') is None
        else:
            assert [member.body() for member in family.members] == original_members
            assert family.current_stop == original_stop
            assert family.state is FamilyState.DIVERGED and not family.admits_new_risk
            assert registry.for_intent('child') is None
        assert reader.count() == before_count and reader.head() == before_head
        assert writer.head() == before_head and reader.verify_chain()[0]
        assert other.count() == 0
