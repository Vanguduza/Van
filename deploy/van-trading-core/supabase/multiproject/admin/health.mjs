// Process/config health only; never claim whole-platform production readiness.
import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
try{
 const path=process.env.DIAL_PROJECT_ADMIN_REGISTRY,expected=process.env.DIAL_PROJECT_ADMIN_REGISTRY_SHA256;
 const port=Number(process.env.DIAL_PROJECT_ADMIN_PORT);
 if(!path?.startsWith('/')||!/^[a-f0-9]{64}$/.test(expected??'')||!Number.isInteger(port)||port<1024||port>65535)throw Error();
 const info=await fs.lstat(path);
 if(!info.isFile()||info.isSymbolicLink()||info.nlink!==1||(info.mode&0o077)||info.size>1048576)throw Error();
 const raw=await fs.readFile(path);if(createHash('sha256').update(raw).digest('hex')!==expected)throw Error();
 const value=JSON.parse(raw);
 const response=await fetch('http://127.0.0.1:'+port+'/_internal/health',{headers:{'x-dial-admin-health':value.health_key},signal:AbortSignal.timeout(3000),redirect:'error'});
 if(!response.ok||(await response.json()).state!=='PRIVATE_ADMIN_CANDIDATE_READY')throw Error();
 process.exitCode=0;
}catch{process.exitCode=1;}
