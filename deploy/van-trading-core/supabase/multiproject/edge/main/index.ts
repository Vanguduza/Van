// Trusted main worker for ONE shared upstream Supabase Edge Runtime.
// User functions receive explicit per-function env/permissions, never this
// process's environment or the private multi-project registry. No deploy API.
import { jwtVerify, decodeProtectedHeader } from 'jose';

const utf8 = new TextEncoder();
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const digestPattern = /^[a-f0-9]{64}$/;
const namePattern = /^[a-z][a-z0-9-]{1,47}$/;
const methods = new Set(['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS']);
const ROOT_KEYS = ['schema_version','kind','worker_root','health_key','projects'];
const PROJECT_KEYS = ['project_uuid','hostname','internal_host','gateway_key','jwt_secret','anon_key','service_role_key','issuer','audience','allowed_origins','functions'];
const FUNCTION_KEYS = ['name','source','source_sha256','revision','auth','env','net_allow','memory_mb','timeout_ms','cpu_ms'];
const KIND = 'DIAL_SHARED_EDGE_PRIVATE_REGISTRY_V1';
const MAX_BODY = 1048576;
const MAX_RESPONSE = 4194304;
const MAX_CONFIG = 16777216;
const MAX_GLOBAL = 4;
const MAX_PROJECT = 2;
let active = 0;
let cleanupBarrier:Promise<void>|null = null;
const projectActive = new Map<string,number>();
const functionActive = new Set<string>();
const contexts = new Map<string,any>();
const functionCode = new Map<string,string>();
const functionKey = (p:any,f:any) => p.project_uuid + '/' + f.name + '/' + f.revision;

function exact(value:any, keys:string[]) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).sort().join('\0') !== [...keys].sort().join('\0')) throw new Error('INVALID_REGISTRY');
}
function isString(value:any, min=1, max=65536):value is string {
  return typeof value === 'string' && value.length >= min && value.length <= max && !value.includes('\0');
}
function deny() { throw new Error('INVALID_REGISTRY'); }
async function sha256(bytes:Uint8Array) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
}
function fixedEqual(a:string|null,b:string) {
  if (a === null || a.length !== b.length) return false;
  let value=0;
  for (let i=0;i<a.length;i++) value |= a.charCodeAt(i)^b.charCodeAt(i);
  return value === 0;
}
function endpoint(value:string) {
  // Literal reviewed hostname:port, not URLs, wildcard, CIDR or path patterns.
  return /^[a-z0-9][a-z0-9.-]*:[1-9][0-9]{0,4}$/.test(value) && Number(value.split(':').at(-1))<=65535;
}
function canonical(value:any):string {
  if (value===null || typeof value!=='object') return JSON.stringify(value);
  if (Array.isArray(value)) return '['+value.map(canonical).join(',')+']';
  return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
}

