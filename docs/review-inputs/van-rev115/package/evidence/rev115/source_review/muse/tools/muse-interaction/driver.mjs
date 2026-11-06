/** Non-root, fixed-session stdio actuator. The supervisor owns transport credentials. */
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {MuseBrowserAdapter} from './browser-adapter.mjs';
import {assert,atomicJSON,readJSON,verifyCommand,CommandJournal,digest} from './protocol.mjs';

export async function handleRequest(request,adapter,journal,publicKey,producerId) {
  assert(request&&Object.getPrototypeOf(request)===Object.prototype,'REQUEST_SHAPE');
  assert(typeof request.id==='string'&&/^[A-Za-z0-9_.:-]{1,160}$/.test(request.id),'REQUEST_ID');
  if(request.operation==='observe') {
    assert(Object.keys(request).sort().join(',')==='bindings,id,operation','OBSERVATION_SHAPE');
    assert(Array.isArray(request.bindings)&&request.bindings.length<=100,'OBSERVATION_BOUND');
    return adapter.observe(request.bindings);
  }
  assert(request.operation==='execute'&&Object.keys(request).sort().join(',')==='command,id,operation','OPERATION_FORBIDDEN');
  const command=verifyCommand(request.command,publicKey,producerId);
  const previous=journal.begin(command);
  if(previous?.outcome)return previous.outcome;
  if(previous)return {command_id:command.command_id,command_digest:command.command_digest,state:'UNKNOWN',observed_at_ms:Date.now(),evidence_digest:digest({command_id:command.command_id,prior_attempt:true}),reason:'prior_attempt_requires_reconciliation'};
  let result;
  try {result=await adapter.execute(command);} catch(error) {
    // A transport failure may occur after the click was sent. Never turn that into retry permission.
    result={state:'UNKNOWN',evidence_digest:digest({command_id:command.command_id,uncertain:true}),reason:'interaction_outcome_unconfirmed'};
  }
  const outcome={command_id:command.command_id,command_digest:command.command_digest,...result,observed_at_ms:Date.now()};
  journal.finish(command,outcome);return outcome;
}

async function main() {
  assert(process.getuid()!==0,'ROOT_BROWSER_ACTUATION_REFUSED');
  assert(process.argv.length===2,'ARGV_FORBIDDEN');
  const configPath='/etc/dial-muse/interaction-browser.json';
  const stat=fs.lstatSync(configPath);assert(stat.isFile()&&!stat.isSymbolicLink()&&stat.uid===0&&!(stat.mode&0o022)&&stat.size<16384,'BROWSER_POLICY_PERMISSIONS');
  const config=JSON.parse(fs.readFileSync(configPath,'utf8'));
  assert(config.schema_version===1&&config.producer_id==='van-muse-browser'&&typeof config.public_key_pem==='string','BROWSER_POLICY_INVALID');
  const {chromium}=await import('playwright');
  const browser=await chromium.connectOverCDP('http://127.0.0.1:9225');
  const stateFile='/var/lib/dial-muse-interaction/browser/state.json';
  const state=readJSON(stateFile,{sessions:{},generation:0});
  const adapter=new MuseBrowserAdapter(browser,{producerId:config.producer_id,state,persist:s=>atomicJSON(stateFile,s)});
  const journal=new CommandJournal('/var/lib/dial-muse-interaction/browser/commands');
  let buffer='',chain=Promise.resolve(),pending=0;
  process.stdin.setEncoding('utf8');
  process.stdin.on('data',chunk=>{
    buffer+=chunk;
    if(Buffer.byteLength(buffer)>4*1024*1024||pending>32)process.exit(2);
    let newline;
    while((newline=buffer.indexOf('\n'))>=0){
      const line=buffer.slice(0,newline);buffer=buffer.slice(newline+1);pending++;
      chain=chain.then(async()=>{
        let request;
        try{request=JSON.parse(line);const result=await handleRequest(request,adapter,journal,config.public_key_pem,config.producer_id);process.stdout.write(JSON.stringify({id:request.id,ok:true,result})+'\n');}
        catch(error){process.stdout.write(JSON.stringify({id:request?.id||null,ok:false,error:/^[A-Z0-9_]{1,160}$/.test(error.message)?error.message:'INTERACTION_REFUSED'})+'\n');}
        finally{pending--;}
      });
    }
  });
  process.stdin.on('end',()=>chain.finally(()=>process.exit(0)));
}
if(process.argv[1]&&pathToFileURL(fs.realpathSync(process.argv[1])).href===import.meta.url)main().catch(()=>{process.stdout.write('{"ok":false,"error":"MUSE_BROWSER_UNAVAILABLE"}\n');process.exit(2);});
