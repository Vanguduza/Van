/** Closed transport surface; the server supplies the actual DIAL owner-surface port.
 * Browser JSON cannot supply an actor, scope, qualification or native implementation. */
export const OWNER_OPERATIONS = Object.freeze(['dial_owner_contexts','dial_owner_discover','dial_owner_profiles','dial_owner_route','dial_owner_status','dial_owner_control','dial_owner_session','dial_owner_artifact']);
export function validateOwnerCall(operation,args) {
 if(operation==='dial_owner_contexts'&&args&&Object.keys(args).length===0)return;
 if(!OWNER_OPERATIONS.includes(operation)||!args||Array.isArray(args)||Object.keys(args).some(k=>!['context_ref','input'].includes(k))||typeof args.context_ref!=='string'||!args.context_ref||!args.input||Array.isArray(args.input)||typeof args.input!=='object')throw Error('OWNER_CONTROL_ARGUMENTS_INVALID');
 if(operation==='dial_owner_control'&&(!['pause','cancel','checkpoint','resume'].includes(args.input.action)||typeof args.input.request_id!=='string'||args.input.request_id.length<8))throw Error('OWNER_CONTROL_BINDING_REQUIRED');
 if(operation==='dial_owner_session'&&!['inspect','view','takeover','release','control'].includes(args.input.method))throw Error('OWNER_SESSION_METHOD_INVALID');
}
export async function invokeOwnerControl(port,operation,args,context) {
 validateOwnerCall(operation,args);
 if(typeof port?.invoke!=='function')throw Error('OWNER_CONTROLS_NOT_CONNECTED');
 return port.invoke(operation,structuredClone(args),context);
}
export function sourceAge(at,now=Date.now()) {const ms=typeof at==='number'?at:Date.parse(at);return Number.isFinite(ms)&&now>=ms?Math.floor((now-ms)/1000):null;}
export function workflowLabels(row) {
 return {execution:row.state||'UNOBSERVED',verification:row.verification_receipt?'Evidence available':'Unverified',qualification:row.qualification?.state||'Unqualified',wait:row.reason||row.wait_reason||'No wait reason observed',effect:row.effect_state||'Unobserved'};
}

/** The ORIGINAL Site supplies its existing authenticated Global DIAL transport.
 * It verifies its owner proof and native consumer qualification, and constructs
 * no authority from a browser field or a captured page. */
export function createDialOwnerSurfaceAdapter(callExistingOwnerTool) {
 if(typeof callExistingOwnerTool!=='function')return null;
 return Object.freeze({invoke(operation,args,verifiedActor){validateOwnerCall(operation,args);return callExistingOwnerTool(operation,args,verifiedActor);}});
}