async function loadRegistry() {
  const path = Deno.env.get('DIAL_EDGE_REGISTRY');
  const expected = Deno.env.get('DIAL_EDGE_REGISTRY_SHA256');
  if (!path || !path.startsWith('/') || !expected || !digestPattern.test(expected)) deny();
  const info = await Deno.lstat(path);
  if (!info.isFile || info.isSymlink || info.size>MAX_CONFIG || info.nlink!==1 ||
      (info.mode!==null && (info.mode & 0o077)!==0)) deny();
  const bytes=await Deno.readFile(path);
  if (bytes.length!==info.size || await sha256(bytes)!==expected) deny();
  const config=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
  exact(config,ROOT_KEYS);
  if (config.schema_version!==1 || config.kind!==KIND || !isString(config.health_key,48,128) ||
      !isString(config.worker_root) || !config.worker_root.startsWith('/') || config.worker_root.includes('..') ||
      !Array.isArray(config.projects) || !config.projects.length || config.projects.length>32) deny();
  const ids=new Set();const hosts=new Set();const secrets=new Set();const ingress=new Set();
  for (const p of config.projects) {
    exact(p,PROJECT_KEYS);
    if (!uuid.test(p.project_uuid) || ids.has(p.project_uuid) ||
        !isString(p.hostname,3,253) || !/^[a-z0-9.-]+$/.test(p.hostname) ||
        p.internal_host!==p.project_uuid.replaceAll('-','')+'.edge.internal' || hosts.has(p.internal_host) ||
        !isString(p.jwt_secret,32,1024) || secrets.has(p.jwt_secret) ||
        !isString(p.gateway_key,48,128) || ingress.has(p.gateway_key) ||
        p.issuer!=='https://'+p.hostname+'/auth/v1' || p.audience!=='authenticated' ||
        !Array.isArray(p.allowed_origins) || p.allowed_origins.length>16 ||
        !Array.isArray(p.functions) || !p.functions.length || p.functions.length>32) deny();
    for (const origin of p.allowed_origins) {
      const u=new URL(origin);
      if (u.origin!==origin || u.protocol!=='https:' || u.username || u.password) deny();
    }
    ids.add(p.project_uuid);hosts.add(p.internal_host);secrets.add(p.jwt_secret);ingress.add(p.gateway_key);
    for (const [role,key] of [['anon',p.anon_key],['service_role',p.service_role_key]]) {
      if (!isString(key,32,8192)) deny();
      const {payload}=await jwtVerify(key,utf8.encode(p.jwt_secret),{
        algorithms:['HS256'],issuer:p.issuer,audience:p.audience,requiredClaims:['exp','iat','role'],clockTolerance:0});
      if (payload.role!==role || payload.project_ref!==p.project_uuid) deny();
    }
    const names=new Set();
    for (const f of p.functions) {
      exact(f,FUNCTION_KEYS);
      if (!namePattern.test(f.name) || names.has(f.name) || !isString(f.source,1,1048576) ||
          !digestPattern.test(f.source_sha256) || await sha256(utf8.encode(f.source))!==f.source_sha256 ||
          !digestPattern.test(f.revision) || !['user','service_role','apikey'].includes(f.auth) ||
          !Number.isInteger(f.memory_mb) || f.memory_mb<32 || f.memory_mb>128 ||
          !Number.isInteger(f.timeout_ms) || f.timeout_ms<250 || f.timeout_ms>10000 ||
          !Number.isInteger(f.cpu_ms) || f.cpu_ms<50 || f.cpu_ms>2000 ||
          !f.env || typeof f.env!=='object' || Array.isArray(f.env) || Object.keys(f.env).length>64 ||
          !Array.isArray(f.net_allow) || f.net_allow.length>16 || f.net_allow.some((n:any)=>!isString(n)||!endpoint(n))) deny();
      for (const [k,v] of Object.entries(f.env)) {
        if (!/^[A-Z][A-Z0-9_]{0,63}$/.test(k) || !isString(v,0,16384) || /^(DENO_|LD_|NODE_|DIAL_EDGE_)/.test(k)) deny();
      }
      if (f.env.DIAL_PROJECT_ID!==p.project_uuid || f.env.SUPABASE_ANON_KEY!==p.anon_key) deny();
      if (f.env.SUPABASE_SERVICE_ROLE_KEY!==undefined && f.env.SUPABASE_SERVICE_ROLE_KEY!==p.service_role_key) deny();
      // Bind worker pool identity to both code AND secrets/permissions/auth. A
      // subsequent registry generation cannot reuse a differently scoped worker.
      const revisionInput={project_uuid:p.project_uuid,...f};delete revisionInput.revision;
      if (await sha256(utf8.encode(canonical(revisionInput)))!==f.revision) deny();
      names.add(f.name);functionCode.set(functionKey(p,f),f.source);
    }
    contexts.set(p.internal_host,p);
  }
  return config;
}
const registry=await loadRegistry();

