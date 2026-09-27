from __future__ import annotations

import json
import time
import uuid
from typing import Any

from van_gateway.attention.engine import AttentionEngine
from van_gateway.models import AttentionSeverity
from van_gateway.storage.db import Store

from .models import Suggestion,SuggestionCreate,SuggestionDecision,SuggestionStatus


class SuggestionServiceError(ValueError):
    def __init__(self,code:str,detail:str|None=None)->None:
        super().__init__(code if detail is None else f"{code}: {detail}")
        self.code=code; self.detail=detail


class SuggestionService:
    """Evidence-backed idea lifecycle. Acceptance never executes the proposed action."""

    def __init__(self,store:Store,attention:AttentionEngine)->None:
        self.store=store; self.attention=attention

    @staticmethod
    def _row(row:Any)->Suggestion:
        return Suggestion(
            suggestion_id=row["suggestion_id"],title=row["title"],rationale=row["rationale"],
            proposed_prompt=row["proposed_prompt"],edited_prompt=row["edited_prompt"],
            source_refs=json.loads(row["source_refs_json"] or "[]"),
            status=SuggestionStatus(row["status"]),attention_id=row["attention_id"],
            project_id=row["project_id"],created_at_ms=int(row["created_at_ms"]),
            updated_at_ms=int(row["updated_at_ms"]),decided_at_ms=row["decided_at_ms"],
        )

    async def create(self,body:SuggestionCreate,*,now_ms:int|None=None)->Suggestion:
        if not body.source_refs:
            raise SuggestionServiceError("SUGGESTION_EVIDENCE_REQUIRED")
        now=int(time.time()*1000) if now_ms is None else now_ms
        sid=f"sug_{uuid.uuid4().hex}"
        item=await self.attention.upsert(
            title=body.title,severity=AttentionSeverity.INFO,source="suggestion",
            dedupe_key=f"suggestion:{sid}",project_id=body.project_id,
            payload={"suggestion_id":sid,"source_refs":body.source_refs},
        )
        await self.store.execute(
            """
            INSERT INTO suggestions(
              suggestion_id,title,rationale,proposed_prompt,edited_prompt,source_refs_json,
              status,attention_id,project_id,created_at_ms,updated_at_ms,decided_at_ms
            ) VALUES (?, ?, ?, ?, NULL, ?, 'NEW', ?, ?, ?, ?, NULL)
            """,
            (sid,body.title.strip(),body.rationale.strip(),body.proposed_prompt.strip(),
             Store.dumps(body.source_refs),item.id,body.project_id,now,now),
        )
        out=await self.get(sid); assert out is not None; return out

    async def get(self,suggestion_id:str)->Suggestion|None:
        row=await self.store.fetchone("SELECT * FROM suggestions WHERE suggestion_id = ?",(suggestion_id,))
        return None if row is None else self._row(row)

    async def list(self,status:SuggestionStatus|None=None,limit:int=100)->list[Suggestion]:
        if status is None:
            rows=await self.store.fetchall("SELECT * FROM suggestions ORDER BY created_at_ms DESC LIMIT ?",(max(1,min(limit,500)),))
        else:
            rows=await self.store.fetchall("SELECT * FROM suggestions WHERE status = ? ORDER BY created_at_ms DESC LIMIT ?",(status.value,max(1,min(limit,500))))
        return [self._row(r) for r in rows]

    async def decide(self,suggestion_id:str,body:SuggestionDecision,*,now_ms:int|None=None)->dict[str,Any]:
        current=await self.get(suggestion_id)
        if current is None: raise SuggestionServiceError("SUGGESTION_UNKNOWN")
        if current.status is not SuggestionStatus.NEW:
            raise SuggestionServiceError("SUGGESTION_ALREADY_DECIDED")
        now=int(time.time()*1000) if now_ms is None else now_ms
        if body.action=="dismiss":
            status=SuggestionStatus.DISMISSED; prompt=None
        elif body.action=="edit":
            if not (body.edited_prompt or "").strip(): raise SuggestionServiceError("SUGGESTION_EDIT_REQUIRED")
            status=SuggestionStatus.EDITED; prompt=body.edited_prompt.strip()
        else:
            status=SuggestionStatus.ACCEPTED; prompt=current.proposed_prompt
        await self.store.execute(
            "UPDATE suggestions SET status = ?, edited_prompt = ?, updated_at_ms = ?, decided_at_ms = ? WHERE suggestion_id = ?",
            (status.value,body.edited_prompt.strip() if body.edited_prompt else None,now,now,suggestion_id),
        )
        if current.attention_id:
            await self.attention.mark_handled(current.attention_id)
        # Important: this is a prompt to submit as a fresh owner command. It is not executed here.
        return {"suggestion_id":suggestion_id,"status":status.value,"fresh_owner_prompt":prompt}
