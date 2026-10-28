import sys
sys.path[:0]=['/workspace/van-review-2026-10-18/publish/trading',
 '/workspace/van-review-2026-10-18/publish/trading/tests',
 '/workspace/van-review-2026-10-18/publish/tests/rebuild']
from test_mt5_final_cash_margin import EntryCashSdk,command
from test_mt5_worker_funding import connection
from test_mt5_cash_unit_source import source_executable

def test_actual_ea_helper_retains_strictly_above_reported_fraction(source_executable):
    assert source_executable(['R 2200050 0 10000 1000'])==['ALLOW']

def test_signed_sdk_retains_the_same_strictly_above_reported_fraction(tmp_path):
    sdk=EntryCashSdk(equity=1000.,credit=0.,used=100.,reported_free=900.);original=sdk.account_info
    def account():
        a=original();a.margin_level=220.005;return a
    sdk.account_info=account;sdk.margin_value=10.
    sdk,worker,adapter,now=connection(tmp_path,sdk)
    receipt=adapter.submit(command(adapter.account_alias),now_ms=now['ms'])
    assert receipt.status=='FILLED' and len(sdk.sent)==1
