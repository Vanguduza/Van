import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export function canonical(value) {
  if(value===null || typeof value==='boolean' || typeof value==='string')return JSON.stringify(value);
  if(typeof value==='number' && Number.isSafeInteger(value))return String(value);
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value&&Object.getPrototypeOf(value)===Object.prototype)return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  throw new Error('NON_CANONICAL_VALUE');
}
export const digest=value=>crypto.createHash('sha256').update(canonical(value)).digest('hex');
export const textDigest=value=>crypto.createHash('sha256').update(value).digest('hex');
export function assert(condition,code){if(!condition)throw new Error(code);}
export function atomicJSON(file,value) {
  const dir=path.dirname(file);fs.mkdirSync(dir,{recursive:true,mode:0o700});
  const tmp=file+'.'+crypto.randomUUID()+'.tmp';
  const fd=fs.openSync(tmp,'wx',0o600);
  try{fs.writeFileSync(fd,canonical(value)+'\n');fs.fsyncSync(fd);}finally{fs.closeSync(fd);}
  fs.renameSync(tmp,file);const d=fs.openSync(dir,'r');try{fs.fsyncSync(d);}finally{fs.closeSync(d);}
}
export function readJSON(file,fallback=null) {
  try{const s=fs.lstatSync(file);assert(s.isFile()&&!s.isSymbolicLink()&&!(s.mode&0o077)&&s.uid===process.getuid(),'STATE_PERMISSIONS');assert(s.size<4*1024*1024,'STATE_TOO_LARGE');return JSON.parse(fs.readFileSync(file,'utf8'));}
  catch(e){if(e.code==='ENOENT')return fallback;throw e;}
}
export function verifyCommand(wrapper,publicKey,producerId,now=Date.now()) {
  assert(wrapper&&Object.keys(wrapper).sort().join(',')==='envelope,signature','COMMAND_SHAPE');
  const e=wrapper.envelope;
  assert(e?.schema_version===1&&e.producer_id===producerId,'COMMAND_AUDIENCE');
  assert(/^[A-Za-z0-9_.:-]{8,160}$/.test(e.command_id||''),'COMMAND_ID');
  assert(Number.isSafeInteger(e.issued_at_ms)&&Number.isSafeInteger(e.expires_at_ms)&&e.issued_at_ms<=now+5000&&e.expires_at_ms>now&&e.expires_at_ms-e.issued_at_ms<=120000,'COMMAND_EXPIRED');
  assert(e.command_digest===digest(e.intent),'COMMAND_DIGEST');
  assert(['SEND_MESSAGE','DECIDE_APPROVAL'].includes(e.intent?.action),'COMMAND_OPERATION');
  assert(typeof e.principal==='string'&&/^(device|site):.{1,256}$/.test(e.principal),'COMMAND_PRINCIPAL');
  const key=crypto.createPublicKey(publicKey);
  assert(key.asymmetricKeyType==='ed25519'&&crypto.verify(null,Buffer.from(canonical(e)),key,Buffer.from(wrapper.signature,'base64url')),'COMMAND_SIGNATURE');
  return e;
}

/** Durable no-repeat fence independent of network retries and broker restarts. */
export class CommandJournal {
  constructor(directory){this.directory=directory;fs.mkdirSync(directory,{recursive:true,mode:0o700});}
  file(id){assert(/^[A-Za-z0-9_.:-]{8,160}$/.test(id),'COMMAND_ID');return path.join(this.directory,id+'.json');}
  begin(command){
    const file=this.file(command.command_id),prior=readJSON(file);
    if(prior){assert(prior.digest===command.command_digest,'COMMAND_ID_REUSE');return prior;}
    // Exclusive file creation prevents two independently started actuators claiming one command.
    const fd=fs.openSync(file,'wx',0o600);
    const value={digest:command.command_digest,state:'STARTED',started_at_ms:Date.now()};
    try{fs.writeFileSync(fd,canonical(value)+'\n');fs.fsyncSync(fd);}finally{fs.closeSync(fd);}
    const dir=fs.openSync(this.directory,'r');try{fs.fsyncSync(dir);}finally{fs.closeSync(dir);}
    return null;
  }
  finish(command,outcome){atomicJSON(this.file(command.command_id),{digest:command.command_digest,state:outcome.state,outcome});}
}
