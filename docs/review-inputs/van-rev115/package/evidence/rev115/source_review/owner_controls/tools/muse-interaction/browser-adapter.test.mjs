import test from 'node:test';
import assert from 'node:assert/strict';
import {MuseBrowserAdapter} from './browser-adapter.mjs';

class FakeButton {
  constructor(label){this.label=label;this.clicks=0;}
  async isVisible(){return true;}
  async isEnabled(){return true;}
  async getAttribute(){return null;}
  async innerText(){return this.label;}
  async click(){this.clicks++;}
}
class FakePrompt {
  constructor(text='Muse needs approval to perform this action',persistent=false){
    this.text=text;this.persistent=persistent;this.allow=new FakeButton('Allow once');this.deny=new FakeButton('Deny');
    this.connected=true;
  }
  async innerText(){return this.text;}
  async $$(selector){return selector.includes('checkbox')?(this.persistent?[{}]:[]):[this.allow,this.deny];}
  async evaluate(_fn,other){return other===undefined?!this.connected:this===other;}
}
const binding={task_id:'muse-job-123',project_id:'van',scope_binding_sha256:'a'.repeat(64)};
function create(now=1000){
  const state={sessions:{},generation:0};
  const adapter=new MuseBrowserAdapter({}, {now:()=>now,state,persist:()=>{}});
  return adapter;
}
test('the same provider DOM prompt retains its exact one-use identity', async()=>{
  const a=create();const p=new FakePrompt();
  const first=await a.describePrompt(p,binding,'session-1');
  const again=await a.describePrompt(p,binding,'session-1');
  assert.equal(first.id,again.id);assert.equal(first.expires_at_epoch_ms,again.expires_at_epoch_ms);
});
test('a visually identical replacement is a new approval, not a previous click',async()=>{
  const a=create();
  const first=await a.describePrompt(new FakePrompt(),binding,'session-1');
  const second=await a.describePrompt(new FakePrompt(),binding,'session-1');
  assert.notEqual(first.id,second.id);
});
test('remember and persistent controls are never eligible for Allow once',async()=>{
  const a=create();
  await assert.rejects(a.describePrompt(new FakePrompt('Muse needs approval. Always allow?'),binding,'session-1'),/PERSISTENT_PERMISSION_NOT_SUPPORTED/);
  await assert.rejects(a.describePrompt(new FakePrompt(undefined,true),binding,'session-1'),/PERSISTENT_PERMISSION_NOT_SUPPORTED/);
});
test('stale or incomplete observations refuse actuation before a DOM click',async()=>{
  const a=create();
  const p=new FakePrompt();const d=await a.describePrompt(p,binding,'session-1');
  a.pages.set('session-1',{page:{},binding,threadId:'thread-1'});
  const command={command_id:'cmd-12345678',expires_at_ms:5000,intent:{action:'DECIDE_APPROVAL',session_id:'session-1',thread_id:'thread-1',...binding,control_generation:a.generation,approval_id:d.id,expected_revision:1,action_fingerprint:d.action_fingerprint,choice:'ALLOW_ONCE'}};
  await assert.rejects(a.execute(command),/SOURCE_OBSERVATION_NOT_CURRENT/);
  assert.equal(p.allow.clicks,0);
});
test('an identical replacement cannot receive a click targeted at the prior modal',async()=>{
  const a=create();
  const old=new FakePrompt(),replacement=new FakePrompt();
  const d=await a.describePrompt(old,binding,'session-1');
  a.pages.set('session-1',{page:{},binding,threadId:'thread-1'});
  a.lastComplete=true;a.lastObservedAt=1000;
  a.boundPage=async()=>({});
  a.promptHandles=async()=>[replacement];
  const command={command_id:'cmd-12345678',expires_at_ms:5000,intent:{action:'DECIDE_APPROVAL',session_id:'session-1',thread_id:'thread-1',...binding,control_generation:a.generation,approval_id:d.id,expected_revision:1,action_fingerprint:d.action_fingerprint,choice:'ALLOW_ONCE'}};
  await assert.rejects(a.execute(command),/APPROVAL_DOM_REPLACED/);
  assert.equal(old.allow.clicks,0);assert.equal(replacement.allow.clicks,0);
});
test('a disappearing permission modal is not evidence that Allow succeeded',async()=>{
  const a=create();
  const p=new FakePrompt(),d=await a.describePrompt(p,binding,'session-1');
  a.pages.set('session-1',{page:{},binding,threadId:'thread-1'});
  a.lastComplete=true;a.lastObservedAt=1000;
  a.boundPage=async()=>({});
  a.promptHandles=async()=>[p];
  const command={command_id:'cmd-12345678',expires_at_ms:5000,intent:{action:'DECIDE_APPROVAL',session_id:'session-1',thread_id:'thread-1',...binding,control_generation:a.generation,approval_id:d.id,expected_revision:1,action_fingerprint:d.action_fingerprint,choice:'ALLOW_ONCE'}};
  const result=await a.execute(command);
  assert.equal(p.allow.clicks,1);assert.equal(result.state,'UNKNOWN');
  assert.equal(result.reason,'provider_control_disappeared_but_choice_outcome_not_verified');
});
