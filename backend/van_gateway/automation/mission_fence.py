"""Automation checks the canonical mission lineage at every fresh admission."""
from van_gateway.mission.control import MissionControlError, require_mission_dispatch


async def require_automation_missions(store, *, command_id: str, source_command_id: str | None = None,
                                     mission_id: str | None = None, db=None):
    query = "SELECT mission_id FROM missions WHERE json_extract(authority_envelope_json,'$.source_command_id') IN (?,?)"
    params = (command_id, source_command_id or command_id)
    if db is None:
        rows = await store.fetchall(query, params)
    else:
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
    actual = {row["mission_id"] for row in rows}
    if mission_id and mission_id not in actual:
        raise MissionControlError("AUTOMATION_MISSION_AUTHORITY_MISMATCH")
    for actual_id in sorted(actual):
        await require_mission_dispatch(store, actual_id, db=db)
