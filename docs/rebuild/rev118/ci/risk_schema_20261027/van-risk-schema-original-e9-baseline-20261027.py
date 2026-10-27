from pathlib import Path
import json,subprocess,hashlib
from jsonschema import Draft202012Validator
r=Path('/workspace/van-review-2026-10-18/publish');head='e9cbdd69c9d98688e14b088c19c65e5df80c6e42'
raw=subprocess.check_output(['git','show',head+':trading/vati/contracts/schemas/risk_snapshot.schema.json'],cwd=r)
v=Draft202012Validator(json.loads(raw));snapshots=json.loads((r/'tests/rebuild/fixtures/native_risk_snapshots_e9cbdd69.json').read_text())['snapshots'];results={}
for name,body in snapshots.items():
    errors=list(v.iter_errors(body));assert errors
    assert any(e.validator=='additionalProperties' and 'native_account_context' in e.message for e in errors)
    results[name]={'old_schema_result':'REJECTED_CURRENT_NATIVE_OUTPUT','errors':[e.message for e in errors]}
for name in ['legacy_risk_snapshot_b58bb578.json','legacy_risk_snapshot_no_margin_74b1749a.json']:
    body=json.loads((r/'trading/tests/fixtures'/name).read_text())['snapshot'];v.validate(body)
    results[name]={'old_schema_result':'LEGACY_CONTROL_ACCEPTED'}
receipt={'source_head':head,'original_schema_sha256':hashlib.sha256(raw).hexdigest(),'observed_current_native_rejections':2,'passing_legacy_controls':2,'results':results,'scope':'Actual original JSONSchema validator over actual source-serialized fixture bodies; no native or financial qualification'}
Path('/workspace/van-risk-schema-original-e9-baseline-20261027.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items() if k!='results'}))
