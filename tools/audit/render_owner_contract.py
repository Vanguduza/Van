"""Render the registry as a self-contained, searchable review artifact."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def render():
    feature_document = json.loads((ROOT / "registries/owner_features.json").read_text())
    data = {
        "features": feature_document["features"],
        "screens": json.loads((ROOT / "registries/owner_screens.json").read_text())["screens"],
        "endpoints": json.loads((ROOT / "registries/owner_endpoints.json").read_text())["endpoints"],
    }
    payload = json.dumps(data).replace("<", "\\u003c")
    template = r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VAN owner frontend contract</title>
<style>
:root{color-scheme:light dark;font-family:system-ui,sans-serif}body{max-width:1100px;margin:auto;padding:24px;line-height:1.5}h1{margin-bottom:4px}p{max-width:85ch}nav{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}input,select,button{font:inherit;padding:9px;border:1px solid #89959a;border-radius:6px}input{flex:1;min-width:220px}button[aria-pressed=true]{background:#165c72;color:white}article{border:1px solid #89959a;border-radius:8px;padding:16px;margin:14px 0}article h2{font-size:1.2rem;margin:0}small{display:block;color:#72808a}.badge{display:inline-block;padding:3px 7px;background:#647b8522;border-radius:4px;margin:5px 5px 0 0}details{margin-top:12px}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.85rem}li{margin:4px 0}.note{border-left:4px solid #b88318;padding-left:15px}code{overflow-wrap:anywhere}#count{margin:12px 0}@media print{nav{display:none}details{display:block}article{break-inside:avoid}}
</style>
<h1>VAN owner frontend contract</h1>
<p>__DATE__ · Audited owner functions, wired screens and endpoint access, with historical evidence retained. Source implementation, local validation, deployment and live handset acceptance are separate.</p>
<p class="note">Internal control endpoints belong to service adapters. Android must use an admitted signed owner path or a safe owner projection. Proposed routes are design requirements, not implemented navigation.</p>
<nav aria-label="Registry controls"><button data-tab="features" aria-pressed="true">Owner capabilities</button><button data-tab="screens" aria-pressed="false">Screens</button><button data-tab="endpoints" aria-pressed="false">Endpoints</button><input id="search" type="search" aria-label="Search registry" placeholder="Search goal, control, screen or endpoint"><select id="basis" aria-label="Coverage evidence"><option value="current_coverage_status">Current source</option><option value="baseline_coverage_status">Audit baseline</option></select><select id="coverage" aria-label="Coverage filter"><option value="">All coverage</option><option>partial</option><option>missing</option><option>external</option><option>implemented</option></select></nav>
<div id="count" role="status" aria-live="polite"></div><main id="list"></main>
<script id="registry" type="application/json">__DATA__</script>
<script>
const data=JSON.parse(document.getElementById('registry').textContent),ep=new Map(data.endpoints.map(e=>[e.endpoint_id,e]));let tab='features';
function node(tag,text,parent){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(parent)parent.appendChild(n);return n}
function list(title,items,parent){if(!items?.length)return;node('strong',title,parent);const ul=node('ul',undefined,parent);items.forEach(x=>node('li',typeof x==='string'?x:JSON.stringify(x),ul))}
function details(title,value,parent){const d=node('details',undefined,parent);node('summary',title,d);node('pre',JSON.stringify(value,null,2),d)}
function draw(){const query=document.getElementById('search').value.toLowerCase(),coverage=tab==='endpoints'?'':document.getElementById('coverage').value,basis=document.getElementById('basis').value,rows=data[tab].filter(x=>(!query||JSON.stringify(x).toLowerCase().includes(query))&&(!coverage||(x[basis]||x.baseline_coverage_status)===coverage));const main=document.getElementById('list');main.replaceChildren();document.getElementById('count').textContent=`${rows.length} of ${data[tab].length} ${tab}`;
rows.forEach(x=>{const a=node('article',undefined,main);node('h2',x.title||`${x.method} ${x.path}`,a);node('small',x.id||x.endpoint_id,a);
if(x.current_coverage_status)node('span',`Current source: ${x.current_coverage_status}`,a).className='badge';if(x.baseline_coverage_status)node('span',`Baseline: ${x.baseline_coverage_status}`,a).className='badge';if(x.authentication)node('span',x.authentication,a).className='badge';if(x.registration)node('span',`Registration: ${x.registration}`,a).className='badge';
if(x.functional_wiring_status)node('span',`Functional wiring: ${x.functional_wiring_status}`,a).className='badge';if(x.gap_categories?.length)list('Remaining work categories',x.gap_categories,a);
if(x.owner_goal)node('p',x.owner_goal,a);if(x.route||x.proposed_route)node('p',`${x.route?'Source route':'Proposed route'}: ${x.route||x.proposed_route}`,a);else if(x.host_route||x.host_activity)node('p',`${x.interaction_kind||'Hosted control'} in ${x.host_route||x.host_activity}`,a);list('Information',x.information,a);list('Owner interactions',x.actions,a);list('Remaining work and supported scope',x.integration_gaps||x.gaps,a);
if(x.endpoint_refs){const refs=x.endpoint_refs.map(r=>{const e=ep.get(r.endpoint_id);return {method:r.method,path:r.path,access:r.frontend_access,authentication:e?.authentication,hardware_proof:e?.device_proof_required_when_bound,registration:e?.registration,source:e?.source,endpoint_id:r.endpoint_id}});details('Endpoint contracts and access',refs,a)}
if(x.required_acceptance_states||x.acceptance_states)details('Happy and error-state acceptance',x.required_acceptance_states||x.acceptance_states,a);if(x.screen_ids)details('Screen links',x.screen_ids,a);if(x.feature_ids)details('Capability links',x.feature_ids,a);if(tab==='endpoints')details('Parameters, body, responses and additional gates',x,a);
if(x.current_implementation)details('Implemented controls, source and local verification',x.current_implementation,a);if(x.baseline_provenance)details('Frozen audit baseline',x.baseline_provenance,a);details('Source evidence / full registry entry',x,a)})}
document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>{tab=b.dataset.tab;document.querySelectorAll('[data-tab]').forEach(z=>z.setAttribute('aria-pressed',String(z===b)));document.getElementById('coverage').disabled=tab==='endpoints';document.getElementById('basis').disabled=tab==='endpoints';draw()}));document.getElementById('search').addEventListener('input',draw);document.getElementById('coverage').addEventListener('change',draw);document.getElementById('basis').addEventListener('change',draw);draw();
</script></html>'''
    target = ROOT / "docs/audit/OWNER_FRONTEND_CONTRACT.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(template.replace("__DATA__", payload).replace("__DATE__", feature_document["audit_date"]))
    print(f"Rendered {len(data['features'])} features, {len(data['screens'])} screens and {len(data['endpoints'])} endpoints")


if __name__ == "__main__":
    render()
