#!/usr/bin/env python3
"""Render an offline reading copy. Document processing only, no VAN execution."""
from pathlib import Path
import json,re,html
import mistune
from bs4 import BeautifulSoup
R=Path(__file__).resolve().parents[1]
name='VAN_FORECAST_ADOPTION_BLUEPRINT_REV1_1_20261017'
md=mistune.create_markdown(escape=True,plugins=['table'])
text=(R/(name+'.md')).read_text(encoding='utf-8')
sources=json.loads((R/'references/SOURCE_REGISTER.json').read_text())['sources']
soup=BeautifulSoup(md(text),'html.parser')
used=set()
for heading in soup.find_all(re.compile(r'^h[1-6]$')):
    title=heading.get_text(' ',strip=True)
    slug=re.sub(r'[^a-z0-9]+','-',title.lower()).strip('-')
    original=slug;i=2
    while slug in used:slug=original+'-'+str(i);i+=1
    used.add(slug);heading['id']=slug
# Citation anchors in ordinary text; do not convert S24 phone names.
for node in list(soup.find_all(string=True)):
    if node.parent.name in ('pre','code','a','style','script'):continue
    old=str(node)
    if not re.search(r'\[S\d{2}[^\]]*\]',old):continue
    parts=[];start=0
    for hit in re.finditer(r'\[S\d{2}[^\]]*\]',old):
        parts.append(html.escape(old[start:hit.start()]))
        citation=html.escape(hit.group())
        citation=re.sub(r'S\d{2}',lambda x:f'<a class="cite" href="#source-{x.group()}">{x.group()}</a>',citation)
        parts.append(citation);start=hit.end()
    parts.append(html.escape(old[start:]))
    fragment=BeautifulSoup(''.join(parts),'html.parser')
    for n in list(fragment.contents):node.insert_before(n)
    node.extract()
for i,table in enumerate(soup.find_all('table'),1):
    wrap=soup.new_tag('div',attrs={'class':'table-scroll','tabindex':'0','role':'region','aria-label':f'Scrollable table {i}'})
    table.wrap(wrap)
    for cell in table.find_all('th'):cell['scope']='col'
toc=''.join(f'<a href="#{h["id"]}">{html.escape(h.get_text(" ",strip=True))}</a>' for h in soup.find_all('h2'))
sourcehtml='<section class="source-register" aria-label="Primary source register">'
sourcehtml+='<p class="source-note">Reference observations establish their stated scope, not implementation, permissions, profitability or independent qualification. S01–S25 preserve earlier observations. S26–S42 are revision inputs.</p>'
for s in sources:
    sourcehtml+=f'<article class="source" id="source-{s["id"]}"><h3>{s["id"]} · {html.escape(s["title"])}</h3><p class="meta">{html.escape(s["source_type"].replace("_"," "))} · Observed {s["observed_on"]}</p><p>{html.escape(s["scope_note"])}</p>'
    for loc in s['locations']:
        if loc.startswith('https://'):
            sourcehtml+=f'<p class="source-link"><a href="{html.escape(loc,quote=True)}" rel="noopener noreferrer">{html.escape(loc)}</a></p>'
        else:sourcehtml+=f'<p class="source-link"><code>{html.escape(loc)}</code></p>'
    if s.get('observed_fingerprint'):sourcehtml+=f'<p class="source-link">Fingerprint: <code>{html.escape(s["observed_fingerprint"])}</code></p>'
    sourcehtml+='</article>'
