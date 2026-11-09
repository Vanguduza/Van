// Bounded initial-request admission. Queuing is not execution or a retry.
// Slots stay owned until the original handler settles, even after disconnect.
export class Admission {
  constructor({global=4,perSubject=2,pending=24,pendingPerSubject=12,waitMs=2500}={}){
    for(const value of [global,perSubject,pending,pendingPerSubject,waitMs])if(!Number.isSafeInteger(value)||value<1)throw Error('INVALID_LIMIT');
    this.limits={global,perSubject,pending,pendingPerSubject,waitMs};
    this.active=0;this.bySubject=new Map();this.queue=[];
  }
  allowed(subject){return this.active<this.limits.global&&(this.bySubject.get(subject)??0)<this.limits.perSubject;}
  start(subject){
    this.active++;this.bySubject.set(subject,(this.bySubject.get(subject)??0)+1);let released=false;
    return ()=>{if(released)return;released=true;this.active--;const left=(this.bySubject.get(subject)??1)-1;if(left)this.bySubject.set(subject,left);else this.bySubject.delete(subject);this.pump();};
  }
  pump(){
    while(this.active<this.limits.global){
      const i=this.queue.findIndex(x=>this.allowed(x.subject));if(i<0)return;
      const item=this.queue.splice(i,1)[0];clearTimeout(item.timer);item.signal?.removeEventListener('abort',item.cancel);
      if(item.signal?.aborted){item.reject(Error('REQUEST_ABORTED'));continue;}
      item.resolve(this.start(item.subject));
    }
  }
  acquire(subject,signal){
    if(typeof subject!=='string'||!subject||subject.length>160)return Promise.reject(Error('INVALID_SUBJECT'));
    if(signal?.aborted)return Promise.reject(Error('REQUEST_ABORTED'));
    if(this.allowed(subject))return Promise.resolve(this.start(subject));
    if(this.queue.length>=this.limits.pending||this.queue.filter(x=>x.subject===subject).length>=this.limits.pendingPerSubject)return Promise.reject(Error('CAPACITY_BUSY'));
    return new Promise((resolve,reject)=>{
      const item={subject,signal,resolve,reject,timer:null,cancel:null};
      const remove=message=>{const i=this.queue.indexOf(item);if(i<0)return;this.queue.splice(i,1);clearTimeout(item.timer);signal?.removeEventListener('abort',item.cancel);reject(Error(message));};
      item.cancel=()=>remove('REQUEST_ABORTED');item.timer=setTimeout(()=>remove('CAPACITY_BUSY'),this.limits.waitMs);
      this.queue.push(item);signal?.addEventListener('abort',item.cancel,{once:true});
    });
  }
}
