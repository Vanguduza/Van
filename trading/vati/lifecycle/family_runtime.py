"""Bind lifecycle effects to the existing logical/physical runtime lease owner."""
from vati.app.account_lease import AccountRuntimeLease
from vati.app.physical_account_lease import PhysicalAccountRuntimeLease
from vati.core.canonical import canonical_hash
from vati.lifecycle.family_actions import FamilyActionError


def runtime_fence_ref(lease):
    if not isinstance(lease,AccountRuntimeLease) or lease.held is None:
        raise FamilyActionError('current runtime lease owner is unavailable')
    def body(owner):
        held=owner.held
        if held is None:
            raise FamilyActionError('current physical runtime lease owner is unavailable')
        return dict(account_alias=held.account_alias,holder_instance_id=held.holder_instance_id,
            lease_epoch=held.lease_epoch,acquired_at_ms=held.acquired_at_ms,
            software_version=held.software_version,git_sha=held.git_sha)
    result=dict(version='family-runtime-fence/1',logical=body(lease))
    if isinstance(lease,PhysicalAccountRuntimeLease):
        result['physical']=body(lease._physical)
        result['physical_scope']=lease.physical_scope.lease_key
    return canonical_hash(result)
