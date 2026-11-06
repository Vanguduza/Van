"""Pinned read-only bar vintages from the existing native archive owner.

This is not a DatasetManifest, source/clock qualification, entitlement, model
admission or order authority. Revision and time boundaries are both explicit:
future captures with the same millisecond cannot rewrite an already pinned view.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from vati.core.canonical import canonical_hash,canonical_json
from vati.core.file_lock import exclusive_state_lock
from vati.execution.ctrader.feed import MAX_TIMESTAMP,TrendbarObservation,native_integer
from vati.market_data.native_archive import MAX_RECORDS,NativeArchiveError,NativeMarketArchive


@dataclass(frozen=True)
class WindowBudget:
    records: int=256
    source_bytes: int=64*1024**2
    rows: int=10000

    def __post_init__(self):
        for name,maximum in [('records',MAX_RECORDS),('source_bytes',256*1024**2),('rows',100000)]:
            value=getattr(self,name)
            if type(value) is not int or not 1<=value<=maximum:
                raise NativeArchiveError('NATIVE_WINDOW_BUDGET_INVALID:'+name)


class NativeBarWindowReader:
    """Resolve every row against original source bytes; never grant data use."""
    def __init__(self,archive,*,budget=None):
        if not isinstance(archive,NativeMarketArchive) or archive.observation_type is not TrendbarObservation:
            raise NativeArchiveError('NATIVE_BAR_ARCHIVE_OWNER_REQUIRED')
        self.archive=archive;self.budget=budget or WindowBudget()
        if not isinstance(self.budget,WindowBudget):raise NativeArchiveError('NATIVE_WINDOW_BUDGET_REQUIRED')

    def capture(self,scope,timeframe,*,through_revision,boundary_ref,as_of_ms,from_ms,to_ms):
        """Return a bounded source view pinned to an actual ordinal and cutoff.

        Interval completeness and instrument calendars are deliberately unknown.
        Raw native pagination/spread/contract facts are retained for the actual
        dataset owner to adjudicate alongside entitlements and universe policy.
        """
        try:
            native_integer(through_revision,minimum=1,maximum=MAX_RECORDS)
            native_integer(as_of_ms,maximum=native_integer(self.archive.clock(),maximum=253402300799000))
            native_integer(from_ms,maximum=MAX_TIMESTAMP)
            native_integer(to_ms,minimum=from_ms+1,maximum=MAX_TIMESTAMP)
            if not isinstance(boundary_ref,str) or re.fullmatch('[a-f0-9]{64}',boundary_ref) is None:
                raise ValueError('NATIVE_WINDOW_BOUNDARY_REF_INVALID')
            part=self.archive._partition(scope,timeframe)
            if not part.exists():raise ValueError('NATIVE_WINDOW_SOURCE_UNAVAILABLE')
            with exclusive_state_lock(part/'head.json'):
                paths=list(part.glob('*.json'))
                records=[p for p in paths if p.name!='head.json']
                if len(records)>self.budget.records or any(p.is_symlink() for p in paths):
                    raise ValueError('NATIVE_WINDOW_SOURCE_CAPACITY_OR_PATH')
                if sum(p.stat().st_size for p in paths)>self.budget.source_bytes:
                    raise ValueError('NATIVE_WINDOW_SOURCE_BYTE_LIMIT')
                originals,state=self.archive._load(part,scope,timeframe)
            if state!='CONSISTENT':raise ValueError('NATIVE_WINDOW_INDEX_UNCONFIRMED')
            if through_revision>len(originals):raise ValueError('NATIVE_WINDOW_REVISION_UNAVAILABLE')
            boundary,digest=originals[through_revision-1]
            if digest!=boundary_ref:raise ValueError('NATIVE_WINDOW_BOUNDARY_CONFLICT')
            if boundary['recorded_at_ms']>as_of_ms:raise ValueError('NATIVE_WINDOW_BOUNDARY_AFTER_CUTOFF')
            selected={};sources=[];excluded=set()
            # Preserve all originals in the pinned prefix, including empty or
            # truncated pages. A row-free original must not vanish from lineage.
            for body,digest in originals[:through_revision]:
                observation=body['observation']
                sources.append({'receipt':self.archive._receipt(body,digest,state),
                    'contract':body['contract'],
                    'requested_window':{'from_ms':observation['from_ms'],'to_ms':observation['to_ms']},
                    'has_more':observation['has_more'],'excluded_open_bars':observation['excluded_open_bars'],
                    'interval_basis':observation['interval_basis'],'spread_state':observation['spread_state'],
                    'spread':observation['spread'],'volume_basis':observation['volume_basis']})
                for row in observation['bars']:
                    key=(row['start_ms'],row['end_ms'])
                    if row['start_ms']<from_ms or row['end_ms']>to_ms:
                        if row['end_ms']>from_ms and row['start_ms']<to_ms:excluded.add(key)
                        continue
                    if row['end_ms']>as_of_ms:raise ValueError('NATIVE_WINDOW_BAR_AFTER_CUTOFF')
                    selected[key]={'bar':row,'source_record_ref':digest,'source_revision':body['revision'],
                        'contract_revision':body['contract']['metadata_revision'],
                        'received_at_ms':observation['received_at_ms'],'available_at_ms':body['recorded_at_ms']}
                    if len(selected)>self.budget.rows:raise ValueError('NATIVE_WINDOW_ROW_LIMIT')
            rows=[selected[key] for key in sorted(selected)]
            body={'schema':'vati.native-bar-window/1','scope':dict(scope),'timeframe':timeframe,
                'through_revision':through_revision,'boundary_ref':boundary_ref,'as_of_ms':as_of_ms,
                'from_ms':from_ms,'to_ms':to_ms,'rows':rows,'source_records':sources,
                'excluded_boundary_intervals':[{'start_ms':a,'end_ms':b} for a,b in sorted(excluded)],
                'max_input_available_ms':max(source['receipt']['available_at_ms'] for source in sources),
                'availability_basis':'LOCAL_CAPTURE_CLOCK_NOT_NATIVE_CLOCK_QUALIFICATION',
                'coverage_state':'INCOMPLETE_NATIVE_PAGE' if any(s['has_more'] is True for s in sources)
                    else 'PAGINATION_UNAVAILABLE' if any(s['has_more'] is None for s in sources)
                    else 'UNQUALIFIED_SCHEDULE_COVERAGE',
                'provider_qualified':False,'qualified_for_research':False,'authority_effect':'NONE'}
            if len(canonical_json(body).encode())>self.budget.source_bytes:
                raise ValueError('NATIVE_WINDOW_OUTPUT_BYTE_LIMIT')
            return body|{'window_sha256':canonical_hash(body)}
        except (KeyError,TypeError,ValueError,ArithmeticError,OSError) as error:
            raise NativeArchiveError('native bar window unavailable: '+str(error)) from error

    def verify(self,window,*,expected_scope):
        """Independently resolve original membership; a self-consistent hash is not proof."""
        try:
            if not isinstance(window,dict) or window.get('scope')!=expected_scope:
                raise ValueError('NATIVE_WINDOW_SCOPE_CONFLICT')
            # Bound caller-supplied structures before canonical serialization.
            if (not isinstance(window.get('rows'),list) or len(window['rows'])>self.budget.rows
                    or not isinstance(window.get('source_records'),list)
                    or len(window['source_records'])>self.budget.records):
                raise ValueError('NATIVE_WINDOW_INPUT_CAPACITY')
            if len(canonical_json(window).encode())>self.budget.source_bytes:
                raise ValueError('NATIVE_WINDOW_INPUT_BYTE_LIMIT')
            actual=self.capture(expected_scope,window['timeframe'],through_revision=window['through_revision'],
                boundary_ref=window['boundary_ref'],as_of_ms=window['as_of_ms'],
                from_ms=window['from_ms'],to_ms=window['to_ms'])
            if canonical_json(actual)!=canonical_json(window):raise ValueError('NATIVE_WINDOW_ORIGINAL_READBACK_CONFLICT')
            return actual
        except (KeyError,TypeError,ValueError,ArithmeticError,OSError) as error:
            raise NativeArchiveError('native bar window verification unavailable: '+str(error)) from error
