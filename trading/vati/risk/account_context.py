"""Original native account identity for risk inputs, not a financial grant.

Existing provider captures own observation and authentication. This module
preserves their original account facts and immutable MT5 query reference in
the decision input. It neither assigns old history nor shares reservations.
"""
import json
import re

from vati.core.canonical import canonical_hash, canonical_json
from vati.funding.native import NativeAccountMark, native_int
from vati.funding.mt5 import Mt5FundingFrame, TIME_BASES, amount, text
from vati.risk.arithmetic import fraction
from vati.risk.contracts import NativeAccountRiskContext

_DIGEST = re.compile(r'[0-9a-f]{64}', re.ASCII)
_MT5_MARK_FIELDS = {
    'schema', 'scope_hash', 'source_ref', 'account_alias', 'login', 'server',
    'currency', 'demo', 'observed_at_ms', 'source_kind', 'source_nonce',
    'native_clock_ms', 'query_native_to_ms', 'currency_digits', 'balance',
    'reported_equity', 'credit', 'net_equity', 'valuation_basis',
}


def _digest(value):
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError('native risk account input requires an exact source digest')
    return value


def _physical_key(provider, realm, account_id):
    # Reuse the existing arbitration namespace with actual source identity.
    # The key supplies neither native observation proof nor an owner grant.
    from vati.accounts.physical_scope import ExpectedPhysicalScope
    return ExpectedPhysicalScope(provider, realm, str(account_id)).lease_key


def inspect_context(context):
    """Validate source metadata only; this cannot establish provider authority."""
    if type(context) is not NativeAccountRiskContext:
        raise ValueError('native risk account input requires typed context')
    if context.risk_capital_qualified is not False or context.execution_authority is not False:
        raise ValueError('native account identity cannot issue financial authority')
    if not isinstance(context.source_mark_json, str) or len(context.source_mark_json) > 16384:
        raise ValueError('native risk account source mark capacity')
    mark = json.loads(context.source_mark_json)
    if context.source_mark_json != canonical_json(mark):
        raise ValueError('native risk account source mark must retain canonical bytes')
    text(context.account_alias)
    _digest(context.monetary_scope_hash); _digest(context.observation_ref)
    if context.provider == 'CTRADER':
        source = NativeAccountMark.from_body(mark)
        from vati.execution.ctrader.transport import DEMO_HOST, LIVE_HOST
        key = _physical_key('ctrader', DEMO_HOST if source.environment == 'DEMO' else LIVE_HOST,
                            source.native_account_id)
        if context.source_query_ref is not None or context.observation_ref != canonical_hash(mark):
            raise ValueError('native cTrader risk account source reference mismatch')
        equity, balance = source.net_equity, source.balance
        currency, alias, scope, observed = source.currency, source.account_alias, source.scope_hash, source.observed_at_ms
    elif context.provider == 'MT5':
        if (not isinstance(mark, dict) or set(mark) != _MT5_MARK_FIELDS
                or mark['schema'] != 'mt5-account-mark/1'
                or mark['valuation_basis'] != 'REPORTED_ACCOUNT_EQUITY_MINUS_NATIVE_ACCOUNT_CREDIT'):
            raise ValueError('native MT5 risk account mark format invalid')
        for name in ('account_alias', 'server', 'currency', 'source_nonce'):
            text(mark[name])
        if type(mark['demo']) is not bool or mark['source_kind'] not in TIME_BASES:
            raise ValueError('native MT5 risk account source identity invalid')
        native_int(mark['login'], minimum=1)
        for name in ('observed_at_ms', 'native_clock_ms', 'query_native_to_ms'):
            native_int(mark[name], minimum=0)
        native_int(mark['currency_digits'], minimum=0, maximum=16)
        if mark['query_native_to_ms'] < mark['native_clock_ms']:
            raise ValueError('native MT5 risk account query clock invalid')
        balance, equity = amount(mark['balance']), amount(mark['net_equity'])
        reported, credit = amount(mark['reported_equity']), amount(mark['credit'])
        if credit < 0 or fraction(equity) != fraction(reported) - fraction(credit):
            raise ValueError('native MT5 risk account cash valuation invalid')
        scope = canonical_hash({'provider': 'MT5', 'login': mark['login'], 'server': mark['server'],
                                'currency': mark['currency'], 'demo': mark['demo']})
        if mark['scope_hash'] != scope or mark['source_ref'] != context.observation_ref:
            raise ValueError('native MT5 risk account scope/reference mismatch')
        _digest(context.source_query_ref)
        key = _physical_key('mt5', mark['server'], mark['login'])
        currency, alias, observed = mark['currency'], mark['account_alias'], mark['observed_at_ms']
    else:
        raise ValueError('native risk account provider unsupported')
    if (context.physical_account_key != key or context.monetary_scope_hash != scope
            or context.account_alias != alias):
        raise ValueError('native risk account input contradicts original source identity')
    return {'equity': equity, 'balance': balance, 'currency': currency,
            'observed_at_ms': observed, 'mark': mark}


