import test from 'node:test';
import assert from 'node:assert/strict';
import {CinematicStudioClient} from './cinematic-studio-client.mjs';
import {createMuseBff} from './bff.mjs';
test('Studio reuses existing Site owner identity and same-origin authentication before any native call',async()=>{
 const calls=[];const make=actor=>createMuseBff({siteOrigin:'https://fixture.test',ownerSubject:'owner',requireOwner:async()=>actor,nativeStudio:{call:async(request,context)=>{calls.push({request,context});return{state:'OBSERVED'};}}});
 const request=origin=>new Request('https://fixture.test/api/muse/studio',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:JSON.stringify({operation:'contexts',arguments:{}})});
 assert.equal((await make({id:'other',auth_method:'sites_identity'}).handle(request('https://fixture.test'))).status,403);assert.equal((await make({id:'owner',auth_method:'sites_identity'}).handle(request('https://hostile.test'))).status,403);assert.equal(calls.length,0);assert.equal((await make({id:'owner',auth_method:'sites_identity'}).handle(request('https://fixture.test'))).status,200);assert.equal(calls[0].context.verifiedSiteActor.id,'owner');assert.equal(calls[0].request.operation,'contexts');
});
test('lost Studio readback retains exact request key; source revision changes create a distinct request',async()=>{
 const sent=[];let fail=true;const client=new CinematicStudioClient({fetchImpl:async(_,request)=>{sent.push(JSON.parse(request.body));if(fail)throw Error('LOST');return new Response(JSON.stringify({state:'COMPLETED'}));}});const args={scope:{project_id:'source',round_id:'round'},expected_revision:1,source_hash:'a'.repeat(64)};
 await assert.rejects(client.call('undo',args),/LOST/);fail=false;await client.call('undo',args);assert.equal(sent[0].arguments.request_key,sent[1].arguments.request_key);await client.call('undo',{...args,expected_revision:2});assert.notEqual(sent[1].arguments.request_key,sent[2].arguments.request_key);
});
