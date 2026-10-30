"""Resolve owner account edits without replacing omitted native settings."""
from dataclasses import replace

from fastapi import HTTPException

from vati.accounts import Account, AccountRegistryError, CredentialRef
from vati.accounts.access import validate_mode
from vati.execution.deriv_identity import DerivIdentityError,validate_deriv_endpoint as validate_provider_endpoint

TEXT_FIELDS = frozenset({'broker','mode','currency','label','server','login','bridge_url','mandate_ref','venue','notes'})
BOOL_FIELDS = frozenset({'demo','enabled'})
PRIVATE_FIELDS = frozenset({'_expected_resource_version','_native_operation','_expected_review_digest'})
NATIVE_BROKERS = frozenset({'DERIV','CTRADER','MT5','MT5_EA'})
IDENTITY_FIELDS = frozenset({'broker','currency','server','login','bridge_url','demo','venue'})


def validate_deriv_endpoint(endpoint):
    try:
        validate_provider_endpoint(endpoint)
    except DerivIdentityError as exc:
        raise HTTPException(422,str(exc)) from None


def resolve_account_config(args, *, alias, current, secret_path):
    if set(args) - ({'alias'} | TEXT_FIELDS | BOOL_FIELDS | PRIVATE_FIELDS):
        raise HTTPException(422,'Unsupported account configuration fields')
    changes={}
    for key in TEXT_FIELDS:
        if key not in args:
            continue
        if not isinstance(args[key],str):
            raise HTTPException(422,f'{key} must be text')
        changes[key]=args[key]
    for key in BOOL_FIELDS:
        if key in args:
            if type(args[key]) is not bool:
                raise HTTPException(422,f'{key} must be a JSON boolean')
            changes[key]=args[key]
    for key in ('broker','currency'):
        if key in changes:
            changes[key]=changes[key].upper()
    if current is None:
        broker=changes.get('broker')
        if not broker:
            raise HTTPException(422,'broker is required for a new account')
        credential=CredentialRef(secrets_file=str(secret_path)) if broker in NATIVE_BROKERS else CredentialRef()
        candidate=Account(alias=alias,broker=broker,credential_ref=credential,
            mode='DEMO_TRADER' if changes.get('demo',True) else 'OBSERVE',currency='USD')
    else:
        candidate=current
    candidate=replace(candidate,**changes)
    if not candidate.label:
        candidate=replace(candidate,label=alias)
    try:
        candidate.validate()
        if candidate.enabled or current is None:
            validate_mode(candidate,candidate.mode)
    except (AccountRegistryError,RuntimeError) as exc:
        raise HTTPException(422,str(exc)) from None
    if candidate.broker=='DERIV' and (candidate.enabled or current is None or candidate.bridge_url!=current.bridge_url):
        validate_deriv_endpoint(candidate.bridge_url)
    if current is not None and any(getattr(candidate,key)!=getattr(current,key) for key in IDENTITY_FIELDS):
        # Changing a native connection can orphan active protection. The
        # explicit migration contract needs independent current state proof;
        # a metadata edit or new credential file is not such a proof.
        raise HTTPException(409,'Native account identity changes require verified migration; current connection retained')
    return candidate
