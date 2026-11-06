from __future__ import annotations

import json
import hashlib
import time
import uuid
from typing import Any

from van_gateway.storage.db import Store

from .models import ConversationFollowUp,ConversationMessage,ConversationMessagePage,ConversationThread,FollowUpStatus,ThreadKind,ThreadStatus


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

    async def ensure_main(self, *, now_ms: int | None = None) -> ConversationThread:
        now = int(time.time()*1000) if now_ms is None else now_ms
        row = await self.store.fetchone("SELECT thread_id FROM conversation_threads WHERE kind='MAIN'",())
        if row is None:
            async with self.store.connection() as db:
                await db.execute("BEGIN IMMEDIATE")
                await db.execute(
                    "INSERT OR IGNORE INTO conversation_threads(thread_id,title,kind,status,project_id,created_at_ms,updated_at_ms,archived_at_ms) VALUES(?, 'VAN','MAIN','ACTIVE',NULL,?,?,NULL)",
                    ("thr_"+uuid.uuid4().hex,now,now),
                )
                row = await (await db.execute("SELECT thread_id FROM conversation_threads WHERE kind='MAIN'",())).fetchone()
                await db.commit()
        result = await self.get(row["thread_id"])
        assert result is not None
        return result

    async def create(self,title:str,project_id:str|None=None,*,now_ms:int|None=None)->ConversationThread:
        if not title.strip(): raise ConversationServiceError("THREAD_TITLE_REQUIRED")
        now=int(time.time()*1000) if now_ms is None else now_ms
        tid=f"thr_{uuid.uuid4().hex}"
        await self.store.execute(
            "INSERT INTO conversation_threads(thread_id,title,kind,status,project_id,created_at_ms,updated_at_ms,archived_at_ms) VALUES (?, ?, 'SIDE', 'ACTIVE', ?, ?, ?, NULL)",
            (tid,title.strip(),project_id,now,now),
        )
        out=await self.get(tid); assert out is not None; return out

    async def _message_page(self, db: Any, thread_id: str, *, limit: int,
                            before_message_id: str | None = None) -> ConversationMessagePage:
        bound = max(1,min(limit,1000))
        params: list[Any] = [thread_id]
        where = "thread_id=?"
        if before_message_id is not None:
            cursor = await (await db.execute(
                "SELECT rowid AS position,created_at_ms FROM conversation_messages WHERE message_id=? AND thread_id=?",
                (before_message_id,thread_id),
            )).fetchone()
            if cursor is None:
                raise ConversationServiceError("MESSAGE_CURSOR_INVALID")
            where += " AND (created_at_ms<? OR (created_at_ms=? AND rowid<?))"
            params += [cursor["created_at_ms"],cursor["created_at_ms"],cursor["position"]]
        rows = await (await db.execute(
            f"SELECT * FROM conversation_messages WHERE {where} ORDER BY created_at_ms DESC,rowid DESC LIMIT ?",
            tuple(params+[bound+1]),
        )).fetchall()
        count = await (await db.execute("SELECT count(*) AS n FROM conversation_messages WHERE thread_id=?",(thread_id,))).fetchone()
        more = len(rows)>bound
        visible = list(reversed(rows[:bound]))
        return ConversationMessagePage(thread_id=thread_id,messages=[self._message(row) for row in visible],
            total_count=int(count["n"]),has_more=more,
            next_before_message_id=visible[0]["message_id"] if more and visible else None)

    async def messages_page(self, thread_id: str, *, limit: int = 200,
                            before_message_id: str | None = None) -> ConversationMessagePage:
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            row = await (await db.execute("SELECT thread_id FROM conversation_threads WHERE thread_id=?",(thread_id,))).fetchone()
            if row is None:
                raise ConversationServiceError("THREAD_UNKNOWN")
            return await self._message_page(db,thread_id,limit=limit,before_message_id=before_message_id)

    async def _thread(self, db: Any, row: Any, *, message_limit: int = 200,
                      include_messages: bool = True) -> ConversationThread:
        thread_id = row["thread_id"]
        page = await self._message_page(db,thread_id,limit=message_limit)
        draft = await (await db.execute("SELECT draft_text FROM conversation_drafts WHERE thread_id=?",(thread_id,))).fetchone()
        followups = await (await db.execute("SELECT * FROM conversation_followups WHERE thread_id=? ORDER BY created_at_ms,followup_id",(thread_id,))).fetchall()
        return ConversationThread(thread_id=thread_id,title=row["title"],kind=ThreadKind(row["kind"]),
            status=ThreadStatus(row["status"]),project_id=row["project_id"],created_at_ms=row["created_at_ms"],
            updated_at_ms=row["updated_at_ms"],archived_at_ms=row["archived_at_ms"],
            draft_text="" if draft is None else draft["draft_text"],
            messages=page.messages if include_messages else [],
            message_count=page.total_count,messages_has_more=page.has_more if include_messages else page.total_count>0,
            messages_next_before_id=page.next_before_message_id if include_messages else None,
            followups=[self._followup(item) for item in followups])

    async def get(self, thread_id: str, *, message_limit: int = 200) -> ConversationThread | None:
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            row = await (await db.execute("SELECT * FROM conversation_threads WHERE thread_id = ?",(thread_id,))).fetchone()
            return None if row is None else await self._thread(db,row,message_limit=message_limit)

    async def list(self, status: ThreadStatus | None = None, limit: int = 100) -> list[ConversationThread]:
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            where = "" if status is None else " WHERE status=?"
            params = [] if status is None else [status.value]
            rows = await (await db.execute(f"SELECT * FROM conversation_threads{where} ORDER BY kind,updated_at_ms DESC,thread_id LIMIT ?",
                tuple(params+[max(1,min(limit,500))]))).fetchall()
            return [await self._thread(db,row,message_limit=1,include_messages=False) for row in rows]

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

    @staticmethod
    async def _active_thread(db: Any, thread_id: str) -> Any:
        row = await (await db.execute("SELECT * FROM conversation_threads WHERE thread_id = ?",(thread_id,))).fetchone()
        if row is None:
            raise ConversationServiceError("THREAD_UNKNOWN")
        if row["status"] == ThreadStatus.ARCHIVED.value:
            raise ConversationServiceError("THREAD_ARCHIVED")
        return row

    async def save_draft(self, thread_id: str, text: str, *, now_ms: int | None = None) -> ConversationThread:
        now = int(time.time()*1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await (await db.execute("SELECT thread_id FROM conversation_threads WHERE thread_id=?",(thread_id,))).fetchone()
            if row is None:
                raise ConversationServiceError("THREAD_UNKNOWN")
            await db.execute("INSERT INTO conversation_drafts(thread_id,draft_text,updated_at_ms) VALUES(?,?,?) ON CONFLICT(thread_id) DO UPDATE SET draft_text=excluded.draft_text,updated_at_ms=excluded.updated_at_ms",(thread_id,text,now))
            await db.execute("UPDATE conversation_threads SET updated_at_ms=? WHERE thread_id=?",(now,thread_id))
            await db.commit()
        result = await self.get(thread_id)
        assert result is not None
        return result

    async def append_message(self, thread_id: str, *, role: str, body: str, command_id: str | None = None,
                             mission_id: str | None = None, artifact_refs: list[str] | None = None,
                             terminal: bool = False, now_ms: int | None = None) -> ConversationMessage:
        if role not in {"OWNER","VAN","SYSTEM"}:
            raise ConversationServiceError("MESSAGE_ROLE_INVALID")
        if not body.strip():
            raise ConversationServiceError("MESSAGE_BODY_REQUIRED")
        now = int(time.time()*1000) if now_ms is None else now_ms
        mid = "msg_"+uuid.uuid4().hex
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            await self._active_thread(db,thread_id)
            await db.execute("INSERT INTO conversation_messages(message_id,thread_id,role,body,command_id,mission_id,artifact_refs_json,terminal,created_at_ms) VALUES(?,?,?,?,?,?,?,?,?)",
                (mid,thread_id,role,body,command_id,mission_id,Store.dumps(artifact_refs or []),int(terminal),now))
            await db.execute("UPDATE conversation_threads SET updated_at_ms=? WHERE thread_id=?",(now,thread_id))
            await db.commit()
        return ConversationMessage(message_id=mid,thread_id=thread_id,role=role,body=body,command_id=command_id,
            mission_id=mission_id,artifact_refs=artifact_refs or [],terminal=terminal,created_at_ms=now)

    async def queue_followup(self, thread_id: str, prompt: str, *, now_ms: int | None = None) -> ConversationFollowUp:
        value = prompt.strip()
        if not value:
            raise ConversationServiceError("FOLLOWUP_PROMPT_REQUIRED")
        if len(value)>8000:
            raise ConversationServiceError("FOLLOWUP_PROMPT_TOO_LONG")
        now = int(time.time()*1000) if now_ms is None else now_ms
        fid = "fu_"+uuid.uuid4().hex
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            await self._active_thread(db,thread_id)
            await db.execute("INSERT INTO conversation_followups(followup_id,thread_id,prompt,status,command_id,created_at_ms,updated_at_ms) VALUES(?,?,?,'QUEUED',NULL,?,?)",(fid,thread_id,value,now,now))
            await db.execute("UPDATE conversation_threads SET updated_at_ms=? WHERE thread_id=?",(now,thread_id))
            await db.commit()
        return ConversationFollowUp(followup_id=fid,thread_id=thread_id,prompt=value,status=FollowUpStatus.QUEUED,
            command_id=None,created_at_ms=now,updated_at_ms=now)

    async def decide_followup(self, thread_id: str, followup_id: str, action: str, *,
                              command_id: str | None = None, now_ms: int | None = None) -> ConversationFollowUp:
        if action not in {"promote","dismiss"}:
            raise ConversationServiceError("FOLLOWUP_ACTION_INVALID")
        now = int(time.time()*1000) if now_ms is None else now_ms
        status = FollowUpStatus.PROMOTED if action=="promote" else FollowUpStatus.DISMISSED
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await (await db.execute("SELECT * FROM conversation_followups WHERE thread_id=? AND followup_id=?",(thread_id,followup_id))).fetchone()
            if row is None:
                raise ConversationServiceError("FOLLOWUP_UNKNOWN")
            if row["status"] != FollowUpStatus.QUEUED.value:
                raise ConversationServiceError("FOLLOWUP_ALREADY_DECIDED")
            await db.execute("UPDATE conversation_followups SET status=?,command_id=?,updated_at_ms=? WHERE followup_id=? AND thread_id=?",
                (status.value,command_id if status is FollowUpStatus.PROMOTED else None,now,followup_id,thread_id))
            await db.execute("UPDATE conversation_threads SET updated_at_ms=? WHERE thread_id=?",(now,thread_id))
            await db.commit()
        return ConversationFollowUp(followup_id=followup_id,thread_id=thread_id,prompt=row["prompt"],status=status,
            command_id=command_id if status is FollowUpStatus.PROMOTED else None,created_at_ms=row["created_at_ms"],updated_at_ms=now)

    async def append_projection(self, thread_id: str, *, projection_key: str, role: str, body: str,
                                command_id: str | None = None, mission_id: str | None = None,
                                artifact_refs: list[str] | None = None, terminal: bool = False,
                                now_ms: int | None = None) -> ConversationMessage:
        """Present canonical work in its original thread without dispatching it."""
        if not projection_key.strip():
            raise ConversationServiceError("MESSAGE_PROJECTION_KEY_REQUIRED")
        if role not in {"OWNER","VAN","SYSTEM"}:
            raise ConversationServiceError("MESSAGE_ROLE_INVALID")
        if not body.strip():
            raise ConversationServiceError("MESSAGE_BODY_REQUIRED")
        mid = "msgp_"+hashlib.sha256(projection_key.encode()).hexdigest()[:40]
        now = int(time.time()*1000) if now_ms is None else now_ms
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            existing = await (await db.execute("SELECT * FROM conversation_messages WHERE message_id=?",(mid,))).fetchone()
            if existing is not None:
                if (existing["thread_id"],existing["role"],existing["command_id"],existing["mission_id"]) != (thread_id,role,command_id,mission_id):
                    raise ConversationServiceError("MESSAGE_PROJECTION_SCOPE_CONFLICT")
                return self._message(existing)
            thread = await (await db.execute("SELECT thread_id FROM conversation_threads WHERE thread_id=?",(thread_id,))).fetchone()
            if thread is None:
                raise ConversationServiceError("THREAD_UNKNOWN")
            # Canonical terminal observations still belong in an archived original
            # thread. They cannot restore it or authorize another execution.
            await db.execute("INSERT INTO conversation_messages(message_id,thread_id,role,body,command_id,mission_id,artifact_refs_json,terminal,created_at_ms) VALUES(?,?,?,?,?,?,?,?,?)",
                (mid,thread_id,role,body.strip(),command_id,mission_id,Store.dumps(artifact_refs or []),int(terminal),now))
            await db.execute("UPDATE conversation_threads SET updated_at_ms=? WHERE thread_id=?",(now,thread_id))
            row = await (await db.execute("SELECT * FROM conversation_messages WHERE message_id=?",(mid,))).fetchone()
            await db.commit()
            return self._message(row)
