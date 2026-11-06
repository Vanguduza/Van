"""Consume DDS's common twin unchanged using the existing VAN_PROJECTION principal."""
import json

from van_gateway.dial_dev.client import DialDevClient, DialDevDisabled, DialDevUnavailable


class CognitiveTwinClient:
    def __init__(self, client: DialDevClient, *, projects=('van',)):
        self.client = client
        self.projects = frozenset(projects)

    async def read(self, project_id='van') -> dict:
        if project_id not in self.projects:
            return {'state': 'DEGRADED', 'reason': 'TWIN_PROJECT_SCOPE_DENIED', 'projection': None}
        try:
            upstream = await self.client.post('/mcp', {'jsonrpc': '2.0', 'id': 'van-common-twin',
                'method': 'tools/call', 'params': {'name': 'cognitive_twin_projection_get',
                                                 'arguments': {'project_id': project_id}}})
            if upstream.status_code != 200:
                raise DialDevUnavailable('upstream_error')
            if len(upstream.body) > 512_000:
                raise DialDevUnavailable("upstream_malformed")
            body = json.loads(upstream.body)
            result = body.get('result', {})
            if result.get('isError') or body.get('error'):
                raise DialDevUnavailable('upstream_auth_refused')
            twin = result.get('structuredContent')
            if twin is None:
                twin = json.loads(result['content'][0]['text'])
            required = {'schema_version', 'twin_id', 'twin_kind', 'scope_id', 'repository_sha',
                'project_truth_hash', 'facts', 'projection_revision', 'machine_facts_hash',
                'generated_at', 'freshness', 'dot_synthesis', 'owner_annotations', 'open_questions', 'decisions_required'}
            if not isinstance(twin, dict) or not required <= twin.keys() or twin['scope_id'] != project_id:
                raise DialDevUnavailable('upstream_malformed')
            if twin['schema_version'] != 1 or not isinstance(twin['facts'], list) or len(twin['facts']) > 100:
                raise DialDevUnavailable('upstream_malformed')
            for group in ('facts', 'derived_current_state', 'attention', 'owner_annotations'):
                if not isinstance(twin.get(group, []), list) or len(twin.get(group, [])) > 100:
                    raise DialDevUnavailable('upstream_malformed')
                if any(not isinstance(r, dict) or r.get('classification') not in ('PUBLIC', 'INTERNAL_SANITIZED') for r in twin.get(group, [])):
                    raise DialDevUnavailable('upstream_malformed')
            for group in ('observations', 'hypotheses'):
                if not isinstance(twin.get(group, []), list) or len(twin.get(group, [])) > 100:
                    raise DialDevUnavailable('upstream_malformed')
                if any(not isinstance(r, dict) or r.get('classification') not in ('PUBLIC', 'INTERNAL_SANITIZED') for r in twin['dot_synthesis'].get(group, [])):
                    raise DialDevUnavailable('upstream_malformed')
            if twin['freshness'].get('state') not in ('CURRENT', 'STALE'):
                raise DialDevUnavailable('upstream_malformed')
            # Do not rebuild facts, narratives, repository refs or source revision locally.
            return {'state': 'AVAILABLE', 'authority': 'DERIVED_READ_ONLY', 'projection': twin,
                    'live_qualification_claimed': False}
        except DialDevDisabled:
            return {'state': 'DEGRADED', 'reason': 'TWIN_CONSUMER_DISABLED', 'projection': None}
        except DialDevUnavailable as exc:
            return {'state': 'DEGRADED', 'reason': exc.reason, 'projection': None}
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            return {'state': 'DEGRADED', 'reason': 'upstream_malformed', 'projection': None}
