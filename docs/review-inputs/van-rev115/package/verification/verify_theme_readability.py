#!/usr/bin/env python3
"""Readability specification bindings and opaque token arithmetic, never device acceptance."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def read(f):return json.loads((ROOT/f).read_text())
def luminance(value):
    channels=[int(value[i:i+2],16)/255 for i in (1,3,5)]
    return sum(w*(v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4) for w,v in zip((0.2126,0.7152,0.0722),channels))
def contrast(a,b):
    lo,hi=sorted((luminance(a),luminance(b)))
    return (hi+0.05)/(lo+0.05)
def main():
    errors=[]
    def check(ok,label):
        if not ok:errors.append(label)
    registry=read('design/ALL_SURFACE_CONTRACTS.json')
    f='design/THEME_READABILITY_CONTEXT_BINDINGS.json';b=read(f)
    by={s['id']:s for s in registry['surfaces']}
    ids=[x['context_id'] for x in b['bindings']]
    check(len(ids)==len(set(ids))==234 and set(ids)==set(by),'Exact 234-context coverage')
    check(f in registry['extension_registries'],'Extension discoverable from main registry')
    refs={'T-VAN-CX-020-POS','T-VAN-CX-020-NEG','T-VAN-CX-020-REC'}
    tests={t['id'] for t in read('verification/TEST_CONTRACTS.json')['tests']}
    check(refs<=tests,'Existing test references resolve')
    check(b['native_scenarios_state']=='NOT_RUN' and b['new_application_test_ids']==0,'Native status/count boundary')
    check((ROOT/b['normative_contract']).is_file(),'Normative amendment exists')
    for x in b['bindings']:
        check(x['frontend_units']==by.get(x['context_id'],{}).get('frontend_units'),x['context_id']+': frontend ownership')
        check(set(x['acceptance_refs'])==refs and set(x['themes'])=={'dark','light'},x['context_id']+': acceptance/themes')
    p=read('plan/DEVELOPMENT_PLAN.json')
    for u in p['units']:
        if u['id'] in ['UX-001','UX-002','UX-003','QA-001'] or u['id'].startswith('FE-'):
            check(u.get('theme_readability_contract')==b['normative_contract'],u['id']+': plan refinement')
    authority=read('CANONICAL_AUTHORITY.json')
    check(authority.get('theme_readability_context_bindings')==f,'Canonical binding')
    check(b['normative_contract'] in (ROOT/authority['master']).read_text(),'Master integration')
    colors=read(b['palette_source'])['color'];samples=[]
    for theme in ['dark','light']:
        for fg in ['text_primary','text_secondary','text_muted','border_control','focus']:
            threshold=4.5 if fg.startswith('text') else 3.0
            for bg in ['canvas','canvas_top','surface','surface_top','surface_raised','inset','navigation','chart_background']:
                ratio=contrast(colors[theme][fg],colors[theme][bg])
                samples.append({'theme':theme,'foreground':fg,'background':bg,'ratio':round(ratio,4),'minimum':threshold,'passes':ratio>=threshold})
                check(ratio>=threshold,':'.join([theme,fg,bg])+': opaque reference contrast')
    # Published WCAG example values catch transfer-function or ratio arithmetic regression.
    check(abs(contrast('#000000','#FFFFFF')-21)<1e-9,'Black/white reference 21:1')
    check(abs(contrast('#777777','#FFFFFF')-4.47808945)<1e-7,'Mid-grey reference')
    result={'scope':'DOCUMENT_BINDINGS_AND_OPAQUE_TOKEN_ARITHMETIC_ONLY','amendment_date':'2026-10-21','passed':not errors,'findings':errors,'contexts':len(ids),'static_token_pairs':len(samples),'token_sha256':hashlib.sha256((ROOT/b['palette_source']).read_bytes()).hexdigest(),'samples':samples,'application_acceptance_tests_executed':0,'native_scenarios_state':'NOT_RUN','rendered_and_handset_contrast_verified':False,'limitation':'Opaque paired tokens only; no compositing, gradients, disabled states, actual glyphs, device brightness, accessibility tree or S24 acceptance.'}
    print(json.dumps(result,indent=2))
    return int(bool(errors))
if __name__=='__main__':raise SystemExit(main())
