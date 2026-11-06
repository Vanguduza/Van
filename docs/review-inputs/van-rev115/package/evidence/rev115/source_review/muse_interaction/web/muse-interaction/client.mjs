/** Same-origin browser client. Approvals are never queued for automatic offline replay. */
export async function sha(value){const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(value)));return [...new Uint8Array(b)].map(v=>v.toString(16).padStart(2,'0')).join('');}
export class MuseClient {
 constructor({base='/api/muse/interaction',fetcher=fetch}={}){this.base=base;this.fetcher=fetcher;this.pending=new Map();}
 async call(path='',options={}){const response=await this.fetcher(this.base+path,{credentials:'same-origin',redirect:'error',...options,headers:{'Accept':'application/json',...(options.body?{'Content-Type':'application/json'}:{}),...options.headers}});const value=await response.json();if(!response.ok||value?.ok===false)throw Error(value.error?.code||value.error||'MUSE_UNAVAILABLE');return value?.ok===true?value.result:value;}
 overview(){return this.call();}
 async decide(prompt,choice){
  const intent=this.binding(prompt);Object.assign(intent,{action:'DECIDE_APPROVAL',approval_id:prompt.id,expected_revision:prompt.revision,action_fingerprint:prompt.action_fingerprint,choice});
  intent.idempotency_key='approval:'+await sha(intent);return this.send(intent);
 }
 async message(thread,text){const intent=this.binding(thread);Object.assign(intent,{action:'SEND_MESSAGE',expected_revision:thread.revision,text});intent.idempotency_key='message:'+await sha(intent);return this.send(intent);}
 binding(value){const b={};for(const k of ['session_id','thread_id','task_id','project_id','scope_binding_sha256','control_generation'])b[k]=value[k]??null;return b;}
 async send(intent){const key=intent.idempotency_key;const prior=this.pending.get(key);if(prior?.command_id)return prior;
  // Keep the identical intent through transport errors. A retry is a retry, not a new command.
  this.pending.set(key,{intent,state:'DELIVERY_UNCONFIRMED'});
  const receipt=await this.call('',{method:'POST',body:JSON.stringify(intent)});this.pending.set(key,{...receipt,intent});return receipt;
 }
 async receipts(){for(const [key,row] of this.pending){if(!row.command_id)continue;const receipt=await this.call('/commands/'+encodeURIComponent(row.command_id));this.pending.set(key,{...receipt,intent:row.intent});}return [...this.pending.values()];}
}
export function sourceFresh(value,now=Date.now()){const t=value?.relay?.last_source_at_ms;return Number.isSafeInteger(t)&&now>=t&&now-t<=90000&&value.relay.state==='live'&&value.health?.state==='GREEN'&&value.watchdog?.state==='GREEN';}

/** Presentation fence only; the authenticated Muse broker revalidates everything. */
export function mayDecideApproval(prompt,choice,fresh,now=Date.now()) {
 if(!fresh||!prompt||!['ALLOW_ONCE','DENY'].includes(choice))return false;
 if(prompt.state!=='AWAITING_OWNER'||!Number.isSafeInteger(prompt.expires_at_epoch_ms)||prompt.expires_at_epoch_ms<=now)return false;
 if(!Number.isSafeInteger(prompt.revision)||prompt.revision<1||!Number.isSafeInteger(prompt.control_generation)||prompt.control_generation<1)return false;
 if(!/^[a-fA-F0-9]{64}$/.test(prompt.action_fingerprint||'')||!/^[a-fA-F0-9]{64}$/.test(prompt.scope_binding_sha256||''))return false;
 for(const k of ['id','session_id','thread_id','task_id'])if(typeof prompt[k]!=='string'||!prompt[k].trim())return false;
 if(!Array.isArray(prompt.allowed_actions)||!prompt.allowed_actions.includes(choice))return false;
 if(choice==='ALLOW_ONCE'&&(prompt.action_class==='A5'||typeof prompt.description!=='string'||!prompt.description.trim()))return false;
 return true;
}