function response(status:number,code:string,req:Request,p?:any,requestId?:string) {
  const headers=new Headers({'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});
  if (requestId) headers.set('X-Dial-Request-ID',requestId);
  const origin=req.headers.get('origin');
  if (p && origin && p.allowed_origins.includes(origin)) {headers.set('Access-Control-Allow-Origin',origin);headers.set('Vary','Origin');}
  return new Response(JSON.stringify({error:code}),{status,headers});
}
async function boundedBytes(stream:ReadableStream<Uint8Array>|null,limit:number,signal?:AbortSignal) {
  if (!stream) return new Uint8Array();
  signal?.throwIfAborted();
  const reader=stream.getReader();let total=0;const chunks=[];
  const onAbort=()=>{reader.cancel().catch(()=>{});};
  signal?.addEventListener('abort',onAbort,{once:true});
  try {
    while(true) {signal?.throwIfAborted();const {done,value}=await reader.read();signal?.throwIfAborted();if(done)break;total+=value.byteLength;if(total>limit)throw new Error('BODY_LIMIT');chunks.push(value);}
  } catch(e) {await reader.cancel().catch(()=>{});throw e;} finally {signal?.removeEventListener('abort',onAbort);reader.releaseLock();}
  const result=new Uint8Array(total);let offset=0;for(const chunk of chunks){result.set(chunk,offset);offset+=chunk.byteLength;}return result;
}
async function verifyRequest(req:Request,p:any,f:any) {
  const key=req.headers.get('apikey');
  if (!fixedEqual(key,p.anon_key) && !fixedEqual(key,p.service_role_key)) throw new Error('UNAUTHORIZED');
  const raw=req.headers.get('authorization');
  if (raw!==null && !/^Bearer [A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(raw)) throw new Error('UNAUTHORIZED');
  const token=raw ? raw.slice(7):key!;
  const header=decodeProtectedHeader(token);
  if (header.alg!=='HS256' || header.jku!==undefined || header.jwk!==undefined || header.x5u!==undefined) throw new Error('UNAUTHORIZED');
  const {payload}=await jwtVerify(token,utf8.encode(p.jwt_secret),{
    algorithms:['HS256'],issuer:p.issuer,audience:p.audience,requiredClaims:['exp','iat','role'],clockTolerance:0});
  if (!['anon','authenticated','service_role'].includes(String(payload.role))) throw new Error('UNAUTHORIZED');
  if (f.auth==='user' && (payload.role!=='authenticated'||typeof payload.sub!=='string'||!uuid.test(payload.sub))) throw new Error('UNAUTHORIZED');
  if (f.auth==='service_role' && payload.role!=='service_role') throw new Error('UNAUTHORIZED');
  return {token,subject:payload.sub??null,role:payload.role};
}

Deno.serve(async(req:Request)=>{
  const url=new URL(req.url);
  if (url.pathname==='/_internal/health') {
    if (!fixedEqual(req.headers.get('x-dial-edge-health'),registry.health_key)) return response(404,'NOT_FOUND',req);
    return Response.json({state:'CANDIDATE_RUNTIME_READY_NOT_PRODUCTION',project_count:contexts.size},{headers:{'Cache-Control':'no-store'}});
  }
  const host=req.headers.get('host');const p=host?contexts.get(host):undefined;
  const requestId=crypto.randomUUID();
  if (!p || !fixedEqual(req.headers.get('x-dial-edge-gateway'),p.gateway_key)) return response(421,'PROJECT_ROUTE_REFUSED',req,undefined,requestId);
  if (!methods.has(req.method) || req.headers.has('upgrade')) return response(405,'METHOD_REFUSED',req,p,requestId);
  if (url.pathname.length>2048 || url.pathname.includes('%') || url.pathname.includes('\\') || url.pathname.includes('//')) return response(400,'PATH_REFUSED',req,p,requestId);
  const name=url.pathname.split('/')[1];const f=p.functions.find((x:any)=>x.name===name);
  if (!f) return response(404,'FUNCTION_NOT_REGISTERED',req,p,requestId);
  const origin=req.headers.get('origin');
  if (origin && !p.allowed_origins.includes(origin)) return response(403,'ORIGIN_REFUSED',req,p,requestId);
  if(req.method==='OPTIONS') {
    if (!origin || !p.allowed_origins.includes(origin)) return response(403,'ORIGIN_REFUSED',req,p,requestId);
    return new Response(null,{status:204,headers:{'Access-Control-Allow-Origin':origin,'Vary':'Origin',
      'Access-Control-Allow-Methods':'GET,HEAD,POST,PUT,PATCH,DELETE,OPTIONS',
      'Access-Control-Allow-Headers':'authorization,apikey,content-type,x-client-info',
      'Access-Control-Max-Age':'600','Cache-Control':'no-store'}});
  }
  let identity;
  try {identity=await verifyRequest(req,p,f);} catch {return response(401,'FUNCTION_AUTH_REFUSED',req,p,requestId);}
  // No new worker may enter while a previous native idle cleanup is in flight.
  while(cleanupBarrier!==null) await cleanupBarrier;
  const key=functionKey(p,f);const count=projectActive.get(p.project_uuid)??0;
  if (active>=MAX_GLOBAL||count>=MAX_PROJECT||functionActive.has(key)) return response(429,'FUNCTION_CAPACITY_BUSY',req,p,requestId);
  active++;projectActive.set(p.project_uuid,count+1);functionActive.add(key);
  const abort=new AbortController();let timedOut=false;let released=false;
  let rejectDeadline:(reason?:any)=>void;
  const deadline=new Promise<never>((_,reject)=>{rejectDeadline=reject;});
  const timer=setTimeout(()=>{timedOut=true;abort.abort();rejectDeadline(new Error('FUNCTION_DEADLINE'));},f.timeout_ms+500);
  const release=()=>{
    if(released)return;released=true;clearTimeout(timer);abort.abort();
    active--;functionActive.delete(key);
    projectActive.set(p.project_uuid,(projectActive.get(p.project_uuid)??1)-1);
    if(active===0 && cleanupBarrier===null) {
      cleanupBarrier=EdgeRuntime.userWorkers.tryCleanupIdleWorkers(100).then(()=>{},()=>{}).finally(()=>{cleanupBarrier=null;});
    }
  };
  const execution=(async()=>{
    const declared=req.headers.get('content-length');
    if(declared && (!/^\d+$/.test(declared)||Number(declared)>MAX_BODY))return response(413,'FUNCTION_BODY_TOO_LARGE',req,p,requestId);
    const body=await boundedBytes(req.body,MAX_BODY,abort.signal);
    const headers=new Headers(req.headers);
    for(const k of [...headers.keys()]) if(k.startsWith('x-dial-')||k.startsWith('x-forwarded-')||['forwarded','x-tenant-id','x-project-id','connection','content-length'].includes(k))headers.delete(k);
    headers.set('Host',p.hostname);headers.set('Authorization','Bearer '+identity.token);
    headers.set('X-Dial-Project-ID',p.project_uuid);headers.set('X-Dial-Request-ID',requestId);
    const forwarded=new Request('https://'+p.hostname+'/functions/v1'+url.pathname+url.search,
      {method:req.method,headers,body:['GET','HEAD'].includes(req.method)?undefined:body,signal:abort.signal});
    EdgeRuntime.applySupabaseTag(req,forwarded);
    const worker=await EdgeRuntime.userWorkers.create({
      servicePath:registry.worker_root+'/'+p.project_uuid+'/'+f.name+'/'+f.revision,
      maybeModuleCode:functionCode.get(key),
      envVars:Object.entries(f.env),forceCreate:false,noModuleCache:true,noNpm:true,allowRemoteModules:false,
      memoryLimitMb:f.memory_mb,workerTimeoutMs:f.timeout_ms+750,cpuTimeSoftLimitMs:f.cpu_ms,cpuTimeHardLimitMs:f.cpu_ms+100,
      permissions:{allow_all:false,allow_env:Object.keys(f.env),
        allow_net:f.net_allow.length?f.net_allow:null,deny_net:f.net_allow.length?null:[],
        allow_read:null,deny_read:[],allow_write:null,deny_write:[],
        allow_run:null,deny_run:[],allow_ffi:null,deny_ffi:[],allow_sys:null,deny_sys:[],allow_import:null},
      context:{projectRef:p.project_uuid},
    });
    const result=await worker.fetch(forwarded,{signal:abort.signal});
    const bytes=await boundedBytes(result.body,MAX_RESPONSE,abort.signal);
    const out=new Headers(result.headers);
    for(const k of [...out.keys()])if(k.startsWith('access-control-')||k.startsWith('x-dial-')||['connection','transfer-encoding','content-length','set-cookie'].includes(k))out.delete(k);
    out.set('X-Dial-Request-ID',requestId);out.set('X-Content-Type-Options','nosniff');out.set('Cache-Control','no-store');
    if(origin){out.set('Access-Control-Allow-Origin',origin);out.set('Vary','Origin');}
    return new Response(req.method==='HEAD'||[204,205,304].includes(result.status)?null:bytes,{status:result.status,headers:out});
  })();
  // On an HTTP deadline the original native execution remains owned until its
  // settlement/hard worker lifetime, so a timeout cannot exceed admission caps.
  execution.then(release,release);
  try {return await Promise.race([execution,deadline]);}
  catch {
    return response(timedOut?504:502,timedOut?'FUNCTION_DEADLINE':'FUNCTION_EXECUTION_FAILED',req,p,requestId);
  }
});
