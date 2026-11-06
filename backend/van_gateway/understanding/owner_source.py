"""Read-only evidence for owner-derived learning; never issues authority."""
from dataclasses import dataclass
from typing import Any
from van_gateway.command.authority import AuthoritySource,CommandAuthorityRecord,CommandAuthorityService
from van_gateway.mission.models import AuthorityEnvelope
from van_gateway.models import ActionClass,OriginChannel,PrincipalType

@dataclass(frozen=True)
class OwnerMissionSource:
    mission: Any
    envelope: AuthorityEnvelope
    authority: CommandAuthorityRecord
    snapshot: Any

async def owner_mission_source(db: Any,mission_id: str)->OwnerMissionSource|None:
    native=await(await db.execute('SELECT * FROM missions WHERE mission_id=?',(mission_id,))).fetchone()
    if native is None:return None
    envelope=AuthorityEnvelope.model_validate_json(native['authority_envelope_json'])
    source=envelope.source_command_id
    if not source:return None
    row=await(await db.execute('SELECT value FROM runtime_meta WHERE key=?',(CommandAuthorityService.PREFIX+source,))).fetchone()
    if row is None:return None
    record=CommandAuthorityRecord.model_validate_json(row['value'])
    origins={OriginChannel.VOICE:'OWNER_VOICE',OriginChannel.TEXT:'OWNER_TEXT',OriginChannel.UI:'OWNER_UI'}
    if (record.command_id!=source or record.authority_source is not AuthoritySource.OWNER_COMMAND
        or record.principal_type is not PrincipalType.OWNER_DEVICE
        or envelope.max_action_class is not record.effective_action_class
        or native['owner_principal_id']!='device:'+record.device_id
        or record.origin_channel not in origins or native['origin_channel']!=record.origin_channel.value
        or native['origin']!=origins[record.origin_channel] or not record.request_hash
        or record.effective_action_class in {ActionClass.A4,ActionClass.A5} and not record.owner_approved):
        return None
    snapshot=await(await db.execute('SELECT command_id,digest,kernel_revision FROM context_snapshots WHERE snapshot_id=?',(record.snapshot_id,))).fetchone()
    if snapshot is None or snapshot['command_id']!=source or snapshot['digest']!=record.context_digest:return None
    return OwnerMissionSource(native,envelope,record,snapshot)
