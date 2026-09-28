from __future__ import annotations

import json
import time
import uuid
from typing import Any

from van_gateway.storage.db import Store

from .models import ConversationFollowUp,ConversationMessage,ConversationThread,FollowUpStatus,ThreadKind,ThreadStatus


class ConversationServiceError(ValueError):
    def __init__(self,code:str)->None:
        super().__init__(code); self.code=code


class ConversationService:
    """Self-hosted thread state. History is presentation/context, never execution truth."""

    def __init__(self,store:Store)->None:self.store=store

    @staticmethod
    def _followup(row:Any)->ConversationFollowUp:
        return ConversationFollowUp(
            followup_id=row["followup_id"],thread_id=row["thread_id"],prompt=row["prompt"],
            status=FollowUpStatus(row["status"]),command_id=row["command_id"],
            created_at_ms=int(row["created_at_ms"]),updated_at_ms=int(row["updated_at_ms"]),
        )

    @staticmethod
    def _message(row:Any)->ConversationMessage:
        return ConversationMessage(
            message_id=row["message_id"],thread_id=row["thread_id"],role=row["role"],body=row["body"],
            command_id=row["command_id"],mission_id=row["mission_id"],
            artifact_refs=json.loads(row["artifact_refs_json"] or "[]"),
            terminal=bool(row["terminal"]),created_at_ms=int(row["created_at_ms"]),
        )

    async def ensure_main(self,*,now_ms:int|None=None)->ConversationThread:
        row=await self.store.fetchone("SELECT thread_id FROM conversation_threads WHERE kind = 'MAIN' LIMIT 1")
        if row is None:
            now=int(time.time()*1000) if now_ms is None else now_ms
            tid=f"thr_{uuid.uuid4().hex}"
            await self.store.execute(
                "INSERT INTO conversation_threads(thread_id,title,kind,status,project_id,created_at_ms,updated_at_ms,archived_at_ms) VALUES (?, 'VAN', 'MAIN', 'ACTIVE', NULL, ?, ?, NULL)",
                (tid,now,now),
            )
            return await self.get(tid)  # type: ignore[return-value]
        return await self.get(row["thread_id"])  # type: ignore[return-value]

    async def create(self,title:str,project_id:str|None=None,*,now_ms:int|None=None)->ConversationThread:
        if not title.strip(): raise ConversationServiceError("THREAD_TITLE_REQUIRED")
        now=int(time.time()*1000) if now_ms is None else now_ms
        tid=f"thr_{uuid.uuid4().hex}"
        await self.store.execute(
            "INSERT INTO conversation_threads(thread_id,title,kind,status,project_id,created_at_ms,updated_at_ms,archived_at_ms) VALUES (?, ?, 'SIDE', 'ACTIVE', ?, ?, ?, NULL)",
            (tid,title.strip(),project_id,now,now),
        )
        out=await self.get(tid); assert out is not None; return out

    async def get(self,thread_id:str,*,message_limit:int=200)->ConversationThread|None:
        row=await self.store.fetchone("SELECT * FROM conversation_threads WHERE thread_id = ?",(thread_id,))
        if row is None:return None
        messages=await self.store.fetchall(
            "SELECT * FROM conversation_messages WHERE thread_id = ? ORDER BY created_at_ms ASC LIMIT ?",
            (thread_id,max(1,min(message_limit,1000))),
        )
        draft=await self.store.fetchone("SELECT draft_text FROM conversation_drafts WHERE thread_id = ?",(thread_id,))
        followups=await self.store.fetchall(
            "SELECT * FROM conversation_followups WHERE thread_id = ? ORDER BY created_at_ms ASC",
            (thread_id,),
        )
        return ConversationThread(
            thread_id=row["thread_id"],title=row["title"],kind=ThreadKind(row["kind"]),
            status=ThreadStatus(row["status"]),project_id=row["project_id"],
            created_at_ms=int(row["created_at_ms"]),updated_at_ms=int(row["updated_at_ms"]),
            archived_at_ms=row["archived_at_ms"],draft_text="" if draft is None else draft["draft_text"],
            messages=[self._message(m) for m in messages],
            followups=[self._followup(item) for item in followups],
        )

    async def list(self,status:ThreadStatus|None=None,limit:int=100)->list[ConversationThread]:
        if status is None:
            rows=await self.store.fetchall("SELECT thread_id FROM conversation_threads ORDER BY kind ASC, updated_at_ms DESC LIMIT ?",(max(1,min(limit,500)),))
        else:
            rows=await self.store.fetchall("SELECT thread_id FROM conversation_threads WHERE status = ? ORDER BY kind ASC, updated_at_ms DESC LIMIT ?",(status.value,max(1,min(limit,500))))
        out=[]
        for r in rows:
            item=await self.get(r["thread_id"],message_limit=1)
            if item is not None: item.messages=[]; out.append(item)
        return out

    async def rename(self,thread_id:str,title:str,*,now_ms:int|None=None)->ConversationThread:
        current=await self.get(thread_id, message_limit=1)
        if current is None: raise ConversationServiceError("THREAD_UNKNOWN")
        if not title.strip(): raise ConversationServiceError("THREAD_TITLE_REQUIRED")
        now=int(time.time()*1000) if now_ms is None else now_ms
        await self.store.execute("UPDATE conversation_threads SET title = ?, updated_at_ms = ? WHERE thread_id = ?",(title.strip(),now,thread_id))
        out=await self.get(thread_id); assert out is not None; return out

    async def set_status(self,thread_id:str,status:ThreadStatus,*,now_ms:int|None=None)->ConversationThread:
        current=await self.get(thread_id,message_limit=1)
        if current is None: raise ConversationServiceError("THREAD_UNKNOWN")
        if current.kind is ThreadKind.MAIN and status is ThreadStatus.ARCHIVED:
            raise ConversationServiceError("MAIN_THREAD_CANNOT_ARCHIVE")
        now=int(time.time()*1000) if now_ms is None else now_ms
        archived=now if status is ThreadStatus.ARCHIVED else None
        await self.store.execute("UPDATE conversation_threads SET status = ?, archived_at_ms = ?, updated_at_ms = ? WHERE thread_id = ?",(status.value,archived,now,thread_id))
        out=await self.get(thread_id); assert out is not None; return out

    async def save_draft(self,thread_id:str,text:str,*,now_ms:int|None=None)->ConversationThread:
        if await self.get(thread_id,message_limit=1) is None: raise ConversationServiceError("THREAD_UNKNOWN")
        now=int(time.time()*1000) if now_ms is None else now_ms
        await self.store.execute(
            """
            INSERT INTO conversation_drafts(thread_id,draft_text,updated_at_ms) VALUES (?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET draft_text=excluded.draft_text, updated_at_ms=excluded.updated_at_ms
            """,(thread_id,text,now),
        )
        out=await self.get(thread_id); assert out is not None; return out

    async def append_message(
        self,thread_id:str,*,role:str,body:str,command_id:str|None=None,mission_id:str|None=None,
        artifact_refs:list[str]|None=None,terminal:bool=False,now_ms:int|None=None,
    )->ConversationMessage:
        thread=await self.get(thread_id,message_limit=1)
        if thread is None: raise ConversationServiceError("THREAD_UNKNOWN")
        if thread.status is ThreadStatus.ARCHIVED: raise ConversationServiceError("THREAD_ARCHIVED")
        if role not in {"OWNER","VAN","SYSTEM"}: raise ConversationServiceError("MESSAGE_ROLE_INVALID")
        if not body.strip(): raise ConversationServiceError("MESSAGE_BODY_REQUIRED")
        now=int(time.time()*1000) if now_ms is None else now_ms
        mid=f"msg_{uuid.uuid4().hex}"
        await self.store.execute(
            "INSERT INTO conversation_messages(message_id,thread_id,role,body,command_id,mission_id,artifact_refs_json,terminal,created_at_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mid,thread_id,role,body,command_id,mission_id,Store.dumps(artifact_refs or []),1 if terminal else 0,now),
        )
        await self.store.execute("UPDATE conversation_threads SET updated_at_ms = ? WHERE thread_id = ?",(now,thread_id))
        return ConversationMessage(message_id=mid,thread_id=thread_id,role=role,body=body,command_id=command_id,mission_id=mission_id,artifact_refs=artifact_refs or [],terminal=terminal,created_at_ms=now)


    async def queue_followup(
        self,thread_id:str,prompt:str,*,now_ms:int|None=None
    )->ConversationFollowUp:
        thread=await self.get(thread_id,message_limit=1)
        if thread is None: raise ConversationServiceError("THREAD_UNKNOWN")
        if thread.status is ThreadStatus.ARCHIVED: raise ConversationServiceError("THREAD_ARCHIVED")
        value=prompt.strip()
        if not value: raise ConversationServiceError("FOLLOWUP_PROMPT_REQUIRED")
        if len(value)>8000: raise ConversationServiceError("FOLLOWUP_PROMPT_TOO_LONG")
        now=int(time.time()*1000) if now_ms is None else now_ms
        fid=f"fu_{uuid.uuid4().hex}"
        await self.store.execute(
            "INSERT INTO conversation_followups(followup_id,thread_id,prompt,status,command_id,created_at_ms,updated_at_ms) VALUES (?, ?, ?, 'QUEUED', NULL, ?, ?)",
            (fid,thread_id,value,now,now),
        )
        return ConversationFollowUp(
            followup_id=fid,thread_id=thread_id,prompt=value,status=FollowUpStatus.QUEUED,
            command_id=None,created_at_ms=now,updated_at_ms=now,
        )

    async def decide_followup(
        self,thread_id:str,followup_id:str,action:str,*,command_id:str|None=None,now_ms:int|None=None
    )->ConversationFollowUp:
        row=await self.store.fetchone(
            "SELECT * FROM conversation_followups WHERE thread_id = ? AND followup_id = ?",
            (thread_id,followup_id),
        )
        if row is None: raise ConversationServiceError("FOLLOWUP_UNKNOWN")
        current=self._followup(row)
        if current.status is not FollowUpStatus.QUEUED:
            raise ConversationServiceError("FOLLOWUP_ALREADY_DECIDED")
        if action not in {"promote","dismiss"}:
            raise ConversationServiceError("FOLLOWUP_ACTION_INVALID")
        if action=="promote" and not (command_id or "").strip():
            raise ConversationServiceError("FOLLOWUP_COMMAND_ID_REQUIRED")
        status=FollowUpStatus.PROMOTED if action=="promote" else FollowUpStatus.DISMISSED
        now=int(time.time()*1000) if now_ms is None else now_ms
        await self.store.execute(
            "UPDATE conversation_followups SET status = ?, command_id = ?, updated_at_ms = ? WHERE followup_id = ?",
            (status.value,command_id if status is FollowUpStatus.PROMOTED else None,now,followup_id),
        )
        return ConversationFollowUp(
            followup_id=current.followup_id,thread_id=current.thread_id,prompt=current.prompt,
            status=status,command_id=command_id if status is FollowUpStatus.PROMOTED else None,
            created_at_ms=current.created_at_ms,updated_at_ms=now,
        )