def validate_snapshot_context(snapshot):
    context = snapshot.native_account_context
    if context is None:
        return
    source = inspect_context(context)
    if (context.account_alias != snapshot.account_alias
            or {'MT5': 'mt5', 'CTRADER': 'ctrader'}[context.provider] != snapshot.symbol_contract.venue
            or source['currency'] != snapshot.symbol_contract.account_currency
            or fraction(source['balance']) != fraction(snapshot.balance)
            or fraction(source['equity']) != fraction(snapshot.equity)
            or source['observed_at_ms'] // 1000 > snapshot.now_unix):
        raise ValueError('native account source context does not bind this risk snapshot')


def context_with_funding_hold(ledger, adapter, account, funding, *, now_ms, mt5_capture=None):
    """A failed source capture holds new risk and preserves original refusals.

    Evidence failure must not prevent a held snapshot or the independent
    position-protection path. Provider details never become owner diagnostics.
    """
    try:
        context = context_for_account(ledger, adapter, account,
            now_ms=now_ms, mt5_capture=mt5_capture)
    except Exception as exc:
        from vati.funding.risk_fence import FundingRiskFence
        held = funding if not funding.available else FundingRiskFence(False,
            'NATIVE_RISK_ACCOUNT_SOURCE_UNAVAILABLE:' + type(exc).__name__[:64])
        return None, held
    return context, funding


def context_for_account(ledger, adapter, account, *, now_ms, mt5_capture=None):
    """Preserve actual cached source data; perform no provider or order I/O."""
    if account.verified is not True:
        return None
    from vati.execution.ctrader.adapter import CtraderAdapter
    from vati.execution.mt5_bridge import Mt5BridgeAdapter
    from vati.execution.mt5_pull import Mt5PullAdapter
    mark = getattr(account, 'funding_mark', None)
    if isinstance(adapter, CtraderAdapter) and type(mark) is NativeAccountMark:
        source = NativeAccountMark.from_body(mark.body())
        from vati.execution.ctrader.transport import DEMO_HOST, LIVE_HOST
        realm = DEMO_HOST if source.environment == 'DEMO' else LIVE_HOST
        if (adapter.ctid_trader_account_id != source.native_account_id
                or adapter.transport.host != realm):
            raise ValueError('current cTrader source account identity mismatch')
        body, query = source.body(), None
        provider, observed_ref = 'CTRADER', canonical_hash(body)
        key = _physical_key('ctrader', realm, source.native_account_id)
    elif isinstance(adapter, (Mt5BridgeAdapter, Mt5PullAdapter)) and type(mark) is Mt5FundingFrame:
        from vati.funding.mt5_journal import Mt5FundingBook
        source = Mt5FundingFrame.from_body(mark.body())
        adapter.identity.validate({'login': source.login, 'server': source.server,
                                   'currency': source.currency, 'demo': source.demo})
        if not isinstance(mt5_capture, dict):
            raise ValueError('original native MT5 query reference unavailable')
        query = _digest(mt5_capture.get('query_ref'))
        with ledger.read_snapshot():
            rows = [e for e in Mt5FundingBook(ledger)._queries(source.scope_hash) if e.hash == query]
        if len(rows) != 1 or rows[0].payload['source_ref'] != source.source_ref:
            raise ValueError('original native MT5 query reference does not bind current facts')
        # Alias is a presentation binding. The existing source_ref explicitly
        # excludes it; a repeated original poll may already have another alias.
        body = source.mark_body()
        strip_alias = lambda value: {k: v for k, v in value.items() if k != 'account_alias'}
        if strip_alias(rows[0].payload['mark']) != strip_alias(body):
            raise ValueError('original native MT5 query mark contradicts current facts')
        provider, observed_ref = 'MT5', source.source_ref
        key = _physical_key('mt5', source.server, source.login)
    else:
        return None
    native_int(now_ms, minimum=source.observed_at_ms)
    if (source.account_alias != account.account_alias or account.account_alias != adapter.account_alias
            or source.currency != account.currency or source.balance != account.balance
            or source.net_equity != account.equity):
        raise ValueError('native account source data does not bind current account')
    context = NativeAccountRiskContext(provider, key, source.scope_hash, account.account_alias,
        observed_ref, query, canonical_json(body))
    inspect_context(context)
    return context
