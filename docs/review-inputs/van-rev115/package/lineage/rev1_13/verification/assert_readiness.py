#!/usr/bin/env python3
"""Refuse operational readiness claims from this unsigned preparation pack.
This portable guard is not an authority issuer or replacement for DIAL's actual
independent receipt verifier. A real certificate is supplied through that verifier,
not manufactured by editing these preparation templates.
"""
import argparse,json,sys
from pathlib import Path
r=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--gate',choices=['F15','BG'],required=True);a=p.parse_args()
f='F15_CERTIFICATE.json' if a.gate=='F15' else 'BACKEND_COMPLETE_CERTIFICATE.json'
x=json.loads((r/'verification'/f).read_text())
reasons=['INDEPENDENT_ISSUER_NOT_VERIFIED','OWNER_TRUST_AND_SIGNATURE_NOT_VERIFIED','REQUIRED_RUNTIME_OR_PREPARATION_RECEIPTS_NOT_ADMITTED']
if x.get('status')=='NOT_ISSUED':reasons.insert(0,'CERTIFICATE_NOT_ISSUED')
print(json.dumps({'gate':a.gate,'ready':False,'reasons':reasons,'scope':'Prepared pack cannot issue or verify live readiness. Invoke the qualified independent DIAL authority with exact project/source/scope evidence.'},indent=2));sys.exit(2)
