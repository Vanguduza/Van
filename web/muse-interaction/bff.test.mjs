import { webcrypto } from "node:crypto";
globalThis.crypto ??= webcrypto;
import test from 'node:test';
import assert from 'node:assert/strict';
import {createMuseBff,canonical,digest} from './bff.mjs';
import {MuseClient,sourceFresh,mayDecideApproval} from './client.mjs';
const site='https://fixture.chatgpt.site',subject='user:fixture',audience='fixture-site';
const pair=await crypto.subtle.generateKey('Ed25519',true,['sign','verify']);
const publicJwk=await crypto.subtle.exportKey('jwk',pair.publicKey);
const encode=b=>Buffer.from(b).toString('base64url');
const fixture=extra=>createMuseBff({siteOrigin:site,ownerSubject:subject,audience,requireOwner:async()=>({id:subject,auth_method:'sites_identity'}),signOwnerEnvelope:async envelope=>({envelope,signature:'fixture-only'}),transport:async signed=>({ok:true,result:{operation:signed.envelope.operation,arguments:signed.envelope.arguments}}),gatewayPublicJwk:publicJwk,invokeExistingTask:async(operation,args,context)=>({ok:true,result:{operation,args,context}}),now:()=>100000,...extra});
async function request(changes={}){const e={schema_version:1,issuer:'VAN_MUSE_GATEWAY',audience,subject,principal:'device:fixture',operation:'muse_get_overview',arguments:{},request_id:'fixture-request',issued_at_ms:100000,expires_at_ms:160000,...changes};e.payload_hash=await digest({operation:e.operation,arguments:e.arguments});const signature=encode(await crypto.subtle.sign('Ed25519',pair.privateKey,new TextEncoder().encode(canonical(e))));return {envelope:e,signature};}
test('authenticated Site read uses its existing owner signer',async()=>{const r=await fixture().handle(new Request(site+'/api/muse/interaction'));assert.equal(r.status,200);assert.equal((await r.json()).operation,'muse_interaction_read');});
test('a service label is not an owner session',async()=>{const r=await fixture({requireOwner:async()=>({id:subject,auth_method:'service_key'})}).handle(new Request(site+'/api/muse/interaction'));assert.equal(r.status,403);});
test('cross-origin writes are refused',async()=>{const r=await fixture().handle(new Request(site+'/api/muse/interaction',{method:'POST',body:'{}',headers:{Origin:'https://other.invalid'}}));assert.equal(r.status,403);});
test('native task bridge requires exact signed gateway owner intent',async()=>{const r=await fixture().handle(new Request(site+'/api/muse/van-owner',{method:'POST',body:JSON.stringify(await request())}));assert.equal(r.status,200);const v=await r.json();assert.equal(v.result.context.verifiedGatewayPrincipal,'device:fixture');});
test('changed gateway task arguments cannot be forwarded',async()=>{const body=await request();body.envelope.arguments={job_id:'another'};const r=await fixture().handle(new Request(site+'/api/muse/van-owner',{method:'POST',body:JSON.stringify(body)}));assert.equal(r.status,403);});
test('unrelated service operations are not admitted',async()=>{const r=await fixture().handle(new Request(site+'/api/muse/van-owner',{method:'POST',body:JSON.stringify(await request({operation:'run_shell'}))}));assert.equal(r.status,403);});
test('expired native attestation is refused',async()=>{const r=await fixture().handle(new Request(site+'/api/muse/van-owner',{method:'POST',body:JSON.stringify(await request({expires_at_ms:99999}))}));assert.equal(r.status,403);});
test('client retry retains its exact intent',async()=>{const bodies=[];const client=new MuseClient({fetcher:async(url,opt)=>{bodies.push(opt.body);if(bodies.length===1)throw Error('fixture lost reply');return new Response(JSON.stringify({command_id:'musecmd_fixture',state:'QUEUED'}));}});const action={idempotency_key:'same-request',action:'SEND_MESSAGE',text:'fixture'};await assert.rejects(client.send(action));await client.send(action);assert.equal(bodies[0],bodies[1]);});
test('stale observation is never shown as live',()=>{assert.equal(sourceFresh({relay:{last_source_at_ms:1,state:'live'},health:{state:'GREEN'},watchdog:{state:'GREEN'}},90002),false);});

test('health unobserved never unlocks Site controls even when relay is fresh',()=>{
 const snapshot={relay:{last_source_at_ms:1000,state:'live'},health:{state:'UNOBSERVED'},watchdog:{state:'GREEN'},control_admitted:true};
 assert.equal(sourceFresh(snapshot,1200),false);
 assert.equal(sourceFresh({...snapshot,health:{state:'GREEN'},watchdog:{state:'DEGRADED'}},1200),false);
 assert.equal(sourceFresh({...snapshot,health:{state:'GREEN'}},1200),true);
});
test('Site approval choices require exact provider prompt identity and scope',()=>{
 const p={id:'approval-1',session_id:'session-1',thread_id:'thread-1',task_id:'task-1',scope_binding_sha256:'a'.repeat(64),action_fingerprint:'f'.repeat(64),control_generation:2,revision:1,expires_at_epoch_ms:5000,action_class:'A2',description:'Read a project file',state:'AWAITING_OWNER',allowed_actions:['ALLOW_ONCE','DENY']};
 assert.equal(mayDecideApproval(p,'ALLOW_ONCE',true,1000),true);
 assert.equal(mayDecideApproval({...p,scope_binding_sha256:'bad'},'ALLOW_ONCE',true,1000),false);
 assert.equal(mayDecideApproval({...p,control_generation:0},'DENY',true,1000),false);
 assert.equal(mayDecideApproval({...p,revision:0},'ALLOW_ONCE',true,1000),false);
 assert.equal(mayDecideApproval({...p,action_fingerprint:'changed'},'DENY',true,1000),false);
 assert.equal(mayDecideApproval({...p,action_class:'A5'},'ALLOW_ONCE',true,1000),false);
 assert.equal(mayDecideApproval({...p,action_class:'A5'},'DENY',true,1000),true);
 assert.equal(mayDecideApproval(p,'ALLOW_ONCE',false,1000),false);
 assert.equal(mayDecideApproval(p,'ALLOW_ONCE',true,5001),false);
});
