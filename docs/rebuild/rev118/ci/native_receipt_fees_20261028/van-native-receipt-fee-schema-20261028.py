from pathlib import Path
from dataclasses import asdict
from decimal import Decimal
import hashlib, json, sys
root=Path('/workspace/van-review-2026-10-18/publish')
sys.path[:0]=[str(root/'trading'),str(root/'trading/tests')]
from test_native_receipt_fee_knowledge import native_fill
from vati.core.canonical import canonical_json
from vati.app.trade_lifecycle import AccountTradeLifecycle
from jsonschema import Draft202012Validator
schema=root/'trading/vati/contracts/schemas/execution_receipt.schema.json'
validator=Draft202012Validator(json.loads(schema.read_text()))
Draft202012Validator.check_schema(validator.schema)
rows=[]
for missing,commission,expected in [(('commission',),-350,None),((),0,Decimal('0')),((),-350,Decimal('3.50'))]:
    with native_fill(missing,commission) as (_,_,receipt):
        payload=json.loads(canonical_json(asdict(receipt)))
        validator.validate(payload)
        cold=AccountTradeLifecycle._receipt_from_payload(payload)
        assert cold.fees==expected and cold.receipt_hash==receipt.receipt_hash
        assert cold.filled_qty==Decimal('.10') and cold.protective_stop_confirmed
        rows.append({'fees':payload['fees'],'receipt_hash':cold.receipt_hash,'schema_valid':True,
            'actual_fill_retained':True,'protection_retained':True,'same_original_hash':True})
print(json.dumps({'schema_sha256':hashlib.sha256(schema.read_bytes()).hexdigest(),'cases':rows,
    'source_fixtures_not_provider_or_device_qualification':True},indent=2))
