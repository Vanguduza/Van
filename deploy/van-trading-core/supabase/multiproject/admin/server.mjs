// One private project-aware gateway in front of the existing Studio + pg-meta.
// It verifies existing-issuer operator tokens; it does not issue credentials.
import http from 'node:http';
import {Admission} from './admission.mjs';
import fs from 'node:fs/promises';
import { createHash,createCipheriv,randomBytes,timingSafeEqual } from 'node:crypto';
import { importJWK,jwtVerify } from 'jose';

const MAX_REQUEST=262144,MAX_RESPONSE=4194304;
const isUuid=x=>typeof x==='string'&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(x);
const sha=x=>createHash('sha256').update(x).digest('hex');
function exact(value,keys){if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).sort().join('|')!==[...keys].sort().join('|'))throw Error('INVALID_ADMIN_REGISTRY');}
function equal(a,b){return typeof a==='string'&&typeof b==='string'&&a.length===b.length&&timingSafeEqual(Buffer.from(a),Buffer.from(b));}
const path=process.env.DIAL_PROJECT_ADMIN_REGISTRY,expected=process.env.DIAL_PROJECT_ADMIN_REGISTRY_SHA256;
if(!path?.startsWith('/')||!/^[a-f0-9]{64}$/.test(expected??''))throw Error('ADMIN_REGISTRY_REQUIRED');
const info=await fs.lstat(path);
if(!info.isFile()||info.isSymbolicLink()||info.nlink!==1||(info.mode&0o077)||info.size>1048576)throw Error('PRIVATE_REGISTRY_REQUIRED');
const bytes=await fs.readFile(path);
if(sha(bytes)!==expected)throw Error('REGISTRY_DIGEST_MISMATCH');
const config=JSON.parse(bytes.toString('utf8'));
exact(config,['schema_version','origin','meta_url','studio_url','crypto_key','health_key','issuer','audience','public_jwk','operators','projects']);
if(config.schema_version!==1||typeof config.crypto_key!=='string'||config.crypto_key.length<32||typeof config.health_key!=='string'||config.health_key.length<48)throw Error('INVALID_ADMIN_REGISTRY');
const origin=new URL(config.origin);
if(origin.protocol!=='https:'||origin.origin!==config.origin)throw Error('ADMIN_HTTPS_ORIGIN_REQUIRED');
for(const name of ['meta_url','studio_url']){const u=new URL(config[name]);if(u.protocol!=='http:'||u.username||u.password||!['127.0.0.1','meta','studio'].includes(u.hostname)||u.pathname!=='/')throw Error('PRIVATE_UPSTREAM_REQUIRED');}
if(config.public_jwk.kty!=='OKP'||config.public_jwk.crv!=='Ed25519'||'d' in config.public_jwk)throw Error('VERIFIER_PUBLIC_KEY_ONLY');
const verification=await importJWK(config.public_jwk,'EdDSA');
if(!Array.isArray(config.projects)||config.projects.length<1||config.projects.length>32||!Array.isArray(config.operators)||!config.operators.length)throw Error('INVALID_ADMIN_REGISTRY');
const projects=new Map();
for(const p of config.projects){
  exact(p,['ref','name','database','database_user','connection','rest_url']);
  if(!isUuid(p.ref)||projects.has(p.ref)||typeof p.name!=='string'||p.name.length>80||!/^dial_[a-f0-9]{32}_admin$/.test(p.database_user))throw Error('PROJECT_IDENTITY_INVALID');
  const u=new URL(p.connection);
  if(u.protocol!=='postgresql:'||u.username!==p.database_user||u.pathname!=='/'+p.database||!['db','127.0.0.1'].includes(u.hostname)||!u.password)throw Error('PROJECT_DATABASE_BINDING_INVALID');
  if(p.database_user!=='dial_'+p.ref.replaceAll('-','')+'_admin')throw Error('PROJECT_ROLE_BINDING_INVALID');
  projects.set(p.ref,p);
}
const operators=new Map();
for(const o of config.operators){
  exact(o,['subject','projects','can_query']);
  if(typeof o.subject!=='string'||operators.has(o.subject)||!Array.isArray(o.projects)||o.projects.some(p=>!projects.has(p))||typeof o.can_query!=='boolean')throw Error('OPERATOR_SCOPE_INVALID');
  operators.set(o.subject,o);
}
// CryptoJS/OpenSSL-compatible AES envelope consumed by the pinned native pg-meta.
// This connection ciphertext is generated server-side; client pg headers ignored.
function encryptConnection(text){
  const salt=randomBytes(8),password=Buffer.from(config.crypto_key);let result=Buffer.alloc(0),prior=Buffer.alloc(0);
  while(result.length<48){prior=createHash('md5').update(Buffer.concat([prior,password,salt])).digest();result=Buffer.concat([result,prior]);}
  const cipher=createCipheriv('aes-256-cbc',result.subarray(0,32),result.subarray(32,48));
  return Buffer.concat([Buffer.from('Salted__'),salt,cipher.update(text,'utf8'),cipher.final()]).toString('base64');
}
function respond(res,status,data,headers={}){const body=JSON.stringify(data);res.writeHead(status,{'content-type':'application/json','cache-control':'no-store','x-content-type-options':'nosniff',...headers});res.end(body);}
async function bounded(stream,limit){let total=0;const parts=[];for await(const p of stream){total+=p.length;if(total>limit)throw Error('BODY_LIMIT');parts.push(p);}return Buffer.concat(parts);}
function projectView(p,verified=false){return {id:p.ref,ref:p.ref,name:p.name,organization_id:1,cloud_provider:'localhost',region:'local',status:verified?'ACTIVE_HEALTHY':'INACTIVE',dial_database_connection_verified:verified,inserted_at:'2026-11-04T00:00:00.000Z',connectionString:'',restUrl:p.rest_url,dial_scope:'DATABASE_ADMIN_CANDIDATE_NOT_PRODUCTION_ACCEPTANCE'};}
async function verifyDatabase(p,timeout=1500){
  try{
    const response=await fetch(config.meta_url+'/query',{method:'POST',headers:{'content-type':'application/json','x-connection-encrypted':encryptConnection(p.connection)},body:JSON.stringify({query:'SELECT current_database() AS db,current_user AS role'}),signal:AbortSignal.timeout(timeout),redirect:'error'});
    const bytes=await bounded(response.body,4096);if(!response.ok)return false;
    const value=JSON.parse(bytes.toString('utf8'));
    return Array.isArray(value)&&value.length===1&&value[0].db===p.database&&value[0].role===p.database_user;
  }catch{return false;}
}
async function visibleCatalogue(refs){
  const result=[],deadline=Date.now()+2500;
  for(const ref of refs){const p=projects.get(ref);const remaining=deadline-Date.now();result.push(projectView(p,remaining>0?await verifyDatabase(p,Math.max(1,Math.min(1500,remaining))):false));}
  return result;
}
async function authorization(req){
  let token,fromCookie=false;
  const item=(req.headers.cookie??'').split(';').map(x=>x.trim()).find(x=>x.startsWith('__Host-dial-admin='));
  if(item){token=item.slice('__Host-dial-admin='.length);fromCookie=true;}
  else if(req.headers.authorization){const match=/^Bearer ([A-Za-z0-9_.-]+)$/.exec(req.headers.authorization);if(!match)throw Error('AUTH');token=match[1];}
  if(!token)throw Error('AUTH');
  const {payload}=await jwtVerify(token,verification,{algorithms:['EdDSA'],issuer:config.issuer,audience:config.audience,requiredClaims:['sub','iat','exp'],maxTokenAge:'10m',clockTolerance:0});
  if(payload.exp-payload.iat>600)throw Error('AUTH');
  const op=operators.get(payload.sub);if(!op)throw Error('AUTH');
  if(req.headers.origin&&req.headers.origin!==config.origin)throw Error('ORIGIN');
  if(fromCookie&&!['GET','HEAD'].includes(req.method)&&req.headers.origin!==config.origin)throw Error('ORIGIN');
  return op;
}
let activeAssets=0;const assetWaiters=[];
async function assetSlot(){
  if(activeAssets<4){activeAssets++;return;}
  if(assetWaiters.length>=96)throw Error('ASSET_CAPACITY');
  await new Promise((resolve,reject)=>{
    const item={resolve,timer:null};
    item.timer=setTimeout(()=>{const i=assetWaiters.indexOf(item);if(i>=0)assetWaiters.splice(i,1);reject(Error('ASSET_CAPACITY'));},12000);
    assetWaiters.push(item);
  });
}
function releaseAsset(){const next=assetWaiters.shift();if(next){clearTimeout(next.timer);next.resolve();}else activeAssets--;}
const operatorAdmission=new Admission({global:4,perSubject:2,pending:24,pendingPerSubject:12,waitMs:2500});
const server=http.createServer(async(req,res)=>{
 let releaseOperator=null,assetAdmitted=false;const disconnect=new AbortController();
 const onClose=()=>disconnect.abort();res.once('close',onClose);
 try{
  if(req.url==='/_internal/health'){
    if(!equal(req.headers['x-dial-admin-health'],config.health_key))return respond(res,404,{error:'NOT_FOUND'});
    return respond(res,200,{state:'PRIVATE_ADMIN_CANDIDATE_READY',projects:projects.size});
  }
  if(req.headers.host?.split(':')[0]!==origin.hostname)return respond(res,421,{error:'ADMIN_HOST_REFUSED'});
  if((req.url?.length??0)>2048||req.url.includes('%')||req.url.includes('\\')||req.url.includes('//')||/(^|\/)\.{1,2}(\/|$)/.test(req.url.split('?')[0]))return respond(res,400,{error:'ADMIN_PATH_REFUSED'});
  let op;try{op=await authorization(req);}catch{return respond(res,401,{error:'OPERATOR_AUTHORIZATION_REQUIRED'});}
  const allowed=new Set(op.projects),url=new URL(req.url,config.origin),p=url.pathname;
  const asset=p.startsWith('/_next/static/')||p==='/favicon.ico'||p.startsWith('/favicon/')||p.startsWith('/img/')||p.startsWith('/monaco-editor/');
  if(asset){if(!['GET','HEAD'].includes(req.method))return respond(res,405,{error:'METHOD_REFUSED'});await assetSlot();assetAdmitted=true;}
  else{try{releaseOperator=await operatorAdmission.acquire(op.subject,disconnect.signal);}
    catch{return respond(res,429,{error:'ADMIN_CAPACITY_BUSY_NO_REPLAY'});}}
  if(res.destroyed)return;

  const catalogue=()=>visibleCatalogue(op.projects);
  if(req.method==='GET'&&p==='/api/platform/projects')return respond(res,200,await catalogue());
  if(req.method==='GET'&&p==='/api/platform/profile')return respond(res,200,{id:op.subject,username:op.subject,primary_email:'',organizations:[{id:1,slug:'default-org-slug',name:'DIAL Projects',projects:await catalogue()}]});
  if(req.method==='GET'&&p==='/api/platform/organizations')return respond(res,200,[{id:1,slug:'default-org-slug',name:'DIAL Projects',plan:{id:'self-hosted',name:'Self hosted'}}]);
  const detail=/^\/api\/platform\/projects\/([a-f0-9-]+)$/.exec(p);
  if(detail){if(!allowed.has(detail[1]))return respond(res,404,{error:'PROJECT_NOT_AVAILABLE'});if(req.method!=='GET')return respond(res,405,{error:'CATALOG_READ_ONLY'});return respond(res,200,projectView(projects.get(detail[1]),await verifyDatabase(projects.get(detail[1]))));}
  const databases=/^\/api\/platform\/projects\/([a-f0-9-]+)\/databases$/.exec(p);
  if(databases){
    if(!allowed.has(databases[1]))return respond(res,404,{error:'PROJECT_NOT_AVAILABLE'});
    if(req.method!=='GET')return respond(res,405,{error:'CATALOG_READ_ONLY'});
    const selected=projects.get(databases[1]),connection=new URL(selected.connection),verified=await verifyDatabase(selected);
    return respond(res,200,[{cloud_provider:'localhost',connectionString:'',connection_string_read_only:'',
      db_host:connection.hostname,db_name:selected.database,db_port:Number(connection.port||5432),db_user:selected.database_user,
      identifier:'default',inserted_at:'',region:'local',restUrl:selected.rest_url,size:'',
      status:verified?'ACTIVE_HEALTHY':'INACTIVE',dial_database_connection_verified:verified}]);
  }
  if(req.method==='GET'&&['/api/platform/deployment-mode','/api/enabled-features-overrides','/api/get-deployment-commit'].includes(p)){
    const upstream=await fetch(config.studio_url+p,{signal:AbortSignal.timeout(5000),redirect:'error'});
    const raw=await bounded(upstream.body,65536);
    return respond(res,upstream.status,JSON.parse(raw.toString('utf8')));
  }
  const metadata=/^\/api\/platform\/pg-meta\/([a-f0-9-]+)\/(tables|schemas|columns|policies|types|views|indexes|query)$/.exec(p);
  if(metadata){
    const [_,ref,route]=metadata;if(!allowed.has(ref))return respond(res,404,{error:'PROJECT_NOT_AVAILABLE'});
    if(route==='query'?(req.method!=='POST'||!op.can_query):req.method!=='GET')return respond(res,403,{error:'OPERATION_NOT_GRANTED'});
    const project=projects.get(ref),headers={'content-type':'application/json','x-connection-encrypted':encryptConnection(project.connection)};
    let body;if(req.method==='POST'){const raw=await bounded(req,MAX_REQUEST);const value=JSON.parse(raw.toString('utf8'));if(!value||typeof value.query!=='string'||Object.keys(value).some(k=>!['query','disable_statement_timeout'].includes(k))||('disable_statement_timeout' in value&&value.disable_statement_timeout!==false))return respond(res,400,{error:'QUERY_REQUEST_INVALID_OR_TIMEOUT_BYPASS'});body=JSON.stringify({query:value.query});}
    const response=await fetch(config.meta_url+'/'+route+url.search,{method:req.method,headers,body,signal:AbortSignal.timeout(8000),redirect:'error'});
    const raw=await bounded(response.body,MAX_RESPONSE);
    if(!response.ok)return respond(res,response.status>=400&&response.status<500?response.status:502,{message:'PROJECT_DATABASE_REQUEST_FAILED'});
    return respond(res,200,JSON.parse(raw.toString('utf8')));
  }
  // Never fall through an unknown API to Studio's single default DB authority.
  if(p.startsWith('/api/'))return respond(res,501,{error:'PROJECT_API_NOT_QUALIFIED'});
  if(req.method==='GET'&&p==='/'){
    const escape=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
    res.writeHead(200,{'content-type':'text/html; charset=utf-8','cache-control':'no-store','content-security-policy':"default-src 'none'; style-src 'unsafe-inline'"});
    return res.end('<!doctype html><html><title>DIAL Project Administration</title><h1>Projects</h1>'+(await catalogue()).map(x=>'<p><a href="/project/'+x.ref+'/editor">'+escape(x.name)+'</a></p>').join('')+'<p>Private project-scoped administration. Production acceptance is separate.</p></html>');
  }
  const page=/^\/project\/([a-f0-9-]+)(\/.*)?$/.exec(p);
  if(page&&!allowed.has(page[1]))return respond(res,404,{error:'PROJECT_NOT_AVAILABLE'});
  if(!page&&!asset)return respond(res,404,{error:'ROUTE_NOT_QUALIFIED'});
  if(!['GET','HEAD'].includes(req.method))return respond(res,405,{error:'METHOD_REFUSED'});
  const upstream=await fetch(config.studio_url+p+url.search,{method:req.method,signal:AbortSignal.timeout(12000),redirect:'manual'});
  if(upstream.status>=300&&upstream.status<400)return respond(res,502,{error:'STUDIO_REDIRECT_REQUIRES_QUALIFICATION'});
  const raw=await bounded(upstream.body,asset?2*MAX_RESPONSE:8*MAX_RESPONSE);
  res.writeHead(upstream.status,{'content-type':upstream.headers.get('content-type')??'application/octet-stream','cache-control':asset?'private, max-age=86400, immutable':'no-store','x-content-type-options':'nosniff'});res.end(raw);
 }catch(error){if(!res.headersSent)respond(res,error.message==='BODY_LIMIT'?413:502,{error:'ADMIN_OPERATION_FAILED_NO_REPLAY'});else res.end();}
 finally{res.removeListener('close',onClose);if(assetAdmitted)releaseAsset();if(releaseOperator)releaseOperator();}
});
server.maxHeadersCount=64;server.headersTimeout=5000;server.requestTimeout=10000;
const host=process.env.DIAL_PROJECT_ADMIN_HOST??'127.0.0.1';const port=Number(process.env.DIAL_PROJECT_ADMIN_PORT);
if(!['127.0.0.1','0.0.0.0'].includes(host)||!Number.isInteger(port)||port<1024||port>65535)throw Error('EXACT_ADMIN_LISTENER_REQUIRED');
server.listen(port,host,()=>console.log('PRIVATE_PROJECT_ADMIN_STARTED'));
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>server.close(()=>process.exit(0)));
