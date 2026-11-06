import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {canonical,digest,verifyCommand,CommandJournal} from './protocol.mjs';
const keys=crypto.generateKeyPairSync('ed25519');
const pub=keys.publicKey.export({type:'spki',format:'pem'});
function command(change={}){const intent={action:'DECIDE_APPROVAL',choice:'DENY'};return {schema_version:1,command_id:'musecmd_fixture',command_digest:digest(intent),producer_id:'fixture',principal:'device:owner',issued_at_ms:1000,expires_at_ms:6000,intent,...change};}
function signed(e){return {envelope:e,signature:crypto.sign(null,Buffer.from(canonical(e)),keys.privateKey).toString('base64url')};}
test('canonical map ordering is shared with Python',()=>assert.equal(canonical({z:1,a:{c:'é',b:true}}),'{"a":{"b":true,"c":"é"},"z":1}'));
test('unsafe floats are rejected',()=>assert.throws(()=>canonical({a:NaN})));
test('signature binds current exact command',()=>assert.equal(verifyCommand(signed(command()),pub,'fixture',2000).command_id,'musecmd_fixture'));
test('signature rejects changed body',()=>{const c=signed(command());c.envelope.intent.choice='ALLOW_ONCE';assert.throws(()=>verifyCommand(c,pub,'fixture',2000));});
test('wrong producer is rejected',()=>assert.throws(()=>verifyCommand(signed(command()),pub,'another',2000)));
test('expired command is rejected',()=>assert.throws(()=>verifyCommand(signed(command()),pub,'fixture',6000)));
test('no blanket approval operation exists',()=>{const intent={action:'ALWAYS_ALLOW'};assert.throws(()=>verifyCommand(signed(command({intent,command_digest:digest(intent)})),pub,'fixture',2000));});
test('durable claim prevents replay after restart',()=>{const d=fs.mkdtempSync(path.join(os.tmpdir(),'muse-journal-'));try{const c=command(),j=new CommandJournal(d);assert.equal(j.begin(c),null);assert.equal(new CommandJournal(d).begin(c).state,'STARTED');j.finish(c,{state:'UNKNOWN'});assert.equal(new CommandJournal(d).begin(c).state,'UNKNOWN');}finally{fs.rmSync(d,{recursive:true,force:true});}});
test('same id with different contents is rejected',()=>{const d=fs.mkdtempSync(path.join(os.tmpdir(),'muse-journal-'));try{const j=new CommandJournal(d);j.begin(command());assert.throws(()=>j.begin(command({command_digest:'0'.repeat(64)})));}finally{fs.rmSync(d,{recursive:true,force:true});}});
