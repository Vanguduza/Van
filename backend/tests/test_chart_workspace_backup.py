"""Actual existing backup/restore service carries chart revisions and original outcomes."""
import pytest
from test_chart_workspace_persistence import service,create,state
from van_gateway.ops.backup import create_backup,restore,verify
from van_gateway.storage.db import Store
from van_gateway.trading.chart_models import ReplaceWorkspace
from van_gateway.trading.chart_workspaces import ChartWorkspaceService

@pytest.mark.asyncio
async def test_chart_revisions_and_original_outcomes_survive_real_backup_and_restore(tmp_path):
    charts=await service(tmp_path);original=await create(charts)
    latest=await charts.replace('owner',original.workspace_id,ReplaceWorkspace(request_id='before-backup',expected_revision=1,state=state('Layout before backup')))
    folder=tmp_path/'private-backup'
    manifest=create_backup(database_path=charts.store.path,destination=folder)
    assert manifest.schema_version==56 and manifest.row_counts['chart_workspace_revisions']==2
    assert verify(folder)['ok'] is True
    target=tmp_path/'recovered-owner.sqlite3';restore(folder,database_path=target)
    recovered_store=Store(str(target));await recovered_store.migrate();recovered=ChartWorkspaceService(recovered_store)
    assert await recovered.operation('owner','create-one')==original
    assert await recovered.operation('owner','before-backup')==latest
    assert (await recovered.get('owner',original.workspace_id)).state.name=='Layout before backup'
    first=await recovered.get('owner',original.workspace_id,1)
    assert first.state.panels[0].drawings[0].anchors[0].price=='0.000000000000000001'
    assert first.state.panels[0].drawings[0].note=='owner private note fixture'
    assert (await recovered.revisions('owner',original.workspace_id)).total_count==2
