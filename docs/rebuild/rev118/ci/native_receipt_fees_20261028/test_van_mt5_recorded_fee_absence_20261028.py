"""Next-packet counterexamples; source fixtures, never live MT5 evidence."""
from decimal import Decimal as D
from test_mt5_physical_identity import build
from test_mt5_explicit_entry_deadline import command
from test_mql_native_function_bodies import ea
from test_mt5_pending_receipts import command as pull_command
from vati.execution.mt5_bridge import Mt5BridgeAdapter
from vati.execution.mt5_pull import BridgeQueue, Mt5PullAdapter


def test_real_signed_worker_result_without_charge_fields_is_not_fee_zero(tmp_path):
    worker, client, native = build(tmp_path)
    adapter = Mt5BridgeAdapter(client, clock=lambda:1000000)
    receipt = adapter.submit(command(1001000), now_ms=1000000)
    assert receipt.status == 'FILLED' and receipt.filled_qty == D('.1')
    assert receipt.protective_stop_confirmed and len(adapter.positions()) == 1
    assert receipt.fees is None, 'the signed worker returns no measured charge fields'


def test_actual_ea_function_fill_without_charge_fields_is_not_fee_zero(ea, tmp_path):
    queue = BridgeQueue(tmp_path/'native-result.sqlite3')
    try:
        native = ea('entry-market')['results'][0]
        receipt = Mt5PullAdapter(queue)._entry_receipt(pull_command(), native, now_ms=1700000000000)
        assert receipt.status in ('FILLED','PARTIAL') and receipt.filled_qty > 0
        assert receipt.protective_stop_confirmed
        assert receipt.fees is None, 'the original EA reply does not measure commission or fees'
    finally:
        queue.close()
