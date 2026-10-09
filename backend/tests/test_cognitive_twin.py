"""Actual DDS common compiler + gateway MCP wire contract; no live qualification."""
import json
import subprocess
from pathlib import Path
import httpx
import pytest
from van_gateway.cognitive.twin import CognitiveTwinClient
from van_gateway.dial_dev.client import DialDevClient
from van_gateway.dial_dev.config import DialDevConfig


def common_twin():
    compiler = Path('/workspace/cf-dds/agent-system/orchestration/cognitive-twin.mjs')
    if not compiler.exists():
        return json.loads((Path(__file__).parent / 'fixtures/cognitive_twin_dds_compiler.json').read_text())
    script = "import {compileTwin} from " + json.dumps(compiler.as_uri()) + ";console.log(JSON.stringify(compileTwin({twin_id:'twin:van',twin_kind:'DEVELOPMENT',scope_id:'van',repository_sha:'abc',project_truth_hash:'sha256:truth',generated_at:'2026-10-06T12:00:00Z',freshness_ttl_seconds:300,facts:[{id:'repo',classification:'PUBLIC',authority:'CANONICAL',evidence_refs:['git:abc']}],dot_synthesis:{hypotheses:[{id:'h1',classification:'INTERNAL_SANITIZED',authority:'DERIVED',hypothesis:'check',evidence_refs:['git:abc']}]}})));"
    return json.loads(subprocess.check_output(['node', '--input-type=module', '-e', script], text=True))


@pytest.mark.asyncio
async def test_real_compiler_projection_preserved_through_scoped_mcp_wire(tmp_path):
    twin = common_twin()
    token = 'test-van-projection-' + 'x' * 40
    credential = tmp_path / 'token'; credential.write_text(token)
    requests = []
    def handler(request):
        requests.append(request)
        assert request.url.path == '/mcp'
        assert request.headers['authorization'] == 'Bearer ' + token
        assert json.loads(request.content) == {'jsonrpc':'2.0','id':'van-common-twin','method':'tools/call','params':{'name':'cognitive_twin_projection_get','arguments':{'project_id':'van'}}}
        return httpx.Response(200, json={'jsonrpc':'2.0','id':'van-common-twin','result':{'structuredContent':twin}})
    client = CognitiveTwinClient(DialDevClient(DialDevConfig(enabled=True,base_url='http://dds.test',token_file=str(credential)), transport=httpx.MockTransport(handler)))
    result = await client.read()
    assert result['projection'] == twin
    assert result['authority'] == 'DERIVED_READ_ONLY'
    assert result['live_qualification_claimed'] is False
    assert (await client.read('dial'))['reason'] == 'TWIN_PROJECT_SCOPE_DENIED'
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['restricted','malformed','echo','redirect'])
async def test_private_malformed_and_credential_bearing_upstream_never_reach_device(tmp_path, mutation):
    twin = common_twin(); token='x'*40
    credential=tmp_path/'token';credential.write_text(token)
    def handler(request):
        if mutation == 'restricted': twin['facts'][0]['classification']='RESTRICTED'
        if mutation == 'malformed': twin['dot_synthesis']=[]
        if mutation == 'echo': return httpx.Response(200,text=token)
        if mutation == 'redirect': return httpx.Response(302,headers={'location':'http://other.test'})
        return httpx.Response(200,json={'result':{'structuredContent':twin}})
    client=CognitiveTwinClient(DialDevClient(DialDevConfig(enabled=True,base_url='http://dds.test',token_file=str(credential)),transport=httpx.MockTransport(handler)))
    result=await client.read()
    assert result['state']=='DEGRADED' and result['projection'] is None
    assert token not in json.dumps(result)
