const READS=new Set(['contexts','snapshot','search','operation-status']);
export class CinematicStudioClient{
 constructor({fetchImpl=globalThis.fetch}={}){this.fetchImpl=(...args)=>Reflect.apply(fetchImpl,globalThis,args);this.pending=new Map();}
 async call(operation,args={}){
  const key=JSON.stringify({operation,arguments:args});let request=this.pending.get(key);
  if(!request){request={operation,arguments:{...args,...(!READS.has(operation)?{request_key:crypto.randomUUID()}:{})}};if(!READS.has(operation))this.pending.set(key,request);}
  const response=await this.fetchImpl('/api/muse/studio',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(request)});
  const result=await response.json();if(!response.ok)throw Error(result.error||'Studio request not confirmed.');
  if(!['OUTCOME_UNKNOWN','RUNNING','QUEUED','WAITING','DISPATCHED'].includes(result.state))this.pending.delete(key);
  return result;
 }
}
