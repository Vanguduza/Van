import {OWNER_OPERATIONS,invokeOwnerControl,createDialOwnerSurfaceAdapter} from './owner-controls.mjs';
/** Server-only adapter for the existing private Site. No browser or VM credential is returned. */
const TASKS=new Set(['muse_get_overview','muse_get_job','muse_get_command','muse_create_project','muse_resolve_project','muse_submit_task','muse_continue_task','muse_cancel_task']);
export function canonical(value) {
  if(value===null||typeof value==='string'||typeof value==='boolean')return JSON.stringify(value);
  if(typeof value==='number'&&Number.isSafeInteger(value))return String(value);
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value&&Object.getPrototypeOf(value)===Object.prototype)return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  throw new Error('NON_CANONICAL_VALUE');
}
export async function digest(value){const data=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(value)));return [...new Uint8Array(data)].map(b=>b.toString(16).padStart(2,'0')).join('');}
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
const from64=s=>Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-s.length%4)%4)),c=>c.charCodeAt(0));
async function body(request,max=65536){
 const reader=request.body?.getReader();if(!reader)throw Error('BODY_REQUIRED');let bytes=0;const parts=[];
 while(true){const {done,value}=await reader.read();if(done)break;bytes+=value.byteLength;if(bytes>max){await reader.cancel();throw Error('BODY_TOO_LARGE');}parts.push(value);}
 const merged=new Uint8Array(bytes);let p=0;for(const part of parts){merged.set(part,p);p+=part.length;}const v=JSON.parse(new TextDecoder().decode(merged));if(!v||Array.isArray(v)||typeof v!=='object')throw Error('BODY_INVALID');return v;
}

/** Dependencies must be supplied by the ORIGINAL Site's server, not browser code.
 * requireOwner verifies Sites identity and ownership. signOwnerEnvelope reuses its existing
 * owner signer. transport uses the existing authenticated DIAL route to /v1/muse/site.
 * invokeExistingTask reuses its real task implementation/DB; it must never be a mock in production.
 */
