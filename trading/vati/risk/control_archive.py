"""Original direct-control signature data, never a new authority verifier.

The live authority owner verifies and consumes the token first. We archive its
exact public-key binding with the effect, so restart does not substitute today's
registry for the original proof. Historical validation grants no operation.
"""
from dataclasses import asdict
import hashlib
import json

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from vati.authority import OwnerAuthority, PREFIX, MAX_ACT_LIFETIME_SECONDS, _unb64u, canonical_statement


def archive_verified_control(token, verified):
    if type(verified) is not OwnerAuthority:
        raise ValueError('native control requires actual verified owner authority')
    binding = getattr(verified, '_verified_key_binding', None)
    if binding is None or not binding.is_current():
        raise ValueError('native control original owner key is unavailable')
    pem = binding._source.keys.get(binding.key_id)
    key = serialization.load_pem_public_key(pem.encode())
    der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if hashlib.sha256(der).hexdigest() != binding.public_key_sha256:
        raise ValueError('native control original owner key changed')
    return {'schema':'vati.original-direct-risk-control/1', 'token':token,
        'public_key_pem':pem, 'public_key_sha256':binding.public_key_sha256,
        'verified_authority':asdict(verified)}


def validate_original_control(event):
    """Check only the original effect's proof at its original application time."""
    p = event.payload
    archive = p['original_owner_control']
    if (archive['schema'] != 'vati.original-direct-risk-control/1'
            or archive['token'] != p['owner_signature_ref']):
        raise ValueError('original direct control archive mismatch')
    prefix, encoded, signature = archive['token'].split('.')
    body = json.loads(_unb64u(encoded))
    act = 'loss-streak-reset' if p['event'] == 'LOSS_STREAK_RESET' else 'drawdown-resume'
    subject = p['account_alias'] + ':' + p['scope'] if act == 'loss-streak-reset' else p['account_alias']
    original = archive['verified_authority']
    expected = {'act':act, 'subject':subject, 'issued_at_unix':body['iat'],
        'expires_at_unix':body['exp'], 'nonce':body['nonce'], 'key_id':body['kid']}
    if (prefix != PREFIX or original != expected or body['act'] != act or body['subject'] != subject
            or type(body['iat']) is not int or type(body['exp']) is not int
            or not isinstance(body['nonce'],str) or not body['nonce']
            or not 0 < body['exp'] - body['iat'] <= MAX_ACT_LIFETIME_SECONDS
            or event.event_time_ms//1000 + 60 < body['iat']
            or event.event_time_ms//1000 >= body['exp']):
        raise ValueError('original direct control does not bind its effect')
    key = serialization.load_pem_public_key(archive['public_key_pem'].encode())
    if not isinstance(key,ec.EllipticCurvePublicKey) or not isinstance(key.curve,ec.SECP256R1):
        raise ValueError('original direct control key must be P256')
    der = key.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    if hashlib.sha256(der).hexdigest() != archive['public_key_sha256']:
        raise ValueError('original direct control key fingerprint mismatch')
    key.verify(_unb64u(signature),canonical_statement(act=act,subject=subject,
        issued_at_unix=body['iat'],expires_at_unix=body['exp'],nonce=body['nonce']).encode(),
        ec.ECDSA(hashes.SHA256()))
    # This identity is for duplicate-effect detection, never token redemption.
    return archive['public_key_sha256'],body['nonce']
