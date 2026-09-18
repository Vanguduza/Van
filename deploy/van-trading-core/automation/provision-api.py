#!/usr/bin/env python3
import argparse, http.cookiejar, json, os, pathlib, time
import urllib.error, urllib.request

p=argparse.ArgumentParser()
p.add_argument('--base',default='http://127.0.0.1:5678')
p.add_argument('--secrets-dir',required=True)
a=p.parse_args()
sd=pathlib.Path(a.secrets_dir)
keyfile=sd/'n8n-hermes-api.key'
pwfile=sd/'n8n-owner-password'
OWNER='van-owner@dial.invalid'
LABEL='VAN Hermes'
base=a.base.rstrip('/')
TRANSIENT={408,425,429,500,502,503,504}

def decode(raw):
    text=raw.decode(errors='replace')
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {'_non_json': text[:1000]}

def unwrap(obj):
    return obj.get('data',obj) if isinstance(obj,dict) else obj

def cookie_header(jar):
    pairs=[f'{c.name}={c.value}' for c in jar]
    return '; '.join(pairs)

def req(url,method='GET',body=None,headers=None,opener=None,jar=None,attempts=8):
    data=None if body is None else json.dumps(body).encode()
    h={'Accept':'application/json'}
    h.update(headers or {})
    if body is not None:
        h['Content-Type']='application/json'
    if jar:
        cookie=cookie_header(jar)
        if cookie:
            h['Cookie']=cookie
    last=None
    for attempt in range(1,attempts+1):
        r=urllib.request.Request(base+url,data=data,headers=h,method=method)
        try:
            client=opener.open if opener is not None else urllib.request.urlopen
            with client(r,timeout=15) as x:
                return x.status,decode(x.read())
        except urllib.error.HTTPError as e:
            last=(e.code,decode(e.read()))
            if e.code not in TRANSIENT:
                return last
        except urllib.error.URLError as e:
            last=(0,{'_transport':str(e.reason)})
        if attempt < attempts:
            time.sleep(min(2*attempt,10))
    return last or (0,{'_transport':'request failed'})

def test_key(k):
    st,_=req('/api/v1/workflows?limit=1',headers={'X-N8N-API-KEY':k},attempts=4)
    return st==200

if keyfile.exists():
    k=keyfile.read_text().strip()
    if k and test_key(k):
        print('N8N_API_KEY_PRESERVED')
        raise SystemExit(0)

password=pwfile.read_text().strip()
jar=http.cookiejar.CookieJar()
op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

ready=False
for _ in range(30):
    st,settings=req('/rest/settings',opener=op,attempts=1)
    if st==200:
        ready=True
        break
    time.sleep(2)
if not ready:
    raise SystemExit(f'n8n settings readiness failed HTTP {st}: {settings}')

st,user=req('/rest/login','POST',
            {'emailOrLdapLoginId':OWNER,'password':password},
            opener=op,jar=jar)
if st!=200:
    ss,setup=req('/rest/owner/setup','POST',
                 {'email':OWNER,'firstName':'VAN','lastName':'Owner','password':password},
                 opener=op,jar=jar)
    if ss not in (200,201):
        raise SystemExit(f'n8n owner setup failed HTTP {ss}: {setup}')
    st,user=req('/rest/login','POST',
                {'emailOrLdapLoginId':OWNER,'password':password},
                opener=op,jar=jar)
if st!=200:
    raise SystemExit(f'n8n owner login failed HTTP {st}: {user}')
if not cookie_header(jar):
    raise SystemExit('n8n login returned no session cookie')

st,raw_scopes=req('/rest/api-keys/scopes',opener=op,jar=jar)
if st!=200:
    raise SystemExit(f'n8n scopes failed HTTP {st}: {raw_scopes}')
scopes=unwrap(raw_scopes)
if isinstance(scopes,dict):
    scopes=scopes.get('scopes',[])
if not isinstance(scopes,list):
    raise SystemExit('n8n scopes response is not a list')
st,keys=req('/rest/api-keys?ownership=mine&take=100',opener=op,jar=jar)
if st!=200:
    raise SystemExit(f'n8n api-key list failed HTTP {st}: {keys}')
key_data=unwrap(keys)
rows=key_data if isinstance(key_data,list) else key_data.get('items',[]) if isinstance(key_data,dict) else []
existing=next((x for x in rows if x.get('label')==LABEL),None)
if existing:
    kid=existing.get('id')
    if not kid:
        raise SystemExit('existing n8n key missing id')
    st,out=req(f'/rest/api-keys/{kid}/rotate','POST',{},opener=op,jar=jar)
else:
    st,out=req('/rest/api-keys','POST',
               {'label':LABEL,'scopes':scopes,'expiresAt':None},
               opener=op,jar=jar)
if st not in (200,201):
    raise SystemExit(f'n8n api-key provision failed HTTP {st}: {out}')

out_data=unwrap(out)
if not isinstance(out_data,dict):
    raise SystemExit('n8n api-key response is not an object')
key=out_data.get('rawApiKey') or out_data.get('apiKey')
if not key or '***' in key: raise SystemExit('n8n did not return raw API key')
fd=os.open(keyfile,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as f: f.write(key+'\n')
os.chmod(keyfile,0o600)
if not test_key(key): raise SystemExit('new n8n API key failed public API canary')
conn=sd/'n8n-connection.json'
conn.write_text(json.dumps({'api_root':'/api/v1','owner':OWNER,'key_label':LABEL},indent=2)+'\n'); os.chmod(conn,0o600)
print('N8N_API_KEY_GREEN')