sourcehtml+='</section>'
css='''
:root{color-scheme:light dark;--bg:#f3f5f7;--paper:#fff;--fg:#18242d;--muted:#51616f;--line:#d7e0e7;--accent:#086777;--wash:#edf5f6;--code:#edf1f5;--shadow:0 8px 40px rgba(25,40,55,.06)}
@media(prefers-color-scheme:dark){:root{--bg:#101820;--paper:#16222c;--fg:#e7edf2;--muted:#afbeca;--line:#35434f;--accent:#7ad2d6;--wash:#1c333c;--code:#21323f;--shadow:none}}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:5rem}body{margin:0;overflow-x:clip;background:var(--bg);color:var(--fg);font:16px/1.72 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:var(--accent);text-decoration-thickness:1px;text-underline-offset:.2em;overflow-wrap:anywhere}a:focus-visible,summary:focus-visible,.table-scroll:focus-visible{outline:3px solid var(--accent);outline-offset:3px}.skip{position:absolute;top:-80px;left:1rem;z-index:100}.skip:focus{top:.4rem;padding:.4rem;background:var(--paper)}.topbar{border-bottom:1px solid var(--line);background:var(--paper);padding:.75rem max(1rem,calc((100vw - 1080px)/2));display:flex;justify-content:space-between;gap:1rem;position:sticky;top:0;z-index:10;font-size:.82rem;line-height:1.4}.topbar strong{letter-spacing:.1em}.topbar a{white-space:nowrap}.cover{max-width:1080px;margin:2.2rem auto 1rem;padding:0 1.4rem}.eyebrow{text-transform:uppercase;letter-spacing:.13em;color:var(--accent);font-size:.76rem;font-weight:700}.cover h1{font-size:clamp(1.85rem,4vw,2.85rem);line-height:1.17;max-width:860px;margin:.55rem 0 1rem;letter-spacing:-.025em}.lede{max-width:780px;color:var(--muted);font-size:1.05rem}.badges{display:flex;flex-wrap:wrap;gap:.5rem;margin:1.2rem 0}.badge{border:1px solid var(--line);padding:.3rem .65rem;border-radius:5px;font-size:.8rem;background:var(--paper)}.quick{background:var(--wash);border-left:4px solid var(--accent);padding:1rem 1.2rem;margin:1.2rem 0}.quick p{margin:0}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:.7rem;margin:1.5rem 0}.stat{background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:1rem}.stat strong{display:block;font-size:1.6rem;line-height:1.2}.stat span{font-size:.82rem;color:var(--muted)}details.contents{border:1px solid var(--line);border-radius:8px;padding:.9rem 1rem;background:var(--paper);margin:1.4rem 0}summary{cursor:pointer;font-weight:650}nav.toc{display:grid;grid-template-columns:1fr 1fr;gap:.3rem 1rem;margin:1rem 0}.toc a{font-size:.88rem;padding:.3rem 0;text-decoration:none;line-height:1.5}.toc a:hover{text-decoration:underline}main{max-width:1080px;background:var(--paper);box-shadow:var(--shadow);border:1px solid var(--line);border-radius:9px;margin:1rem auto 2.5rem;padding:2.4rem 3rem}main>h1{font-size:1.8rem;line-height:1.3;margin-top:0}h2{font-size:1.52rem;line-height:1.35;letter-spacing:-.015em;margin:2.8rem 0 1.1rem;scroll-margin-top:5rem}h3{font-size:1.15rem;line-height:1.4;margin:1.9rem 0 .8rem}p{margin:.9rem 0;overflow-wrap:break-word}blockquote{margin:1.3rem 0;padding:.1rem 1.2rem;border-left:3px solid var(--accent);background:var(--wash)}hr{border:0;border-top:1px solid var(--line);margin:2.3rem 0}ul,ol{padding-left:1.45rem}li{margin:.35rem 0}code{font: .86em/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;background:var(--code);border-radius:3px;padding:.12rem .28rem;overflow-wrap:anywhere}pre{background:var(--code);border:1px solid var(--line);border-radius:7px;padding:1rem 1.1rem;overflow-x:auto;line-height:1.6;tab-size:2}pre code{padding:0;background:transparent;overflow-wrap:normal;white-space:pre}.table-scroll{margin:1.2rem 0;max-width:100%;overflow:auto;border:1px solid var(--line);border-radius:6px}table{border-collapse:collapse;width:100%;font-size:.88rem;line-height:1.58;min-width:590px}th,td{text-align:left;vertical-align:top;padding:.72rem .8rem;border-bottom:1px solid var(--line)}th{background:var(--wash);font-weight:700}tr:last-child td{border-bottom:none}td:first-child{min-width:140px}table code{font-size:.9em}.cite{font-weight:650;font-size:.9em;text-decoration:none}.meta{font-size:.77rem;color:var(--muted);text-transform:uppercase;letter-spacing:.035em}.source{padding:1.1rem 0;border-top:1px solid var(--line)}.source h3{margin:.3rem 0}.source p{font-size:.9rem;margin:.5rem 0}.source-link{overflow-wrap:anywhere;font-size:.78rem!important}.source-note{color:var(--muted)}footer{max-width:1080px;margin:0 auto 2rem;padding:0 1.4rem;font-size:.83rem;color:var(--muted)}
@media(max-width:720px){body{font-size:15px;line-height:1.73}.topbar{position:static;padding:.8rem 1rem;font-size:.74rem}.cover{margin:1.2rem auto .8rem;padding:0 1rem}.cover h1{font-size:1.85rem}.lede{font-size:.95rem}.stats{grid-template-columns:repeat(2,1fr);gap:.5rem}.stat{padding:.8rem}.stat strong{font-size:1.45rem}nav.toc{grid-template-columns:1fr}main{margin:0 .6rem 1.4rem;padding:1.1rem 1rem;border-radius:7px}main>h1{font-size:1.43rem}h2{font-size:1.28rem;margin-top:2.2rem}h3{font-size:1.04rem}pre{font-size:.82rem;padding:.8rem}table{min-width:620px;font-size:.82rem}.quick{padding:.85rem 1rem}.badges{gap:.4rem}.badge{font-size:.72rem}td,th{padding:.65rem}blockquote{padding:.1rem .8rem}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media print{.topbar,.skip,details.contents{display:none}body{background:white;color:black;font-size:10pt}main{border:0;box-shadow:none;margin:0;padding:0;max-width:none}.cover{margin:0;padding:0}.table-scroll{overflow:visible}table{min-width:0;font-size:8pt}pre{white-space:pre-wrap}pre code{white-space:pre-wrap}a{color:inherit}.source,pre,blockquote,tr{break-inside:avoid}}
'''
body=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light dark"><meta name="description" content="VAN Rev1.1 forecasting and prediction-market implementation blueprint. Finalized specification; no application or trading authority."><title>VAN Forecast Adoption · Rev1.1</title><style>{css}</style></head><body><a class="skip" href="#document">Skip to blueprint</a><header class="topbar"><strong>VAN / VATI · ENGINEERING</strong><a href="#contents">Contents</a></header><section class="cover"><div class="eyebrow">Finalized specification · 17 October 2026 · Revision 1.1</div><h1>Forecasting, quant research<br>and prediction-market intelligence</h1><p class="lede">Qlib, LightGBM, FreqAI-inspired operations and NeuralForecast, extended with event expectations, conditional asset response and complete event research laboratories.</p><div class="badges"><span class="badge">Netcup / Oracle topology</span><span class="badge">No licence procurement this phase</span><span class="badge">One VAN risk and execution authority</span></div><div class="quick"><p><strong>Integrated, not a replacement.</strong> Original model scope is preserved. New prediction-market backend work is part of the same dependency graph and remains before the whole-product frontend barrier.</p></div><div class="stats"><div class="stat"><strong>48</strong><span>Child work packages</span></div><div class="stat"><strong>90</strong><span>Engineering requirements</span></div><div class="stat"><strong>180</strong><span>Application test contracts</span></div><div class="stat"><strong>18</strong><span>Principal typed schemas</span></div></div><p class="meta">Application tests NOT_RUN · Independent parent admission pending · No live financial permission</p><details class="contents" id="contents"><summary>Open document contents</summary><nav class="toc" aria-label="Document sections">{toc}</nav></details><p><a href="#22-integrated-prediction-market-intelligence-and-event-research">Go to the integrated prediction-market chapter →</a></p></section><main id="document">{soup}{sourcehtml}</main><footer>Offline reading copy of {name}.md. This is documentation, not a VAN application screen. Source observations, engineering tests, economic evidence and live authority remain distinct.</footer></body></html>'''
(R/(name+'.html')).write_text(body,encoding='utf-8')
print(json.dumps({'html':str(R/(name+'.html')),'bytes':len(body.encode()),'toc_sections':len(soup.find_all('h2')),'sources':len(sources)}))
