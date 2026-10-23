#!/usr/bin/env python3
"""Render current owner contracts as Markdown; preserve all rows and declared gaps."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT/'docs/rebuild/rev118/backend/OWNER_FRONTEND_SCREEN_REGISTRY.md'
INPUTS = ('owner_features','owner_screens','owner_endpoints','owner_endpoint_schemas')


def cell(value):
    if not isinstance(value,str):
        value=json.dumps(value,ensure_ascii=False,sort_keys=True)
    return value.replace('|','\\|').replace('\r','').replace('\n','<br>')


def render():
    docs={k:json.loads((ROOT/'registries'/f'{k}.json').read_text()) for k in INPUTS}
    features=docs['owner_features']['features'];screens=docs['owner_screens']['screens']
    endpoints=docs['owner_endpoints']['endpoints'];schemas=docs['owner_endpoint_schemas']['components']['schemas']
    def unique(rows):
        values={r['id']:r for r in rows}
        if len(values)!=len(rows):raise ValueError('Duplicate registry identity')
        return values
    feature_map=unique(features);screen_map=unique(screens)
    endpoint_map={r['endpoint_id']:r for r in endpoints}
    if len(endpoint_map)!=len(endpoints):raise ValueError('Duplicate endpoint identity')
    for row in features+screens:
        for key,target in [('screen_ids',screen_map),('required_screen_ids',screen_map),('feature_ids',feature_map)]:
            if any(x not in target for x in row.get(key,[])):raise ValueError(f"Unknown {key}: {row['id']}")
        for ref in row.get('endpoint_refs',[])+row.get('backend_contract_extensions',[]):
            if ref.get('endpoint_id') not in endpoint_map:raise ValueError(f"Unknown endpoint: {row['id']}")
    funcs=[f for r in features for f in r.get('current_implementation',{}).get('functions',[])]
    lines=['# VAN current frontend screen and feature registry','',
        f"Current source inventory: **{len(features)} features, {len(funcs)} source functions, {len(screens)} screens/hosted surfaces, {len(endpoints)} endpoint declarations and {len(schemas)} schemas**.",'',
        'This generated document renders the current source contracts, including gaps and unverified states. It does not declare features complete, qualify live services or authorize a redesigned frontend. No new frontend/prototype before BG-001. Current source features are distinct from the frozen Rev1.18 programme of **93 planned features, 349 owner actions, 324 requirements, 1,610 acceptance identities and 131 units**. The complete planned scope remains in [the frozen package](../../../review-inputs/van-rev115/package/) and its [backend consumption contract](../../../review-inputs/van-rev115/package/contracts/BACKEND_TO_FRONTEND_CONSUMPTION_CONTRACT.md).','',
        'Android receives its gateway/Hermes route and trust from signed release/provisioning. Screen designs must not require an owner to enter a host, port, bearer token or certificate. Provisioning, production signing, deployed connectivity and S24 acceptance remain separate qualifications.','',
        'Preserve available/empty/loading/stale/refused/unknown/reconciling states. Accepted or requested work is not an applied effect. Keep original operation identity on uncertainty; GET observes rather than dispatches. Final risk recovery never supplies blanket entry permission. An expired original refused before actor observation has null current risk fields; fetch current state before another approval.','',
        'Owner-access endpoints and service dependencies are listed separately below. An endpoint declaration or client method does not establish a screen consumer, runtime deployment or handset behavior. Historical qualification fields remain in the JSON inputs; this document does not promote them to current evidence.','',
        '## Source inputs','', '| Registry | SHA-256 |','| --- | --- |']
    for name in INPUTS:
        p=ROOT/'registries'/f'{name}.json'
        lines.append(f"| [{name}.json](../../../../registries/{name}.json) | `{hashlib.sha256(p.read_bytes()).hexdigest()}` |")
    lines+=['','Regenerate with `python3 tools/rebuild/render_frontend_registry.py --apply`; verify with `--check`.','',
        '## Screen index','', '| ID | Title | Route / host interaction | Feature IDs | Wiring status |','| --- | --- | --- | --- | --- |']
    for row in screens:
        lines.append('| '+' | '.join(cell(x) for x in (row['id'],row['title'],str(row.get('route',''))+' / '+str(row.get('interaction_kind','')),', '.join(row.get('feature_ids',[])),row.get('functional_wiring_status','UNSPECIFIED')))+' |')
    def listing(title,values):
        if values:
            lines.extend(['',f'**{title}**',''])
            lines.extend('- '+cell(x) for x in values)
    def endpoint_table(row):
        refs=row.get('endpoint_refs',[])
        if refs:
            lines.extend(['','**Declared endpoint contracts**','', '| Method | Path | Access / authentication | Android client |','| --- | --- | --- | --- |'])
            for ref in refs:
                current=endpoint_map[ref['endpoint_id']]
                lines.append('| '+' | '.join(cell(x) for x in (current['method'],current['path'],str(ref.get('frontend_access','UNSPECIFIED'))+' / '+str(current.get('authentication','')),str(ref.get('client_namespace',''))+'.'+str(ref.get('client_function','UNWIRED'))))+' |')
        ext=row.get('backend_contract_extensions',[])
        if ext:
            lines.extend(['','**Backend/client extensions — consumer status is explicit**','', '| Method / path | Client | Status | Scope |','| --- | --- | --- | --- |'])
            for item in ext:
                current=endpoint_map[item['endpoint_id']]
                lines.append('| '+' | '.join(cell(x) for x in (current['method']+' '+current['path'],str(item.get('client_namespace',''))+'.'+str(item.get('client_function','UNWIRED')),item.get('source_status','UNSPECIFIED'),item.get('scope','')))+' |')
        listing('Service dependencies (not Android owner access)',row.get('service_endpoint_ids',[]))
        listing('External dependencies',row.get('external_endpoint_ids',[]))
    lines+=['','## Screens and hosted surfaces']
    for row in screens:
        lines+=['',f"### {row['id']} — {cell(row['title'])}",'',f"Owner goal: {cell(row.get('owner_goal',''))}",
            '',f"Route: `{cell(row.get('route',''))}`; interaction: `{cell(row.get('interaction_kind',''))}`; domain: `{cell(row.get('domain',''))}`.",
            '',f"Feature IDs: {cell(', '.join(row.get('feature_ids',[])))}.",
            '',f"Wiring: `{cell(row.get('functional_wiring_status','UNSPECIFIED'))}`; frontend integration: `{cell(row.get('frontend_integration_status','UNSPECIFIED'))}`; acceptance evidence: `{cell(row.get('acceptance_evidence_status','UNSPECIFIED'))}`."]
        listing('Information supplied',row.get('information',[]));listing('Owner interactions and controls',row.get('actions',[]))
        listing('Required acceptance states',row.get('acceptance_states',[]));listing('Declared gaps',row.get('gaps',[]))
        listing('Current navigation contract', [row['current_navigation_contract']] if row.get('current_navigation_contract') else [])
        endpoint_table(row)
    lines+=['','## Feature obligations']
    for row in features:
        lines+=['',f"### {row['id']} — {cell(row['title'])}",'',f"Owner goal: {cell(row.get('owner_goal',''))}",
            '',f"Screens: {cell(', '.join(row.get('screen_ids',[])))}; required screens: {cell(', '.join(row.get('required_screen_ids',[])))}.",
            '',f"Wiring: `{cell(row.get('functional_wiring_status','UNSPECIFIED'))}`; integration: `{cell(row.get('frontend_integration_status','UNSPECIFIED'))}`."]
        listing('Information supplied',row.get('information',[]));listing('Owner interactions and controls',row.get('actions',[]))
        listing('Required acceptance states',row.get('required_acceptance_states',[]));listing('Declared integration gaps',row.get('integration_gaps',[]))
        listing('Current navigation contract', [row['current_navigation_contract']] if row.get('current_navigation_contract') else [])
        listing('Located source functions (not whole-feature acceptance)',[f"{f['id']}: {f.get('owner_action','')} — {f.get('status','UNSPECIFIED')}" for f in row.get('current_implementation',{}).get('functions',[])])
        endpoint_table(row)
    planned_path=ROOT/'docs/review-inputs/van-rev115/package/reference/REV2_FEATURE_REGISTRY.json'
    planned=json.loads(planned_path.read_text())
    planned_rows=planned['features']
    if planned['count']!=len(planned_rows) or len({r['id'] for r in planned_rows})!=len(planned_rows):
        raise ValueError('Planned feature inventory is incomplete or duplicated')
    lines+=['','## Complete frozen planned feature scope','',
        f"All **{len(planned_rows)} planned features** are copied below from the frozen registry. These are distinct from the {len(features)} current-source feature groups above. A frozen stage or provisional surface is a planning statement, not implementation, visual design, endpoint coverage or acceptance.",'',
        f"Source: [REV2_FEATURE_REGISTRY.json](../../../review-inputs/van-rev115/package/reference/REV2_FEATURE_REGISTRY.json); SHA-256 `{hashlib.sha256(planned_path.read_bytes()).hexdigest()}`.",'',
        '| Planned ID | Domain | Feature | Primary / provisional surface | Frozen stage |',
        '| --- | --- | --- | --- | --- |']
    for row in planned_rows:
        lines.append('| '+' | '.join(cell(x) for x in (row['id'],row['domain'],row['title'],
            str(row.get('primary_surface_id',''))+' / '+str(row.get('provisional_primary_surface_id','')),row.get('stage','UNSPECIFIED')))+' |')
    for row in planned_rows:
        lines+=['',f"#### {row['id']} — {cell(row['title'])}",'',cell(row.get('description','')),
            '',f"Technology: {cell(row.get('product_technology',''))}; functional authority: `{cell(row.get('functional_authority',''))}`; visual authority: `{cell(row.get('visual_authority',''))}`."]
        listing('Required states',row.get('required_states',[]));listing('Required identities',row.get('requirement_ids',[]))
    output='\n'.join(lines)+'\n'
    # Every identity must survive rendering, without silently trimming rows or text.
    if sum(line.startswith('### ') for line in lines)!=len(screens)+len(features):raise ValueError('Rendered row omitted')
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check',action='store_true');mode.add_argument('--apply',action='store_true');args=parser.parse_args()
    content=render();changed=not OUTPUT.is_file() or OUTPUT.read_text()!=content
    if args.apply:OUTPUT.write_text(content)
    print(json.dumps({'output':str(OUTPUT.relative_to(ROOT)),'changed':changed,'applied':args.apply,'scope':'SOURCE_CONTRACTS_ONLY'}))
    return int(args.check and changed)


if __name__=='__main__':raise SystemExit(main())
