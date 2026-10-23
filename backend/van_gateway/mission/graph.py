"""Owner read model of actual mission work; graph layout grants no authority."""
from __future__ import annotations

import hashlib
import heapq
import json
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, Field
from van_gateway.mission.models import Activity, ActivityState, MissionState


class GraphIssue(BaseModel):
    code: Literal['MISSING_DEPENDENCY','CYCLE','CONFLICTING_EXECUTOR_BINDING']
    node_ids: list[str]


class GraphNode(BaseModel):
    node_id: str
    state: ActivityState
    executor: str
    executor_ref: str | None
    executor_state: str | None = None
    executor_observation_available: bool = False
    evidence_refs: list[str] = Field(default_factory=list)
    started_at_ms: int
    ended_at_ms: int | None


class GraphEdge(BaseModel):
    edge_id: str
    source: str
    target: str


class DependencyPath(BaseModel):
    basis: Literal['DEPENDENCY_COUNT'] = 'DEPENDENCY_COUNT'
    node_ids: list[str]
    edge_count: int
    estimated_duration_ms: None = None


class MissionGraph(BaseModel):
    mission_id: str
    mission_state: MissionState
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    issues: list[GraphIssue]
    critical_path: DependencyPath | None
    authority_granted: Literal[False] = False
    snapshot_basis: Literal['GATEWAY_DURABLE_STATE'] = 'GATEWAY_DURABLE_STATE'


def project_graph(mission_id, mission_state, activities, *, evidence=None, observations=None):
    """Longest dependency chain, never an invented duration or success verdict.

    A single database snapshot supplies all inputs. Unavailable executor state
    remains unavailable. Cycles, orphans and duplicate executor claims suppress
    a critical path instead of presenting a broken plan as executable.
    """
    evidence=evidence or {}; observations=observations or {}
    activities=sorted(activities,key=lambda a:a.activity_id)
    if len(activities)>2000:raise ValueError('MISSION_GRAPH_NODE_LIMIT')
    nodes={a.activity_id:a for a in activities};edges={};issues=[]
    successors={n:set() for n in nodes};predecessors={n:set() for n in nodes}
    bindings=defaultdict(list)
    for a in activities:
        if a.mission_id!=mission_id:raise ValueError('MISSION_GRAPH_SCOPE_MISMATCH')
        if a.executor_ref:bindings[(a.executor,a.executor_ref)].append(a.activity_id)
        for dep in sorted(set(a.dependency_activity_ids)):
            raw=json.dumps([mission_id,dep,a.activity_id],ensure_ascii=False,separators=(',',':')).encode()
            edge=GraphEdge(edge_id='medge_'+hashlib.sha256(raw).hexdigest(),source=dep,target=a.activity_id)
            edges[(dep,a.activity_id)]=edge
            if len(edges)>10000:raise ValueError('MISSION_GRAPH_EDGE_LIMIT')
            if dep not in nodes:issues.append(GraphIssue(code='MISSING_DEPENDENCY',node_ids=[dep,a.activity_id]))
            else:successors[dep].add(a.activity_id);predecessors[a.activity_id].add(dep)
    for ids in bindings.values():
        if len(ids)>1:issues.append(GraphIssue(code='CONFLICTING_EXECUTOR_BINDING',node_ids=ids))
    # Iterative Kosaraju, so long workflows cannot overflow Python recursion.
    seen=set();finish=[]
    for start in sorted(nodes):
        if start in seen:continue
        seen.add(start);stack=[(start,iter(sorted(successors[start])))]
        while stack:
            n,it=stack[-1];v=next(it,None)
            if v is None:finish.append(n);stack.pop()
            elif v not in seen:seen.add(v);stack.append((v,iter(sorted(successors[v]))))
    seen=set()
    for start in reversed(finish):
        if start in seen:continue
        seen.add(start);component=[];stack=[start]
        while stack:
            n=stack.pop();component.append(n)
            for v in sorted(predecessors[n]):
                if v not in seen:seen.add(v);stack.append(v)
        if len(component)>1 or start in successors[start]:
            issues.append(GraphIssue(code='CYCLE',node_ids=sorted(component)))
    path=None
    if not issues:
        degree={n:len(predecessors[n]) for n in nodes};ready=[n for n in nodes if degree[n]==0];heapq.heapify(ready)
        length={n:0 for n in nodes};parent={n:None for n in nodes}
        while ready:
            n=heapq.heappop(ready)
            for v in sorted(successors[n]):
                if length[n]+1>length[v]:length[v]=length[n]+1;parent[v]=n
                degree[v]-=1
                if degree[v]==0:heapq.heappush(ready,v)
        chain=[]
        if nodes:
            n=min(nodes,key=lambda n:(-length[n],n))
            while n is not None:chain.append(n);n=parent[n]
            chain.reverse()
        path=DependencyPath(node_ids=chain,edge_count=max(0,len(chain)-1))
    result=[]
    for a in activities:
        o=observations.get(a.activity_id)
        refs=set(evidence.get(a.activity_id,[]))
        if o and o.get('evidence_ref'):refs.add(o['evidence_ref'])
        result.append(GraphNode(node_id=a.activity_id,state=a.state,executor=a.executor,
            executor_ref=a.executor_ref,executor_state=o['state'] if o else None,
            executor_observation_available=o is not None,evidence_refs=sorted(refs),
            started_at_ms=a.started_at_ms,ended_at_ms=a.ended_at_ms))
    return MissionGraph(mission_id=mission_id,mission_state=mission_state,nodes=result,
        edges=[edges[k] for k in sorted(edges)],issues=sorted(issues,key=lambda i:(i.code,i.node_ids)),critical_path=path)
