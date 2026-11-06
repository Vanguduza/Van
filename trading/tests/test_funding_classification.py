from decimal import Decimal as D
from vati.execution.ctrader.protoschema import SCHEMA
from vati.funding.classification import classify,EXTERNAL,CREDIT,SUPPORT,OTHER_BUSINESS,TRADING

def test_every_vendored_native_cash_operation_has_one_explicit_economic_meaning():
    groups=[EXTERNAL,CREDIT,SUPPORT,OTHER_BUSINESS,TRADING]
    assert sum(map(len,groups))==len(set.union(*groups))
    assert set.union(*groups)==set(SCHEMA.enums['ProtoOAChangeBalanceType'])
    for operation in set.union(*groups):
        result=classify(operation,D('-1') if operation.startswith('BALANCE_WITHDRAW') else D('1'))
        assert result['state']=='CLASSIFIED' and result['trade_alpha_claimed'] is False and result['execution_authority'] is False

def test_cash_fees_credit_broker_support_and_other_business_are_distinct():
    assert classify('BALANCE_WITHDRAW_TRANSFER',D('-20'))['category']=='EXTERNAL_CAPITAL'
    assert classify('BALANCE_WITHDRAW_SWAP',D('-2'))['category']=='ACCOUNT_INCOME_OR_EXPENSE'
    assert classify('BALANCE_DEPOSIT_NONWITHDRAWABLE_BONUS',D('20'))['category']=='RESTRICTED_CREDIT'
    assert classify('BALANCE_DEPOSIT_CONVERTED_BONUS',D('20'))['category']=='BROKER_SUPPORT_CAPITAL'
    assert classify('BALANCE_DEPOSIT_IB_COMMISSIONS',D('20'))['category']=='OTHER_BUSINESS_INCOME_OR_EXPENSE'
    assert classify('NATIVE_UNKNOWN:999',D('1'))['state']=='UNKNOWN_OPERATION'
    assert classify('BALANCE_WITHDRAW',D('20'))['state']=='NATIVE_SIGN_CONFLICT'
