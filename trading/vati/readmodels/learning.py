"""Read an account service's recorded analytical view without running a reducer."""
from __future__ import annotations

from vati.core.canonical import canonical_hash
from vati.learning.scope import ENVIRONMENT_FOR_MODE
from vati.risk.mandate import AuthorizationMode


def reported_restated_learning(event, account_alias: str):
    unavailable = {'status': 'NOT_REPORTED', 'selection_authority': False}
    if event is None or 'restated_learning' not in event.payload:
        return unavailable
    invalid = {'status': 'UNVERIFIED_REPORT', 'selection_authority': False}
    if (event.producer not in {'vati-service', 'vati-account-service'}
        or event.hash != canonical_hash(event.body()) or event.payload.get('account_alias') != account_alias):
        return invalid
    report = event.payload['restated_learning']
    if not isinstance(report, dict) or report.get('selection_authority') is not False:
        return invalid
    if report.get('status') == 'UNAVAILABLE':
        return {'status': 'UNAVAILABLE', 'selection_authority': False,
                'source_event_hash': event.hash, 'reported_at_ms': event.received_time_ms}
    try:
        scope = report['scope']
        expected = ENVIRONMENT_FOR_MODE[AuthorizationMode(event.payload['mode'])].value
        if (scope['account_alias'] != account_alias or scope['environment'] != expected
            or report['as_decided_preserved'] is not True or not isinstance(report['views'], dict)
            or report['status'] not in {'NO_OBSERVATIONS', 'ANALYSIS_ONLY', 'MATURITY_PENDING', 'RECONCILIATION_REQUIRED'}):
            return invalid
    except (ValueError, KeyError, TypeError):
        return invalid
    return {**report, 'source_event_hash': event.hash, 'reported_at_ms': event.received_time_ms,
            'freshness': 'RECORDED_ACCOUNT_SNAPSHOT_ONLY'}