export function createMuseBff({siteOrigin,audience,ownerSubject,policyGeneration=1,requireOwner,signOwnerEnvelope,transport,gatewayPublicJwk,invokeExistingTask,nativeOwnerControls,callExistingOwnerTool,now=()=>Date.now()}) {
 nativeOwnerControls??=createDialOwnerSurfaceAdapter(callExistingOwnerTool);
 const root=new URL(siteOrigin);if(root.protocol!=='https:'||root.origin!==siteOrigin)throw Error('SITE_ORIGIN_INVALID');
 const matches=request=>{const p=new URL(request.url).pathname;return p==='/api/muse/van-owner'||p==='/api/muse/tasks'||p==='/api/muse/owner-controls'||p==='/api/muse/interaction'||p.startsWith('/api/muse/interaction/');};
 async function rpc(operation,args){
   if(typeof signOwnerEnvelope!=='function'||typeof transport!=='function')throw Error('INTERACTION_NOT_CONNECTED');
   const time=now();const envelope={schema_version:1,principal:'MUSE_SITE_OWNER',authority_class:'OWNER_SITE_MUSE_TYPED',audience,site_origin:siteOrigin,subject:ownerSubject,policy_generation:policyGeneration,command_id:crypto.randomUUID(),operation,arguments:args,payload_hash:await digest({operation,arguments:args}),issued_at:new Date(time).toISOString(),expires_at:new Date(time+60000).toISOString(),nonce:crypto.randomUUID()};
   const signed=await signOwnerEnvelope(envelope);
   const result=await transport(signed);
   if(result?.ok===false)throw Error(result.error?.code||'INTERACTION_REFUSED');
   return result?.ok===true?result.result:result;
 }
 async function native(request){
   if(request.method!=='POST')return json({error:'METHOD_NOT_ALLOWED'},405);
   if(!gatewayPublicJwk||gatewayPublicJwk.d||typeof invokeExistingTask!=='function')return json({error:'GATEWAY_LINK_NOT_CONNECTED'},503);
   const value=await body(request),e=value.envelope;
   const fields=['schema_version','issuer','audience','subject','principal','operation','arguments','payload_hash','request_id','issued_at_ms','expires_at_ms'].sort();
   if(Object.keys(value).sort().join(',')!=='envelope,signature'||!e||Object.keys(e).sort().join(',')!==fields.join(','))throw Error('GATEWAY_ENVELOPE_INVALID');
   if(e.schema_version!==1||e.issuer!=='VAN_MUSE_GATEWAY'||e.audience!==audience||e.subject!==ownerSubject||!/^device:[A-Za-z0-9_.:-]{1,160}$/.test(e.principal)||!TASKS.has(e.operation)&&!OWNER_OPERATIONS.includes(e.operation))throw Error('GATEWAY_AUTHORITY_INVALID');
   const time=now();if(!Number.isSafeInteger(e.issued_at_ms)||!Number.isSafeInteger(e.expires_at_ms)||e.issued_at_ms>time+5000||e.expires_at_ms<=time||e.expires_at_ms-e.issued_at_ms>120000)throw Error('GATEWAY_ENVELOPE_EXPIRED');
   if(e.payload_hash!==await digest({operation:e.operation,arguments:e.arguments}))throw Error('GATEWAY_PAYLOAD_CHANGED');
   const key=await crypto.subtle.importKey('jwk',gatewayPublicJwk,{name:'Ed25519'},false,['verify']);
   if(!await crypto.subtle.verify('Ed25519',key,from64(value.signature),new TextEncoder().encode(canonical(e))))throw Error('GATEWAY_SIGNATURE_INVALID');
   // Trusted server context is created here after verification, never accepted from JSON.
   const context={ownerSubject,verifiedGatewayPrincipal:e.principal,proofReference:'sha256:'+await digest(e)};
   const result=OWNER_OPERATIONS.includes(e.operation)?await invokeOwnerControl(nativeOwnerControls,e.operation,e.arguments,context):await invokeExistingTask(e.operation,e.arguments,context);
   return json(result);
 }
 async function handle(request){
  try{
   const url=new URL(request.url);
   if(url.origin!==siteOrigin)return json({error:'SITE_ORIGIN_INVALID'},403);
   if(url.pathname==='/api/muse/van-owner')return await native(request);
   if(typeof requireOwner!=='function')return json({error:'OWNER_AUTH_NOT_CONNECTED'},503);
   const actor=await requireOwner(request);
   if(actor?.id!==ownerSubject||actor.auth_method!=='sites_identity')return json({error:'OWNER_REQUIRED'},403);
   if(request.method==='POST'&&request.headers.get('Origin')!==siteOrigin)return json({error:'SAME_ORIGIN_REQUIRED'},403);
   if(url.pathname==='/api/muse/owner-controls'&&request.method==='POST'){
     const value=await body(request);if(Object.keys(value).sort().join(',')!=='arguments,operation')throw Error('OWNER_CONTROL_ARGUMENTS_INVALID');
     return json(await invokeOwnerControl(nativeOwnerControls,value.operation,value.arguments,{ownerSubject,verifiedSiteActor:actor}));
   }
   if(url.pathname==='/api/muse/tasks'){
     if(typeof invokeExistingTask!=='function')throw Error('MUSE_TASKS_NOT_CONNECTED');
     const value=request.method==='GET'?{operation:'muse_get_overview',arguments:{}}:request.method==='POST'?await body(request):null;
     if(!value||Object.keys(value).sort().join(',')!=='arguments,operation'||!TASKS.has(value.operation))throw Error('MUSE_TASK_OPERATION_INVALID');
     return json(await invokeExistingTask(value.operation,value.arguments,{ownerSubject,verifiedSiteActor:actor}));
   }
   if(url.pathname==='/api/muse/interaction'&&request.method==='GET')return json(await rpc('muse_interaction_read',{}));
   if(url.pathname==='/api/muse/interaction'&&request.method==='POST')return json(await rpc('muse_interaction_action',await body(request,32768)),202);
   if(url.pathname.startsWith('/api/muse/interaction/commands/')&&request.method==='GET'){
     const id=url.pathname.slice('/api/muse/interaction/commands/'.length);if(!/^musecmd_[a-zA-Z0-9_-]{8,100}$/.test(id))return json({error:'COMMAND_ID_INVALID'},422);
     return json(await rpc('muse_interaction_receipt',{command_id:id}));
   }
   if(url.pathname==='/api/muse/interaction/events'&&request.method==='GET'){
     let cursor=Number(url.searchParams.get('after')||'0');if(!Number.isSafeInteger(cursor)||cursor<0)return json({error:'CURSOR_INVALID'},422);
     const encoder=new TextEncoder();let cancelled=false;
     const stream=new ReadableStream({async start(controller){
       const end=now()+55000;
       try{while(!cancelled&&!request.signal.aborted&&now()<end){
         const live=await requireOwner(request);if(live?.id!==ownerSubject||live.auth_method!=='sites_identity')break;
         const page=await rpc('muse_interaction_events',{after:cursor});
         if(!Array.isArray(page?.events))throw Error('EVENTS_INVALID');
         for(const event of page.events){if(!Number.isSafeInteger(event.seq)||event.seq<=cursor)throw Error('EVENT_CURSOR_INVALID');cursor=event.seq;controller.enqueue(encoder.encode(`id: ${cursor}\nevent: muse\ndata: ${JSON.stringify(event)}\n\n`));}
         controller.enqueue(encoder.encode(': heartbeat\n\n'));await new Promise(resolve=>setTimeout(resolve,2000));
       }}catch{if(!cancelled)controller.enqueue(encoder.encode('event: unavailable\ndata: {}\n\n'));}finally{if(!cancelled)controller.close();}
     },cancel(){cancelled=true;}});
     return new Response(stream,{headers:{'Content-Type':'text/event-stream','Cache-Control':'no-store','X-Accel-Buffering':'no'}});
   }
   return json({error:'ROUTE_NOT_FOUND'},404);
  }catch(error){return json({error:/^[A-Z0-9_]{1,100}$/.test(error.message)?error.message:'MUSE_REQUEST_REFUSED'},/NOT_CONNECTED/.test(error.message)?503:403);}
 }
 return {matches,handle};
}
