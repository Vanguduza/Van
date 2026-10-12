/** Main-frame semantic interaction only. No cookies, localStorage, arbitrary JS from callers,
 * screen coordinates, navigation, browser/profile creation, or Always Allow operation. */
import crypto from 'node:crypto';
import {assert,digest,textDigest} from './protocol.mjs';

const ORIGIN='https://muse.ai';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const normalized=text=>String(text).replace(/\s+/g,' ').trim();
const userSelector='.hatch-chat-groupable-bubble.bg-chat-user-bubble,[data-message-author-role="user"]';
const messageSelector='div.hatch-chat-groupable-bubble,[data-message-author-role]';

export class MuseBrowserAdapter {
  constructor(browser,{producerId='van-muse-browser',state={sessions:{}},persist=()=>{},now=()=>Date.now()}={}) {
    this.browser=browser;this.producerId=producerId;this.state=state;this.persist=persist;this.now=now;
    this.generation=Math.max(this.now(),(state.generation||0)+1);state.generation=this.generation;this.persist(state);
    this.refs=new Map();this.pages=new Map();this.promptCounter=0;
    this.lastComplete=false;this.lastObservedAt=0;
  }

  async boundPage(binding) {
    const u=new URL(binding.thread_url);
    assert(u.origin===ORIGIN&&/^\/thread\/[a-zA-Z0-9-]{16,80}$/.test(u.pathname)&&!u.search&&!u.hash,'UNSUPPORTED_THREAD');
    const matches=this.browser.contexts().flatMap(c=>c.pages()).filter(p=>p.url()===u.href);
    assert(matches.length===1,'THREAD_NOT_UNIQUE_OR_GONE');
    const page=matches[0];
    const users=await page.locator(userSelector).allTextContents();
    const prefix='DIAL_MUSE_JOB_BEGIN:'+binding.task_id+':';
    const boundaries=users.flatMap(text=>(text.match(/DIAL_MUSE_JOB_BEGIN:[A-Za-z0-9_.:-]+/g)||[])).filter(s=>s.startsWith(prefix)&&textDigest(s)===binding.job_boundary_sha256);
    assert(boundaries.length===1,'CURRENT_JOB_BOUNDARY_UNQUALIFIED');
    const cdp=await page.context().newCDPSession(page);
    let target;try{target=(await cdp.send('Target.getTargetInfo')).targetInfo.targetId;}finally{await cdp.detach();}
    const sessionId='musesession_'+textDigest(binding.task_id+':'+target).slice(0,40);
    return {page,sessionId,threadId:u.pathname.split('/')[2],boundary:boundaries[0]};
  }

  async promptHandles(page) {
    const handles=[];
    for(const button of await page.getByRole('button',{name:/^(Allow|Allow once|Deny)$/i}).elementHandles()) {
      if(!await button.isVisible()||!await button.isEnabled())continue;
      const candidate=await button.evaluateHandle(e=>{
        if(e.closest('textarea,[contenteditable="true"],.bg-chat-user-bubble,[data-message-author-role="user"]'))return null;
        for(let p=e.parentElement;p&&p!==document.body;p=p.parentElement){
          const text=(p.innerText||'').replace(/\s+/g,' ').trim();
          if(text.length>16000)return null;
          const bs=[...p.querySelectorAll('button,[role="button"]')].filter(b=>b.getClientRects().length);
          const names=bs.map(b=>(b.getAttribute('aria-label')||b.innerText||'').trim());
          if(names.filter(x=>/^(Allow|Allow once)$/i.test(x)).length===1&&names.filter(x=>/^Deny$/i.test(x)).length===1&&/needs approval|allow .{1,120} to perform this action|share information with/i.test(text))return p;
        }
        return null;
      });
      const el=candidate.asElement();if(!el)continue;
      let duplicate=false;for(const prior of handles){if(await prior.evaluate((a,b)=>a===b,el)){duplicate=true;break;}}
      if(!duplicate)handles.push(el);
    }
    return handles;
  }

