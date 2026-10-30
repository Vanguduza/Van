"""Bounded instrument discovery and exact native alias resolution.

The existing catalog source owner validates every original row and revision.
Enabled/visible listing facts are not a current trading or entitlement grant.
"""
import re

from vati.core.canonical import canonical_hash
from vati.core.ledger import committed_source_snapshot
from vati.execution.ctrader.catalog import catalog_scope
from vati.execution.ctrader.feed import native_integer
from vati.market_data.catalog_store import NativeCatalogStore,CatalogArchiveError

CURSOR=re.compile(r'([a-f0-9]{64}):([a-f0-9]{64}):([1-9][0-9]{0,18})',re.ASCII)


class CatalogSelectionConflict(CatalogArchiveError):
    pass


def discover_instruments(store,scope,*,revision=None,as_of_ms=None,record_ref=None,
                         alias=None,native_symbol_id=None,limit=100,after=None):
    if not isinstance(store,NativeCatalogStore):raise CatalogArchiveError('original catalog owner required')
    scope=catalog_scope(scope);native_integer(limit,minimum=1,maximum=256)
    if record_ref is not None and (type(record_ref) is not str or re.fullmatch('[a-f0-9]{64}',record_ref,re.ASCII) is None):
        raise CatalogArchiveError('native catalog record reference invalid')
    if native_symbol_id is not None:native_integer(native_symbol_id,minimum=1,maximum=2**63-1)
    if alias is not None and (type(alias) is not str or not 1<=len(alias)<=4096
            or not alias.strip() or any(ord(c)<32 or ord(c)==127 for c in alias)):
        raise CatalogArchiveError('native alias invalid')
    selector={'scope':scope,'alias':alias,'native_symbol_id':native_symbol_id}
    selector_hash=canonical_hash(selector)
    cursor=None
    if after is not None:
        if type(after) is not str or (cursor:=CURSOR.fullmatch(after)) is None:
            raise CatalogArchiveError('native catalog cursor invalid')
        if cursor[2]!=selector_hash:raise CatalogSelectionConflict('native catalog cursor selector differs')
    with committed_source_snapshot(store.ledger):
        now=native_integer(store.clock(),maximum=253402300799000)
        original=store.snapshot(scope,revision=revision,
            as_of_ms=(now if revision is as_of_ms is None else as_of_ms))
        if original is not None and original['receipt']['available_at_ms']>now:original=None
    if record_ref is not None and (original is None or record_ref!=original['receipt']['record_ref']):
        raise CatalogSelectionConflict('native catalog pinned source differs')
    if cursor is not None and (original is None or cursor[1]!=original['receipt']['record_ref']):
        raise CatalogSelectionConflict('native catalog cursor revision differs; select the original revision')
    rows=[]
    if original is not None:
        for member in original['members']:
            raw=member['original'];name=raw.get('symbolName' if member['source_kind']=='LIGHT' else 'name')
            if alias is not None and name!=alias:continue
            if native_symbol_id is not None and member['native_symbol_id']!=native_symbol_id:continue
            representable=(name is not None and 1<=len(name)<=256 and bool(name.strip())
                and all(ord(c)>=32 and ord(c)!=127 for c in name))
            instrument=None if not representable else {
                'venue':'ctrader','environment':scope['environment'],'api_family':'cTraderOpenAPI',
                'product_id':str(member['native_symbol_id']),'symbol':name,
                'account_id':str(scope['native_account_id']),'contract_revision':None}
            rows.append({**member,'native_name':name,'instrument_ref':instrument,
                'listing_state':('ARCHIVED' if member['source_kind']=='ARCHIVED' else
                    'NATIVE_ENABLED_UNQUALIFIED' if member['visible'] else 'NATIVE_DISABLED_OR_OMITTED'),
                'frontend_reference_state':('PRESENT' if representable else
                    'NATIVE_NAME_UNAVAILABLE' if not name or not name.strip() else 'NATIVE_NAME_OUTSIDE_FRONTEND_CONTRACT'),
                'contract_state':'FULL_CONTRACT_NOT_RESOLVED','entitlement_state':'NOT_QUALIFIED'})
    count=len(rows)
    state=('NO_CAPTURE' if original is None else 'EMPTY_CATALOG' if not original['members'] else 'CATALOG_OBSERVED_UNQUALIFIED')
    resolution=('NOT_REQUESTED' if alias is native_symbol_id is None else
        'SOURCE_UNAVAILABLE' if original is None else 'NOT_FOUND' if count==0 else
        'RESOLVED_NATIVE_IDENTITY' if count==1 else 'AMBIGUOUS_NATIVE_ALIAS')
    remaining=[r for r in rows if cursor is None or r['native_symbol_id']>int(cursor[3])]
    page=remaining[:limit]
    next_cursor=(original['receipt']['record_ref']+':'+selector_hash+':'+str(page[-1]['native_symbol_id'])
        if len(remaining)>limit else None)
    return {'schema':'vati.native-instrument-catalog-view/1','state':state,'scope':scope,
        'receipt':None if original is None else original['receipt'],
        'requested_revision':revision,'requested_as_of_ms':as_of_ms,'requested_record_ref':record_ref,
        'alias':alias,'native_symbol_id':native_symbol_id,'resolution_state':resolution,
        'total_matches':count,'members':page,'next_cursor':next_cursor,
        'coverage':None if original is None else original['coverage'],
        'alias_matching':'EXACT_ORIGINAL_NATIVE_NAME_NO_CASE_OR_PUNCTUATION_REWRITE',
        'current_tradability':'NOT_EVALUATED_HISTORICAL_LISTING',
        'provider_qualified':False,'execution_authority':False,'authority_effect':'NONE'}
