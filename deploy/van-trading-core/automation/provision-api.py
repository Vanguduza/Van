#!/usr/bin/env python3
import argparse, http.cookiejar, json, os, pathlib, urllib.error, urllib.request
p=argparse.ArgumentParser(); p.add_argument('--base',default='http://127.0.0.1:5678'); p.add_argument('--secrets-dir',required=True)
a=p.parse_args(); sd=pathlib.Path(a.secrets_dir); keyfile=sd/'n8n-hermes-api.key'; pwfile=sd/'n8n-owner-password'
OWNER='van-owner@dial.invalid'; LABEL='VAN Hermes'; base=a.base.rstrip('/')
def req(url,method='GET',body=None,headers=None,opener=None):
    data=None if body is None else json.dumps(body).encode()
    h={'Accept':'application/json'}; h.update(headers or {})
    if body is not None: h['Content-Type']='application/json'
    r=urllib.request.Request(base+url,data=data,headers=h,method=method)
    try:
        with (opener or urllib.request).open(r,timeout=15) as x: return x.status,json.loads(x.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')
def test_key(k):
    st,_=req('/api/v1/workflows?limit=1',headers={'X-N8N-API-KEY':k})
    return st==200
if keyfile.exists():
    k=keyfile.read_text().strip()
    if k and test_key(k): print('N8N_API_KEY_PRESERVED'); raise SystemExit(0)
password=pwfile.read_text().strip(); jar=http.cookiejar.CookieJar(); op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
st,user=req('/rest/login','POST',{'emailOrLdapLoginId':OWNER,'password':password},opener=op)
if st!=200:
    ss,setup=req('/rest/owner/setup','POST',{'email':OWNER,'firstName':'VAN','lastName':'Owner','password':password},opener=op)
    if ss not in (200,201): raise SystemExit(f'n8n owner setup failed HTTP {ss}: {setup}')
    st,user=req('/rest/login','POST',{'emailOrLdapLoginId':OWNER,'password':password},opener=op)
if st!=200: raise SystemExit(f'n8n owner login failed HTTP {st}: {user}')
st,raw_scopes=req('/rest/api-keys/scopes',opener=op)
if st!=200: raise SystemExit(f'n8n scopes failed HTTP {st}: {raw_scopes}')
scopes=raw_scopes if isinstance(raw_scopes,list) else raw_scopes.get('data',raw_scopes.get('scopes'))
if not isinstance(scopes,list): raise SystemExit('n8n scopes response is not a list')
st,keys=req('/rest/api-keys?ownership=mine&take=100',opener=op)
if st!=200: raise SystemExit(f'n8n api-key list failed HTTP {st}: {keys}')
rows=keys if isinstance(keys,list) else keys.get('data',keys.get('items',[]))
existing=next((x for x in rows if x.get('label')==LABEL),None)
if existing:
    kid=existing.get('id')
    if not kid: raise SystemExit('existing n8n key missing id')
    st,out=req(f'/rest/api-keys/{kid}/rotate','POST',{},opener=op)
else:
    st,out=req('/rest/api-keys','POST',{'label':LABEL,'scopes':scopes,'expiresAt':None},opener=op)
if st not in (200,201): raise SystemExit(f'n8n api-key provision failed HTTP {st}: {out}')
key=out.get('rawApiKey') or out.get('apiKey')
if not key or '***' in key: raise SystemExit('n8n did not return raw API key')
fd=os.open(keyfile,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as f: f.write(key+'\n')
os.chmod(keyfile,0o600)
if not test_key(key): raise SystemExit('new n8n API key failed public API canary')
conn=sd/'n8n-connection.json'
conn.write_text(json.dumps({'api_root':'/api/v1','owner':OWNER,'key_label':LABEL},indent=2)+'\n'); os.chmod(conn,0o600)
print('N8N_API_KEY_GREEN')