  async describePrompt(handle,binding,sessionId) {
    const text=normalized(await handle.innerText());assert(text.length>0&&text.length<=16000,'PROMPT_TOO_LARGE_OR_EMPTY');
    const buttons=await handle.$$('button,[role="button"]');
    const choices={};
    for(const b of buttons){
      if(!await b.isVisible()||!await b.isEnabled())continue;
      const name=normalized((await b.getAttribute('aria-label'))||await b.innerText());
      if(/^(Allow|Allow once)$/i.test(name))choices.ALLOW_ONCE=b;
      if(/^Deny$/i.test(name))choices.DENY=b;
    }
    assert(choices.ALLOW_ONCE&&choices.DENY,'PROMPT_CHOICES_CHANGED');
    // An embedded checked toggle could turn a one-time click into a permanent grant.
    // If the provider surfaces a remember/always-allow option, do not guess its state.
    const persistentControls=await handle.$$('input[type="checkbox"],[role="checkbox"],[role="switch"],[aria-checked]');
    assert(!persistentControls.length&&!/\b(always allow|always approve|remember (?:this|my)|don.t ask again|persist(?:ent)? permission)\b/i.test(text),'PERSISTENT_PERMISSION_NOT_SUPPORTED');
    const fingerprint=digest({description:text,choices:Object.keys(choices).sort(),task_id:binding.task_id,scope_binding_sha256:binding.scope_binding_sha256});
    let id=null,entry=null;
    for(const [candidate,prior] of this.refs){
      if(prior.sessionId!==sessionId||prior.fingerprint!==fingerprint)continue;
      try{
        if(await prior.handle.evaluate((existing,current)=>existing===current,handle)){
          id=candidate;entry=prior;break;
        }
      }catch{/* Detached/replaced DOM references can never be reused. */}
    }
    if(!entry){
      // DOM node identity is a separate fence: visually identical provider prompts are
      // not one owner approval. A replacement gets a new ID and cannot inherit a click.
      id='museapproval_'+textDigest(sessionId+':'+fingerprint+':'+this.generation+':'+(++this.promptCounter)).slice(0,40);
      entry={handle,choices,fingerprint,sessionId,description:text,expires:this.now()+15*60000};
      this.refs.set(id,entry);
    }
    return {id,revision:1,action_fingerprint:fingerprint,element_ref:id,description:text,allowed_actions:Object.keys(choices).sort(),action_class:'UNCLASSIFIED',expires_at_epoch_ms:entry.expires};
  }

  async observe(bindings) {
    const sessions=[];let complete=true;const seenPrompts=new Set();const seenSessions=new Set();
    for(const b of bindings){
      try{
        assert(/^[a-f0-9]{64}$/.test(b.scope_binding_sha256)&&/^[a-f0-9]{64}$/.test(b.job_boundary_sha256),'BINDING_INVALID');
        assert(b.current_job_only===true,'CAPTURE_NOT_QUALIFIED');
        const {page,sessionId,threadId,boundary}=await this.boundPage(b);
        const raw=await page.locator(messageSelector).evaluateAll(xs=>xs.map(e=>({text:e.innerText||'',user:e.classList.contains('bg-chat-user-bubble')||e.getAttribute('data-message-author-role')==='user',assistant:e.className.includes('--hatch-agent-bubble-bg')||e.getAttribute('data-message-author-role')==='assistant'})));
        const first=raw.findIndex(m=>m.user&&m.text.includes(boundary));assert(first>=0,'JOB_BOUNDARY_GONE');
        const messages=raw.slice(first+1).filter(m=>m.user||m.assistant).map((m,i)=>({id:'msg_'+textDigest(sessionId+':'+i+':'+(m.user?'user':'assistant')).slice(0,40),role:m.user?'user':'assistant',text:m.text.slice(0,32000),streaming:false})).slice(-200);
        const approvals=[];for(const h of await this.promptHandles(page)){const a=await this.describePrompt(h,b,sessionId);approvals.push(a);seenPrompts.add(a.id);}
        const textareas=page.locator('textarea[placeholder="Message"]:visible');
        const canSend=await textareas.count()===1&&!(await textareas.inputValue())&&await page.getByRole('button',{name:/stop generating|cancel generation|^Stop$/i}).count()===0;
        const data={session_id:sessionId,thread_id:threadId,task_id:b.task_id,project_id:b.project_id??null,scope_binding_sha256:b.scope_binding_sha256,control_generation:this.generation,title:String(b.title||'Muse task').slice(0,240),state:String(b.state||'OBSERVED').slice(0,64),current_job_only:true,can_send:canSend,messages,approvals};
        const hashed=digest(data),old=this.state.sessions[sessionId];
        const revision=old?.digest===hashed?old.revision:(old?.revision||0)+1;
        this.state.sessions[sessionId]={digest:hashed,revision};this.pages.set(sessionId,{page,binding:b,threadId,data:{...data,revision}});
        seenSessions.add(sessionId);sessions.push({...data,revision});
      }catch(error){complete=false;}
    }
    this.lastComplete=complete;this.lastObservedAt=this.now();
    if(complete){
      // Current observations, not historical handles, determine what may be clicked.
      for(const id of this.refs.keys())if(!seenPrompts.has(id))this.refs.delete(id);
      for(const id of this.pages.keys())if(!seenSessions.has(id))this.pages.delete(id);
    }
    this.persist(this.state);
    return {schema_version:1,producer_id:this.producerId,observed_at_ms:this.lastObservedAt,health:complete?'GREEN':'DEGRADED',watchdog:complete?'GREEN':'UNOBSERVED',complete,sessions};
  }

