"""Internal source integration with the existing private trading commander.

No HTTP/MCP command or frozen owner action is registered here. Any proposed new
public exposure still needs its independently reviewed action/lock amendment.
This owner verifies supplied signatures; it never issues grants/certificates.
"""
from contextlib import closing
from dataclasses import dataclass
import time

from vati.authority import OwnerAuthorityVerifier, OwnerAuthorityError
from vati.core.ledger_pg import open_ledger
from vati.risk.operational_grant import OperationalOptimizationGrants, PolicyAdmissionError, qualification_reader

CANONICAL_CONTROLS=('VAN-SO-039','VAN-EL-006')
PUBLIC_ACTION_BINDING='PROPOSED_UNADMITTED_NO_ROUTE_REGISTERED'


@dataclass(frozen=True)
class LifecyclePolicySettings:
    ledger: str
    owner_authority: object
    qualification_authority: object = None
    clock: object = lambda:int(time.time()*1000)



class LifecyclePolicyControls:
    """Private in-process controls; original durable records are authoritative."""
    def __init__(self, settings):
        self.settings=settings

    def _owner(self, ledger):
        return OperationalOptimizationGrants(ledger,owner_authority=self.settings.owner_authority,
            qualification_authority=self.settings.qualification_authority,clock=self.settings.clock)

    @staticmethod
    def _receipt(event):
        return dict(grant_id=event.payload['grant_id'],state=event.payload['state'],
            revision=event.payload['revision'],event_ref=event.hash,
            grant_hash=event.payload.get('grant_hash'),public_action_binding=PUBLIC_ACTION_BINDING,
            native_qualification_issued=False,estate_activation_performed=False)

    def admit(self, grant, qualification, *, owner_signature, qualification_signature, expected_ref=None):
        with closing(open_ledger(self.settings.ledger)) as ledger:
            event=self._owner(ledger).admit(grant,qualification,owner_signature=owner_signature,
                qualification_signature=qualification_signature,expected_ref=expected_ref)
            return self._receipt(event)

    def revoke(self, grant_id, *, owner_signature, expected_ref):
        with closing(open_ledger(self.settings.ledger)) as ledger:
            event=self._owner(ledger).revoke(grant_id,owner_signature=owner_signature,expected_ref=expected_ref)
            return self._receipt(event)

    def read(self, grant_id):
        with closing(open_ledger(self.settings.ledger)) as ledger:
            store=self._owner(ledger);event=store.latest(grant_id)
            if event is None:
                return dict(grant_id=grant_id,state='UNAVAILABLE',current_eligibility='NOT_QUALIFIED',
                    public_action_binding=PUBLIC_ACTION_BINDING)
            result=self._receipt(event)
            try:
                store.current(grant_id,expected_ref=event.hash)
                result['current_eligibility']='CURRENT_SOURCE_BINDING_VERIFIED'
            except (PolicyAdmissionError,OwnerAuthorityError,ValueError):
                result['current_eligibility']='NOT_QUALIFIED'
            return result
