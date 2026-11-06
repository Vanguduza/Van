#!/usr/bin/env python3
"""Check portable forecast schemas/fixtures only; no data access, fitting or authority."""
from __future__ import annotations
import argparse, importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--selftest',action='store_true'); args=parser.parse_args()
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:
        print('jsonschema is required for these document checks; no automatic installation.',file=sys.stderr); return 2
    source=ROOT/'lineage/forecast_rev1_1/verification/prediction_market_contract_checks.py'
    spec=importlib.util.spec_from_file_location('van_fixture_check',source)
    if spec is None or spec.loader is None: raise RuntimeError('Fixture checker unavailable')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    schema_dir=ROOT/'contracts/forecast'
    schemas={p.name.removesuffix('.schema.json'):json.loads(p.read_text()) for p in sorted(schema_dir.glob('*.schema.json'))}
    for schema in schemas.values(): Draft202012Validator.check_schema(schema)
    fixtures={}; findings=[]; checked=0
    for p in sorted((schema_dir/'prediction_market_examples').glob('*.fixture.json')):
        kind=p.name.removesuffix('.fixture.json'); fixtures[kind]=json.loads(p.read_text()); checked+=1
        findings.extend(f'{p.name}: {e}' for e in module.fixture_errors(kind,fixtures[kind],schemas[kind]))
    for p in sorted((schema_dir/'examples').glob('ForecastPacket.fixture.*.json')):
        checked+=1
        findings.extend(f'{p.name}: {e.message}' for e in Draft202012Validator(schemas['ForecastPacket'],format_checker=FormatChecker()).iter_errors(json.loads(p.read_text())))
    mutations=module.mutation_checks(fixtures,schemas) if args.selftest else []
    findings.extend('MISSED_MUTATION:'+m['name'] for m in mutations if m['result']!='DETECTED')
    result={'scope':'DOCUMENT_AND_SYNTHETIC_FIXTURE_ONLY_NOT_ECONOMIC_OR_RUNTIME_QUALIFICATION','schemas':len(schemas),'fixtures':checked,'findings':findings,'mutation_count':len(mutations),'mutations_detected':sum(m['result']=='DETECTED' for m in mutations),'mutations':mutations}
    print(json.dumps(result,indent=2)); return 1 if findings else 0
if __name__=='__main__':
    try: raise SystemExit(main())
    except (OSError,ValueError,KeyError) as exc: print(str(exc),file=sys.stderr); raise SystemExit(2)