  async execute(command) {
    const a=command.intent,entry=this.pages.get(a.session_id);
    assert(this.lastComplete && this.lastObservedAt>0 &&
      this.now()>=this.lastObservedAt &&
      this.now()-this.lastObservedAt<=90000,'SOURCE_OBSERVATION_NOT_CURRENT');
    assert(entry,'SESSION_UNOBSERVED');const b=entry.binding;
    assert(command.expires_at_ms>this.now(),'COMMAND_EXPIRED');
    for(const [key,value] of Object.entries({thread_id:entry.threadId,task_id:b.task_id,project_id:b.project_id??null,scope_binding_sha256:b.scope_binding_sha256,control_generation:this.generation}))assert((a[key]??null)===value,'ACTION_BINDING_CHANGED');
    await this.boundPage(b); // source/thread boundary is re-read at the actuation boundary
    if(a.action==='DECIDE_APPROVAL') {
      const ref=this.refs.get(a.approval_id);assert(ref&&ref.expires>this.now()&&a.expected_revision===1&&ref.fingerprint===a.action_fingerprint,'APPROVAL_CHANGED');
      assert(['ALLOW_ONCE','DENY'].includes(a.choice),'CHOICE_FORBIDDEN');
      // An old ElementHandle may belong to a removed modal while an identical
      // replacement sits in the same location. Verify DOM identity immediately before.
      let current=false;
      for(const active of await this.promptHandles(entry.page)){
        try{if(await ref.handle.evaluate((existing,candidate)=>existing===candidate,active)){current=true;break;}}
        catch{/* A detached old control is not approved. */}
      }
      assert(current,'APPROVAL_DOM_REPLACED');
      const observed=await this.describePrompt(ref.handle,b,a.session_id);
      assert(observed.id===a.approval_id&&observed.action_fingerprint===a.action_fingerprint,'PROMPT_CHANGED');
      const button=ref.choices[a.choice];assert(button&&await button.isVisible()&&await button.isEnabled(),'CONTROL_UNAVAILABLE');
      await button.click({timeout:5000}); // no force, coordinates or arbitrary selector
      let absent=0;
      for(let i=0;i<20;i++){
        await pause(250);
        const still=await ref.handle.evaluate(e=>e.isConnected&&e.getClientRects().length>0).catch(()=>false);
        absent=still?0:absent+1;
        if(absent>=2)return {state:'UNKNOWN',
          evidence_digest:digest({command_id:command.command_id,action_fingerprint:a.action_fingerprint,control_no_longer_present:true}),
          reason:'provider_control_disappeared_but_choice_outcome_not_verified'};
      }
      return {state:'UNKNOWN',evidence_digest:digest({command_id:command.command_id,prompt_still_present:true}),reason:'provider_control_outcome_unconfirmed'};
    }
    assert(a.action==='SEND_MESSAGE'&&a.expected_revision===entry.data.revision,'CONVERSATION_CHANGED');
    const composer=entry.page.locator('textarea[placeholder="Message"]:visible');
    assert(await composer.count()===1&&await composer.inputValue()==='','COMPOSER_BUSY_OR_UNKNOWN');
    assert(typeof a.text==='string'&&a.text.trim()&&a.text.length<=4000,'MESSAGE_INVALID');
    const before=await entry.page.locator(userSelector).count();
    await composer.fill(a.text);
    const send=entry.page.getByRole('button',{name:/^Send$/i});
    assert(await send.count()===1&&await send.isEnabled(),'SEND_BUTTON_UNAVAILABLE');
    await send.click({timeout:5000});
    for(let i=0;i<20;i++){
      await pause(250);const texts=await entry.page.locator(userSelector).allTextContents();
      if(texts.length>before&&normalized(texts.at(-1))===normalized(a.text))return {state:'CONFIRMED',evidence_digest:digest({command_id:command.command_id,message:normalized(a.text),user_bubble_observed:true}),reason:'provider_message_observed'};
    }
    return {state:'UNKNOWN',evidence_digest:digest({command_id:command.command_id,message_unconfirmed:true}),reason:'provider_message_outcome_unconfirmed'};
  }
}
