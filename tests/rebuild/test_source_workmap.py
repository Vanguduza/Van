"""The execution index must detect lost scope and weakened full contracts."""
from copy import deepcopy
import json

import pytest

from tools.rebuild.workmap import ROOT, OUTPUT, build, check_document


def test_current_workmap_preserves_every_original_scope_identity_and_dependency():
    check_document(json.loads((ROOT/OUTPUT).read_text()), build())


@pytest.mark.parametrize('change', [
    'unit', 'dependency', 'requirement', 'acceptance', 'context', 'action',
    'planned_feature', 'source_function', 'contract_semantics', 'self_accepted',
])
def test_scope_loss_or_semantic_weakening_is_detected_even_with_retained_summary_counts(change):
    original = build()
    candidate = deepcopy(original)
    names = {'requirement': 'requirements', 'acceptance': 'acceptance',
        'context': 'contexts', 'action': 'actions', 'planned_feature': 'planned_features',
        'source_function': 'source_functions'}
    if change in names:
        candidate['identity_contract_hashes'][names[change]].popitem()
    elif change == 'unit':
        candidate['units'].pop()
    elif change == 'dependency':
        row = next(u for u in candidate['units'] if u['dependencies'])
        row['dependencies'].pop()
    elif change == 'contract_semantics':
        # Keep every ID/count; changing a state/oracle changes its full-row hash.
        key = next(iter(candidate['identity_contract_hashes']['planned_features']))
        candidate['identity_contract_hashes']['planned_features'][key] = '0'*64
    else:
        candidate['units'][0]['unit_acceptance'] = 'OWNER_ACCEPTED'
    assert candidate['counts'] == original['counts']
    with pytest.raises(ValueError, match='workmap differs'):
        check_document(candidate, original)
