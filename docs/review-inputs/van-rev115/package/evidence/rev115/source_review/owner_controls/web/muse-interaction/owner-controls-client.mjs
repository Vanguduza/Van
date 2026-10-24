import {validateOwnerCall} from './owner-controls.mjs';
/** Pending commands survive reload, but reconnection only reads original state.
 * Per-tab session storage contains scoped intent, never owner credentials. */
export class OwnerControlsClient {
 constructor({fetcher=fetch,storage=globalThis.sessionStorage,base='/api/muse/owner-controls'}={}) {this.fetcher=fetcher;this.storage=storage;this.base=base;this.pending=new Map();try{for(const row of JSON.parse(storage?.getItem('muse-owner-pending')||'[]'))this.pending.set(row.input?.request_id,row);}catch{/* A fresh native read is still required. */}}
 retain(){try{this.storage?.setItem('muse-owner-pending',JSON.stringify([...this.pending.values()]));}catch{/* Runtime memory retains the original identity. */}}
 async call(operation,args) {validateOwnerCall(operation,args);const r=await this.fetcher(this.base,{method:'POST',credentials:'same-origin',redirect:'error',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({operation,arguments:args})});const v=await r.json();if(!r.ok||v?.ok===false)throw Error(v.error?.code||v.error||'OWNER_CONTROLS_UNAVAILABLE');return v?.ok===true?v.result:v;}
 read(operation,context_ref,input={}){return this.call(operation,{context_ref,input});}
 async control(context_ref,row,action){
  const pending=[...this.pending.values()].find(p=>p.context_ref===context_ref&&p.input.operation_id===row.operation_id);
  if(pending)throw Error('CHECK_ORIGINAL_OPERATION_BEFORE_ANOTHER_ACTION');
  const request={context_ref,input:{operation_id:row.operation_id,action,observation_digest:row.observation_digest,request_id:'owner-'+crypto.randomUUID()}};
  this.pending.set(request.input.request_id,request);this.retain();
  // Deliberately retain intent even when the transport throws or returns only acceptance.
  return this.call('dial_owner_control',request);
 }
 async reconcile(request_id){const request=this.pending.get(request_id);if(!request)throw Error('ORIGINAL_OPERATION_REQUIRED');const row=await this.read('dial_owner_status',request.context_ref,{operation_id:request.input.operation_id});if(['COMPLETED','CANCELLED','FAILED','REFUSED','PAUSED'].includes(row.state)){this.pending.delete(request_id);this.retain();}return row;}
}

export class MuseTasksClient {
 constructor({fetcher=fetch}={}){this.fetcher=fetcher;this.pending=new Map();}
 async call(operation,args={}){const r=await this.fetcher('/api/muse/tasks',{method:'POST',credentials:'same-origin',redirect:'error',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({operation,arguments:args})});const v=await r.json();if(!r.ok||v?.ok===false)throw Error(v.error?.code||v.error||'MUSE_TASK_UNAVAILABLE');return v?.ok===true?v.result:v;}
 async write(operation,args){const key=args.idempotency_key;if(typeof key!=='string')throw Error('ORIGINAL_REQUEST_KEY_REQUIRED');const prior=this.pending.get(key);if(prior&&JSON.stringify(prior)!==JSON.stringify({operation,args}))throw Error('ORIGINAL_REQUEST_CHANGED');this.pending.set(key,{operation,args:structuredClone(args)});return this.call(operation,args);}
}
