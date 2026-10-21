"""The authority broker for real stream and narrow CDP producer processes.

Producers authenticate with a scoped machine credential. A stream grant proves
possession of a connection capability, not possession of the owner's device key.
All effective session, profile and control authority is resolved from the store.
Pixels and per-input coordinates stay outside this broker.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
import uuid
from typing import Any

from van_gateway.browser.interactive_models import InteractiveSessionState
from van_gateway.browser.downloads import DownloadBroker, DownloadState, sanitise_name
from van_gateway.browser.interactive_service import InteractiveSessionService
from van_gateway.browser.stream_grants import StreamGrantService, StreamGrantVerifier
from van_gateway.storage.db import Store


class ProducerError(Exception):
    pass


def credential_principal(token: str) -> str:
    return hashlib.sha256(token.strip().encode()).hexdigest()


def parse_proxy_bindings(raw: str) -> dict[str, frozenset[str]]:
    """Non-secret credential fingerprints mapped to TLS peer names they may attest."""
    try:
        value = json.loads(raw or "{}")
        if not isinstance(value, dict):
            raise ValueError
        result = {}
        for principal, callers in value.items():
            if not re.fullmatch(r"[0-9a-f]{64}", principal):
                raise ValueError
            if not isinstance(callers, list) or not callers:
                raise ValueError
            if any(not isinstance(c, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", c) for c in callers):
                raise ValueError
            result[principal] = frozenset(callers)
        return result
    except (ValueError, TypeError) as exc:
        raise ProducerError("browser_control_proxy_bindings_invalid") from exc


class BrowserProducerService:
    def __init__(self, *, store: Store, sessions: InteractiveSessionService,
                 grants: StreamGrantService, control_proxy_bindings: str = "{}") -> None:
        self.store = store
        self.sessions = sessions
        self.grants = grants
        self.verifier = StreamGrantVerifier({grants.signer.key.kid: grants.signer.key.public_pem()})
        self.proxy_bindings = parse_proxy_bindings(control_proxy_bindings)
        self.downloads = DownloadBroker(store)

    @staticmethod
    def _now(now_ms: int | None) -> int:
        return int(time.time() * 1000) if now_ms is None else now_ms

    @staticmethod
    async def _one(db, sql: str, params=()):
        cur = await db.execute(sql, params)
        return await cur.fetchone()

    async def _live(self, db, session_id: str, now: int, *, binding=None):
        session = await self._one(db, "SELECT * FROM browser_interactive_sessions WHERE session_id=?", (session_id,))
        if session is None:
            raise ProducerError("interactive_session_unknown")
        if session["state"] in {"TERMINATING", "TERMINATED", "FAILED"}:
            raise ProducerError("interactive_session_ended")
        if int(session["expires_at_ms"]) <= now:
            raise ProducerError("interactive_session_expired")
        device = await self._one(db, "SELECT revoked_at_unix FROM devices WHERE device_id=?", (session["owner_device_id"],))
        if device is None or device["revoked_at_unix"] is not None:
            raise ProducerError("stream_owner_device_not_active")
        device_binding = await self._one(db, "SELECT status,revoked_at_ms FROM owner_device_bindings WHERE device_id=?", (session["owner_device_id"],))
        if device_binding is not None and (device_binding["status"] != "ACTIVE" or device_binding["revoked_at_ms"] is not None):
            raise ProducerError("stream_owner_device_binding_not_active")
        profile = await self._one(db, "SELECT * FROM browser_profiles WHERE profile_alias=?", (session["profile_alias"],))
        if (profile is None or profile["lease_holder"] != session["profile_lease_id"]
                or profile["lease_holder_kind"] != "INTERACTIVE_SESSION"
                or profile["lease_holder_id"] != session_id):
            raise ProducerError("browser_profile_lease_lost")
        if int(profile["lease_expires_at_ms"] or 0) <= now:
            raise ProducerError("browser_profile_lease_expired")
        if binding is not None and (binding["profile_lease_id"] != profile["lease_holder"]
                or int(binding["profile_generation"]) != int(profile["lease_generation"])):
            raise ProducerError("browser_profile_generation_stale")
        return session, profile

    async def _stream_binding(self, db, producer_id: str, principal: str, now: int):
        row = await self._one(db, "SELECT p.*,g.revoked_at_ms AS grant_revoked_at_ms,g.scope_json,g.device_id,g.profile_alias "
                              "FROM browser_stream_producers p JOIN browser_stream_grants g USING(grant_id) "
                              "WHERE p.producer_session_id=? AND p.producer_principal_sha256=?", (producer_id, principal))
        if row is None:
            raise ProducerError("stream_producer_unknown")
        if row["revoked_at_ms"] is not None or row["grant_revoked_at_ms"] is not None:
            raise ProducerError("stream_producer_revoked")
        session, profile = await self._live(db, row["session_id"], now, binding=row)
        if row["device_id"] != session["owner_device_id"] or row["profile_alias"] != session["profile_alias"]:
            raise ProducerError("stream_grant_binding_mismatch")
        return row, session, profile

    async def _authority(self, db, session, profile, binding=None) -> dict[str, Any]:
        control = await self._one(db, "SELECT * FROM browser_control_leases WHERE session_id=? ORDER BY generation DESC LIMIT 1", (session["session_id"],))
        deletion_requests = []
        if binding is not None:
            cur = await db.execute("SELECT download_id,producer_session_id,target_id FROM browser_downloads WHERE session_id=? AND state='DELETED' AND producer_session_id IS NOT NULL AND host_deleted_at_ms IS NULL ORDER BY created_at_ms LIMIT 128", (session["session_id"],))
            deletion_requests = [{"download_id": r["download_id"], "artifact_producer_session_id": r["producer_session_id"], "target_id": r["target_id"]} for r in await cur.fetchall()]
        return {
            "session_id": session["session_id"], "profile_alias": session["profile_alias"],
            "profile_lease_id": profile["lease_holder"], "profile_generation": int(profile["lease_generation"]),
            "profile_expires_at_ms": profile["lease_expires_at_ms"],
            "control_lease_id": None if control is None else control["control_lease_id"],
            "control_generation": 0 if control is None else int(control["generation"]),
            "control_holder": "NONE" if control is None or control["revoked_at_ms"] is not None else control["holder"],
            "control_issued_for": None if control is None else control["issued_for"],
            "control_expires_at_ms": None if control is None else control["expires_at_ms"],
            "control_revoked_at_ms": None if control is None else control["revoked_at_ms"],
            "viewport": {"width": session["viewport_width"], "height": session["viewport_height"],
                         "device_scale_factor": session["device_scale_factor"], "revision": session["viewport_revision"]},
            "acked_viewport_revision": session["acked_viewport_revision"], "state": session["state"],
            "acked_media_epoch": session["acked_media_epoch"],
            "acked_frame_sequence": session["acked_frame_sequence"],
            "expires_at_ms": session["expires_at_ms"], "active_target_id": session["active_target_id"],
            "media_epoch": None if binding is None else binding["producer_session_id"],
            "observed_viewport_revision": None if binding is None else binding["observed_viewport_revision"],
            "observed_frame_sequence": 0 if binding is None else binding["observed_frame_sequence"],
            "pending_chooser_id": None if binding is None else binding["pending_chooser_id"],
            "pending_chooser_target_id": None if binding is None else binding["pending_chooser_target_id"],
            "download_deletion_requests": deletion_requests,
        }

    async def redeem(self, *, stream_grant: str, producer_session_id: str,
                     principal: str, now_ms: int | None = None) -> dict[str, Any]:
        now = self._now(now_ms)
        claims = self.verifier.verify(stream_grant, now_ms=now)
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", producer_session_id):
            raise ProducerError("stream_producer_id_invalid")
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await self._one(db, "SELECT * FROM browser_stream_grants WHERE grant_id=?", (claims.get("grant_id"),))
            if row is None:
                raise ProducerError("stream_grant_unknown")
            exact = {"grant_id": row["grant_id"], "session_id": row["session_id"], "device_id": row["device_id"],
                     "kid": row["kid"], "profile_alias": row["profile_alias"], "scope": json.loads(row["scope_json"]),
                     "nonce": row["nonce"], "issued_at_ms": row["issued_at_ms"], "expires_at_ms": row["expires_at_ms"]}
            if any(claims.get(k) != v for k, v in exact.items()):
                raise ProducerError("stream_grant_binding_mismatch")
            if row["redeemed_at_ms"] is not None or row["revoked_at_ms"] is not None or int(row["expires_at_ms"]) <= now:
                raise ProducerError("stream_grant_not_redeemable")
            if not {"webrtc.signal", "browser.view"}.issubset(exact["scope"]):
                raise ProducerError("stream_grant_view_scope_required")
            session, profile = await self._live(db, row["session_id"], now)
            if row["device_id"] != session["owner_device_id"] or row["profile_alias"] != session["profile_alias"]:
                raise ProducerError("stream_grant_binding_mismatch")
            if (int(claims.get("max_width", 0)) != int(session["viewport_width"])
                    or int(claims.get("max_height", 0)) != int(session["viewport_height"])
                    or int(claims.get("max_fps", 0)) != int(session["requested_fps"])):
                raise ProducerError("stream_grant_viewport_stale")
            if await self._one(db, "SELECT 1 FROM browser_stream_producers WHERE producer_session_id=?", (producer_session_id,)):
                raise ProducerError("stream_producer_id_reused")
            await db.execute("UPDATE browser_stream_grants SET redeemed_at_ms=? WHERE grant_id=?", (now, row["grant_id"]))
            await db.execute("UPDATE browser_stream_producers SET revoked_at_ms=?,revoke_reason='replaced' WHERE session_id=? AND revoked_at_ms IS NULL", (now, session["session_id"]))
            await db.execute("INSERT INTO browser_stream_producers(producer_session_id,grant_id,session_id,producer_principal_sha256,profile_lease_id,profile_generation,created_at_ms) VALUES(?,?,?,?,?,?,?)",
                             (producer_session_id, row["grant_id"], session["session_id"], principal, profile["lease_holder"], profile["lease_generation"], now))
            binding = await self._one(db, "SELECT * FROM browser_stream_producers WHERE producer_session_id=?", (producer_session_id,))
            authority = await self._authority(db, session, profile, binding)
            await db.commit()
        return {"producer_session_id": producer_session_id, "grant_id": row["grant_id"],
                "session_id": session["session_id"], "owner_device_id": session["owner_device_id"],
                "profile_alias": session["profile_alias"], "scopes": exact["scope"],
                "grant_expires_at_ms": row["expires_at_ms"], "authority": authority,
                "authenticated_principal_kind": "STREAM_GRANT_BEARER"}

    async def authority(self, *, producer_session_id: str, principal: str,
                        now_ms: int | None = None) -> dict[str, Any]:
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            row, session, profile = await self._stream_binding(db, producer_session_id, principal, self._now(now_ms))
            return await self._authority(db, session, profile, row)

    async def authorize_input(self, *, producer_session_id: str, principal: str,
                              session_id: str, control_lease_id: str, control_generation: int,
                              viewport_revision: int, now_ms: int | None = None) -> dict[str, Any]:
        now = self._now(now_ms)
        # Invoke the shared full actuation gate, then repeat its live checks inside a
        # single snapshot alongside producer binding and authenticated subject checks.
        await self.sessions.assert_may_actuate(session_id=session_id, control_lease_id=control_lease_id,
            control_generation=control_generation, viewport_revision=viewport_revision, now_ms=now)
        async with self.store.connection() as db:
            await db.execute("BEGIN")
            row, session, profile = await self._stream_binding(db, producer_session_id, principal, now)
            if session_id != row["session_id"]:
                raise ProducerError("stream_input_session_mismatch")
            if "browser.owner_input" not in json.loads(row["scope_json"]):
                raise ProducerError("stream_input_scope_refused")
            await self._check_control(db, session, control_lease_id, control_generation, now,
                                      holder="OWNER", issued_for=session["owner_device_id"])
            if not InteractiveSessionState(session["state"]).can_actuate:
                raise ProducerError("interactive_session_not_actuatable")
            if viewport_revision != int(session["viewport_revision"]):
                raise ProducerError("interactive_viewport_revision_stale")
            if session["acked_viewport_revision"] != viewport_revision:
                raise ProducerError("interactive_viewport_not_acknowledged")
            if session["acked_media_epoch"] != producer_session_id:
                raise ProducerError("stream_media_epoch_not_acknowledged")
            if row["observed_viewport_revision"] != viewport_revision:
                raise ProducerError("stream_viewport_frame_not_observed")
            return await self._authority(db, session, profile, row)

    async def _check_control(self, db, session, lease_id, generation, now, *, holder=None, issued_for=None):
        control = await self._one(db, "SELECT * FROM browser_control_leases WHERE session_id=? ORDER BY generation DESC LIMIT 1", (session["session_id"],))
        if control is None or control["control_lease_id"] != lease_id:
            raise ProducerError("control_lease_superseded")
        if int(control["generation"]) != generation or session["control_generation"] != generation:
            raise ProducerError("control_generation_stale")
        if control["revoked_at_ms"] is not None:
            raise ProducerError("control_lease_revoked")
        if int(control["expires_at_ms"]) <= now:
            raise ProducerError("control_lease_expired")
        if (holder is not None and control["holder"] != holder) or (issued_for is not None and control["issued_for"] != issued_for):
            raise ProducerError("control_lease_subject_refused")
        if session["control_holder"] != control["holder"] or session["control_lease_id"] != lease_id:
            raise ProducerError("control_lease_session_mismatch")
        return control

    async def observe(self, *, producer_session_id: str, principal: str, event: str,
                      now_ms: int | None = None, **data: Any) -> dict[str, Any]:
        now = self._now(now_ms)
        authority = await self.authority(producer_session_id=producer_session_id, principal=principal, now_ms=now)
        sid = authority["session_id"]
        transitions = {"allocated": "ALLOCATING", "signaling": "SIGNALING", "connecting": "CONNECTING",
                       "reconnecting": "RECONNECTING", "failed": "FAILED"}
        if event in transitions:
            await self.sessions.transition(session_id=sid, target=InteractiveSessionState(transitions[event]), reason=data.get("reason"), now_ms=now)
        elif event == "first_frame":
            viewport = authority["viewport"]
            if (data.get("media_epoch") != producer_session_id or data.get("viewport_revision") != viewport["revision"]
                    or data.get("width") != viewport["width"] or data.get("height") != viewport["height"]):
                raise ProducerError("stream_frame_viewport_mismatch")
            if not isinstance(data.get("frame_sequence"), int) or data["frame_sequence"] <= 0:
                raise ProducerError("stream_frame_sequence_invalid")
            if authority["state"] not in {"CONNECTING", "RECONNECTING", "INTERACTIVE", "AGENT_CONTROLLED"}:
                raise ProducerError("stream_frame_state_refused")
            async with self.store.connection() as db:
                await db.execute("BEGIN IMMEDIATE")
                row, session, profile = await self._stream_binding(db, producer_session_id, principal, now)
                if (session["viewport_revision"] != data["viewport_revision"]
                        or session["viewport_width"] != data["width"] or session["viewport_height"] != data["height"]):
                    raise ProducerError("stream_frame_viewport_mismatch")
                if data["frame_sequence"] <= int(row["observed_frame_sequence"]):
                    raise ProducerError("stream_frame_sequence_stale")
                await db.execute("UPDATE browser_stream_producers SET observed_viewport_revision=?,observed_frame_sequence=?,observed_at_ms=? WHERE producer_session_id=?",
                                 (data["viewport_revision"], data["frame_sequence"], now, producer_session_id))
                await db.execute("UPDATE browser_interactive_sessions SET negotiated_codec=?,negotiated_transport=? WHERE session_id=?", (data.get("codec"), data.get("transport"), sid))
                await db.commit()
            if authority["state"] in {"CONNECTING", "RECONNECTING"}:
                await self.sessions.transition(session_id=sid, target=InteractiveSessionState.INTERACTIVE, reason="producer_first_frame", now_ms=now)
                current = await self.sessions.get(sid)
                if current is not None and current.control_holder.is_agent:
                    await self.sessions.transition(session_id=sid, target=InteractiveSessionState.AGENT_CONTROLLED, reason="producer_agent_reconnected", now_ms=now)
        elif event == "target":
            if not data.get("target_id") or not data.get("url"):
                raise ProducerError("stream_target_observation_invalid")
            await self.sessions.record_active_url(session_id=sid, target_id=data["target_id"], url=data["url"], title=data.get("title"), now_ms=now)
            from urllib.parse import urlsplit
            parsed = urlsplit(data["url"])
            current = await self.sessions.get(sid)
            if current is not None and current.active_target_id == data["target_id"]:
                origin = {"producer_session_id": producer_session_id, "scheme": parsed.scheme,
                    "hostname": (parsed.hostname or "").lower(), "url_digest": current.active_url_digest,
                    "observed_at_ms": now, "source": "AUTHENTICATED_NATIVE_TARGET_OBSERVATION"}
                await self.store.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at_unix_ms=excluded.updated_at_unix_ms",
                    ("browser_target_origin:"+sid+":"+data["target_id"], Store.dumps(origin), now))
        elif event == "target_closed":
            await self.store.execute("UPDATE browser_session_targets SET closed_at_ms=?,is_active=0 WHERE session_id=? AND target_id=?", (now, sid, data.get("target_id")))
            await self.store.execute("UPDATE browser_interactive_sessions SET active_target_id=NULL,active_url_digest=NULL WHERE session_id=? AND active_target_id=?", (sid, data.get("target_id")))
            await self.sessions.record_event(session_id=sid, event_type="session.target_closed", severity="INFO", summary="Browser tab closed", payload={"target_id": data.get("target_id")}, now_ms=now)
        elif event == "closed":
            # Transport closure is a reconnect, never proof the owner's task succeeded.
            if authority["state"] in {"CONNECTING", "INTERACTIVE", "AGENT_CONTROLLED"}:
                await self.sessions.transition(session_id=sid, target=InteractiveSessionState.RECONNECTING, reason=data.get("reason") or "producer_disconnected", now_ms=now)
            await self.store.execute("UPDATE browser_stream_producers SET revoked_at_ms=?,revoke_reason='closed' WHERE producer_session_id=?", (now, producer_session_id))
            return {"producer_session_id": producer_session_id, "state": "CLOSED", "is_work_outcome": False}
        else:
            raise ProducerError("stream_observation_event_unknown")
        if event == "failed":
            return {"producer_session_id": producer_session_id, "state": "FAILED", "is_work_outcome": False}
        return await self.authority(producer_session_id=producer_session_id, principal=principal, now_ms=now)

    async def acknowledge_frame(self, *, session_id: str, revision: int,
                                frame_sequence: int | None, media_epoch: str | None,
                                now_ms: int | None = None) -> bool:
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await self._one(db, "SELECT * FROM browser_stream_producers WHERE session_id=? AND revoked_at_ms IS NULL", (session_id,))
            if row is None:
                historical = await self._one(db, "SELECT 1 FROM browser_stream_producers WHERE session_id=?", (session_id,))
                if historical is not None or media_epoch is not None or frame_sequence is not None:
                    raise ProducerError("stream_frame_ack_producer_absent")
                return False  # independently testable legacy service, without a producer
            row, session, _ = await self._stream_binding(db, row["producer_session_id"], row["producer_principal_sha256"], self._now(now_ms))
            if (media_epoch != row["producer_session_id"] or frame_sequence is None
                    or frame_sequence <= 0 or frame_sequence > int(row["observed_frame_sequence"])
                    or revision != row["observed_viewport_revision"] or revision != session["viewport_revision"]):
                raise ProducerError("stream_frame_ack_not_observed")
            await db.execute("UPDATE browser_interactive_sessions SET acked_viewport_revision=?,acked_media_epoch=?,acked_frame_sequence=? WHERE session_id=?", (revision, media_epoch, frame_sequence, session_id))
            await db.commit()
        return True

    async def _task_binding(self, db, session, task_id: str):
        task = await self._one(db, "SELECT * FROM browser_tasks WHERE task_id=?", (task_id,))
        if task is None or task["profile_alias"] != session["profile_alias"]:
            raise ProducerError("control_task_unknown")
        if task["status"] not in {"PENDING", "LEASED", "RUNNING", "RESUME_AUTHORIZED"}:
            raise ProducerError("control_task_not_active")
        if not session["mission_id"]:
            raise ProducerError("control_task_mission_required")
        mission = await self._one(db, "SELECT state FROM missions WHERE mission_id=?", (session["mission_id"],))
        if mission is None or mission["state"] not in {"CAPTURED", "UNDERSTOOD", "PLANNED", "AUTHORIZED", "RUNNING", "RESUME_AUTHORIZED"}:
            raise ProducerError("control_task_mission_not_active")
        activity = await self._one(db, "SELECT 1 FROM mission_activities WHERE mission_id=? AND executor_ref=? AND executor='BROWSER_FABRIC'", (session["mission_id"], task_id))
        if activity is None:
            raise ProducerError("control_task_mission_mismatch")
        return task

    async def register_chooser(self, *, producer_session_id: str, principal: str,
                               chooser_id: str, target_id: str, now_ms: int | None = None):
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            row, session, _ = await self._stream_binding(db, producer_session_id, principal, self._now(now_ms))
            if target_id != session["active_target_id"]:
                raise ProducerError("control_target_not_bound")
            await db.execute("UPDATE browser_stream_producers SET pending_chooser_id=?,pending_chooser_target_id=? WHERE producer_session_id=?", (chooser_id, target_id, producer_session_id))
            await db.commit()
        return {"chooser_id": chooser_id, "target_id": target_id, "session_id": row["session_id"]}

    async def report_download(self, *, producer_session_id: str, principal: str,
                              event: str, download_id: str, target_id: str,
                              now_ms: int | None = None, **data):
        now = self._now(now_ms)
        authority = await self.authority(producer_session_id=producer_session_id, principal=principal, now_ms=now)
        if event == "started":
            target = await self.store.fetchone("SELECT 1 FROM browser_session_targets WHERE session_id=? AND target_id=? AND closed_at_ms IS NULL", (authority["session_id"], target_id))
            if target is None:
                raise ProducerError("download_target_not_bound")
            if not data.get("suggested_name") or not re.fullmatch(r"[0-9a-f]{64}", data.get("url_digest", "")):
                raise ProducerError("download_started_metadata_invalid")
            await self.downloads.create(download_id=download_id, session_id=authority["session_id"], target_id=target_id,
                suggested_name=data["suggested_name"], declared_mime=data.get("declared_mime"), url_digest=data["url_digest"], now_ms=now)
            await self.store.execute("UPDATE browser_downloads SET producer_session_id=? WHERE download_id=?", (producer_session_id, download_id))
            await self.downloads.start(download_id)
            await self.sessions.record_event(session_id=authority["session_id"], event_type="session.download_created", severity="INFO", summary="Browser download started", payload={"download_id": download_id}, now_ms=now)
        else:
            row = await self.store.fetchone("SELECT * FROM browser_downloads WHERE download_id=?", (download_id,))
            if row is None or row["session_id"] != authority["session_id"] or row["target_id"] != target_id or (event != "deleted" and row["producer_session_id"] != producer_session_id):
                raise ProducerError("download_producer_binding_mismatch")
            if event == "finished":
                if not isinstance(data.get("byte_size"), int) or not 0 <= data["byte_size"] <= 64 * 1024 * 1024:
                    raise ProducerError("download_size_limit_exceeded")
                await self.downloads.finish(download_id=download_id, byte_size=data["byte_size"], content_sha256=data.get("content_sha256", ""), observed_mime=data.get("observed_mime"), now_ms=now)
                await self.sessions.record_event(session_id=authority["session_id"], event_type="session.download_completed", severity="INFO", summary="Browser download classified", payload={"download_id": download_id}, now_ms=now)
            elif event == "failed":
                await self.downloads.fail(download_id, data.get("reason") or "host_download_failed", now_ms=now)
            elif event == "deleted":
                if row["state"] != "DELETED":
                    raise ProducerError("download_delete_not_requested")
                await self.store.execute("UPDATE browser_downloads SET host_deleted_at_ms=? WHERE download_id=?", (now, download_id))
            else:
                raise ProducerError("download_report_event_unknown")
        row = await self.store.fetchone("SELECT * FROM browser_downloads WHERE download_id=?", (download_id,))
        return {"download_id": download_id, "session_id": row["session_id"], "target_id": target_id,
                "state": row["state"], "suggested_name": row["suggested_name"],
                "byte_size": row["byte_size"], "content_sha256": row["content_sha256"],
                "mime_type": row["mime_type"], "actions": [a.value for a in await self.downloads.actions_for(download_id)]}

    async def issue_transfer_grant(self, *, session_id: str, owner_device_id: str,
                                   operation: str, target_id: str, now_ms: int | None = None,
                                   download_id: str | None = None, chooser_id: str | None = None,
                                   byte_size: int | None = None, content_sha256: str | None = None,
                                   suggested_name: str | None = None, mime_type: str | None = None):
        now = self._now(now_ms)
        token = secrets.token_urlsafe(32)
        transfer_id = f"botg_{uuid.uuid4().hex}"
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            row = await self._one(db, "SELECT * FROM browser_stream_producers WHERE session_id=? AND revoked_at_ms IS NULL", (session_id,))
            if row is None:
                raise ProducerError("stream_producer_unknown")
            row, session, profile = await self._stream_binding(db, row["producer_session_id"], row["producer_principal_sha256"], now)
            if session["owner_device_id"] != owner_device_id:
                raise ProducerError("interactive_session_unknown")
            await self._check_control(db, session, session["control_lease_id"], session["control_generation"], now, holder="OWNER", issued_for=owner_device_id)
            if (not InteractiveSessionState(session["state"]).can_actuate or session["acked_media_epoch"] != row["producer_session_id"]
                    or session["acked_viewport_revision"] != session["viewport_revision"] or row["observed_viewport_revision"] != session["viewport_revision"]):
                raise ProducerError("transfer_current_frame_required")
            if operation not in {"download", "analyse"} and target_id != session["active_target_id"]:
                raise ProducerError("control_target_not_bound")
            metadata = {"target_id": target_id}
            if operation in {"upload", "paste", "file_import"} and "browser.owner_input" not in json.loads(row["scope_json"]):
                raise ProducerError("transfer_owner_input_scope_required")
            if operation in {"download", "analyse"}:
                download = await self._one(db, "SELECT * FROM browser_downloads WHERE download_id=? AND session_id=? AND target_id=?", (download_id, session_id, target_id))
                if (download is None or (download["state"] not in ({"COMPLETED", "QUARANTINED"} if operation == "analyse" else {"COMPLETED"})) or (operation != "analyse" and download["failure_reason"])
                        or download["producer_session_id"] is None or download["byte_size"] is None or int(download["byte_size"]) > 64 * 1024 * 1024):
                    raise ProducerError("download_transfer_not_permitted")
                resource_id = download_id
                metadata.update(byte_size=download["byte_size"], content_sha256=download["content_sha256"],
                    suggested_name=download["suggested_name"], mime_type=download["mime_type"],
                    state=download["state"], artifact_producer_session_id=download["producer_session_id"])
            elif operation in {"upload", "paste", "file_import"}:
                limit = 64 * 1024 * 1024 if operation in {"upload", "file_import"} else 64 * 1024
                if (not isinstance(byte_size, int) or isinstance(byte_size, bool) or not 0 <= byte_size <= limit
                        or not isinstance(content_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", content_sha256) is None):
                    raise ProducerError("transfer_file_metadata_invalid")
                resource_id = ("import_" + uuid.uuid4().hex) if operation == "file_import" else (chooser_id if operation == "upload" else target_id)
                if operation == "upload" and (not chooser_id or chooser_id != row["pending_chooser_id"] or target_id != row["pending_chooser_target_id"]):
                    raise ProducerError("upload_chooser_not_current")
                metadata.update(byte_size=byte_size, content_sha256=content_sha256)
                if operation in {"upload", "file_import"}:
                    metadata.update(suggested_name=sanitise_name(suggested_name or "upload.bin"), mime_type=mime_type)
            elif operation == "copy":
                resource_id = target_id
                metadata.update(max_byte_size=64 * 1024)
            else:
                raise ProducerError("transfer_operation_unknown")
            await db.execute("INSERT INTO browser_owner_transfer_grants(transfer_id,token_sha256,producer_session_id,session_id,owner_device_id,operation,resource_id,target_id,profile_lease_id,profile_generation,control_lease_id,control_generation,viewport_revision,metadata_json,created_at_ms,expires_at_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (transfer_id, hashlib.sha256(token.encode()).hexdigest(), row["producer_session_id"], session_id, owner_device_id,
                 operation, resource_id, target_id, profile["lease_holder"], profile["lease_generation"], session["control_lease_id"],
                 session["control_generation"], session["viewport_revision"], Store.dumps(metadata), now, now + 60_000))
            await db.commit()
        return {"transfer_grant": token, "transfer_id": transfer_id, "expires_at_ms": now + 60_000,
                "producer_session_id": row["producer_session_id"], "session_id": session_id,
                "operation": operation, "resource_id": resource_id, **metadata}

    async def consume_transfer_grant(self, *, producer_session_id: str, principal: str,
                                     transfer_grant: str, operation: str, resource_id: str,
                                     content_sha256: str | None = None, byte_size: int | None = None,
                                     now_ms: int | None = None):
        now = self._now(now_ms)
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            producer, session, profile = await self._stream_binding(db, producer_session_id, principal, now)
            row = await self._one(db, "SELECT * FROM browser_owner_transfer_grants WHERE token_sha256=? AND producer_session_id=?", (hashlib.sha256(transfer_grant.encode()).hexdigest(), producer_session_id))
            if row is None:
                raise ProducerError("transfer_grant_unknown")
            if row["consumed_at_ms"] is not None or row["expires_at_ms"] <= now:
                raise ProducerError("transfer_grant_expired_or_consumed")
            if operation != row["operation"] or resource_id != row["resource_id"]:
                raise ProducerError("transfer_grant_resource_mismatch")
            if (row["owner_device_id"] != session["owner_device_id"] or row["profile_lease_id"] != profile["lease_holder"]
                    or row["profile_generation"] != profile["lease_generation"] or row["viewport_revision"] != session["viewport_revision"]):
                raise ProducerError("transfer_grant_authority_stale")
            await self._check_control(db, session, row["control_lease_id"], row["control_generation"], now, holder="OWNER", issued_for=row["owner_device_id"])
            if ((operation not in {"download", "analyse"} and row["target_id"] != session["active_target_id"]) or session["acked_media_epoch"] != producer_session_id
                    or session["acked_viewport_revision"] != row["viewport_revision"] or not InteractiveSessionState(session["state"]).can_actuate):
                raise ProducerError("transfer_grant_authority_stale")
            metadata = json.loads(row["metadata_json"])
            if operation in {"upload", "paste", "file_import"} and (content_sha256 != metadata["content_sha256"] or byte_size != metadata["byte_size"]):
                raise ProducerError("transfer_content_mismatch")
            if operation == "upload":
                if producer["pending_chooser_id"] != resource_id or producer["pending_chooser_target_id"] != row["target_id"]:
                    raise ProducerError("upload_chooser_not_current")
                await db.execute("UPDATE browser_stream_producers SET pending_chooser_id=NULL,pending_chooser_target_id=NULL WHERE producer_session_id=?", (producer_session_id,))
            if operation in {"download", "analyse"}:
                download = await self._one(db, "SELECT * FROM browser_downloads WHERE download_id=?", (resource_id,))
                if (download is None or (download["state"] not in ({"COMPLETED", "QUARANTINED"} if operation == "analyse" else {"COMPLETED"})) or (operation != "analyse" and download["failure_reason"])
                        or download["session_id"] != row["session_id"] or download["target_id"] != row["target_id"]
                        or download["content_sha256"] != metadata["content_sha256"] or download["byte_size"] != metadata["byte_size"]):
                    raise ProducerError("download_transfer_not_permitted")
            await db.execute("UPDATE browser_owner_transfer_grants SET consumed_at_ms=? WHERE transfer_id=?", (now, row["transfer_id"]))
            authority = await self._authority(db, session, profile, producer)
            await db.commit()
        return {"operation": operation, "resource_id": resource_id, "session_id": session["session_id"],
                "producer_session_id": producer_session_id, "transfer_id": row["transfer_id"], **metadata, "authority": authority,
                "authenticated_principal_kind": "OWNER_AUTHORIZED_ONE_USE_TRANSFER_GRANT"}

    async def report_file_result(self, *, producer_session_id, principal, transfer_id,
                                 operation, resource_id, receipt, now_ms=None):
        now = self._now(now_ms)
        if operation != "analyse" or not isinstance(receipt, dict):
            raise ProducerError("file_result_operation_refused")
        fields = {"download_id", "byte_size", "content_sha256", "observed_mime", "analysis_kind",
                  "content_authority", "executed_content", "truncated", "text_preview",
                  "preview_line_count", "analysis_sha256"}
        if (set(receipt) - fields or "text_preview" in receipt or receipt.get("executed_content") is not False
            or receipt.get("content_authority") != "UNTRUSTED_FILE_EVIDENCE"
            or receipt.get("analysis_kind") != "BOUNDED_STATIC_INSPECTION"
            or not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("analysis_sha256", "")))):
            raise ProducerError("file_result_receipt_invalid")
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            producer, session, profile = await self._stream_binding(db, producer_session_id, principal, now)
            row = await self._one(db, "SELECT * FROM browser_owner_transfer_grants WHERE transfer_id=? AND producer_session_id=?", (transfer_id, producer_session_id))
            if row is None or row["operation"] != operation or row["resource_id"] != resource_id or row["consumed_at_ms"] is None:
                raise ProducerError("file_result_grant_not_consumed")
            metadata = json.loads(row["metadata_json"])
            if (receipt.get("download_id") != resource_id or receipt.get("byte_size") != metadata["byte_size"]
                or receipt.get("content_sha256") != metadata["content_sha256"]):
                raise ProducerError("file_result_content_mismatch")
            await self._check_control(db, session, row["control_lease_id"], row["control_generation"], now, holder="OWNER", issued_for=row["owner_device_id"])
            if (row["profile_lease_id"] != profile["lease_holder"] or row["profile_generation"] != profile["lease_generation"]
                or row["expires_at_ms"] <= now or row["viewport_revision"] != session["viewport_revision"]):
                raise ProducerError("file_result_authority_stale")
            result = {"transfer_id": transfer_id, "session_id": session["session_id"], "resource_id": resource_id,
                "operation": operation, "producer_session_id": producer_session_id,
                "status": "VERIFIED_SUCCESS", "receipt": receipt,
                "observation_source": "AUTHENTICATED_NATIVE_STATIC_INSPECTION", "observed_at_ms": now}
            key = "browser_file_operation:" + transfer_id
            old = await self._one(db, "SELECT value FROM runtime_meta WHERE key=?", (key,))
            if old:
                existing = json.loads(old["value"])
                if existing["receipt"] != receipt:
                    raise ProducerError("file_result_idempotency_conflict")
                return existing
            await db.execute("INSERT INTO runtime_meta(key,value,updated_at_unix_ms) VALUES(?,?,?)", (key, Store.dumps(result), now))
            await db.commit()
        return result

    async def issue_control_grant(self, *, task_id: str, session_id: str, target_id: str,
                                  caller_common_name: str, proxy_principal_sha256: str,
                                  scope: str, step_budget: int, deadline_ms: int,
                                  now_ms: int | None = None) -> dict[str, Any]:
        now = self._now(now_ms)
        if caller_common_name not in self.proxy_bindings.get(proxy_principal_sha256, frozenset()):
            raise ProducerError("control_proxy_caller_not_admitted")
        if scope not in {"browser.observe", "browser.actuate", "browser.evidence"} or not 1 <= step_budget <= 50:
            raise ProducerError("control_grant_bounds_invalid")
        if not now < deadline_ms <= now + 900_000:
            raise ProducerError("control_grant_deadline_invalid")
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE")
            session, profile = await self._live(db, session_id, now)
            task = await self._task_binding(db, session, task_id)
            if session["state"] != "AGENT_CONTROLLED" or session["control_holder"] not in {"HERMES_DETERMINISTIC", "HERMES_STAGEHAND"}:
                raise ProducerError("control_owner_delegation_required")
            control = await self._check_control(db, session, session["control_lease_id"], session["control_generation"], now, issued_for=caller_common_name)
            target = await self._one(db, "SELECT 1 FROM browser_session_targets WHERE session_id=? AND target_id=? AND closed_at_ms IS NULL", (session_id, target_id))
            if target is None or target_id != session["active_target_id"]:
                raise ProducerError("control_target_not_bound")
            if await self._one(db, "SELECT 1 FROM browser_control_producer_grants WHERE task_id=? AND session_id=? AND caller_common_name=?", (task_id, session_id, caller_common_name)):
                raise ProducerError("control_grant_already_issued")
            grant_id = f"bcpg_{uuid.uuid4().hex}"
            await db.execute("INSERT INTO browser_control_producer_grants(grant_id,task_id,session_id,target_id,proxy_principal_sha256,caller_common_name,scope,control_lease_id,control_generation,profile_lease_id,profile_generation,step_budget,deadline_ms,created_at_ms) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (grant_id, task_id, session_id, target_id, proxy_principal_sha256, caller_common_name, scope,
                 control["control_lease_id"], control["generation"], profile["lease_holder"], profile["lease_generation"], step_budget, deadline_ms, now))
            await db.commit()
        return {"grant_id": grant_id, "task_id": task_id, "session_id": session_id,
                "target_id": target_id, "caller_common_name": caller_common_name,
                "scope": scope, "step_budget": step_budget, "steps_remaining": step_budget,
                "deadline_ms": deadline_ms, "allowed_domains": [task["target_domain"]],
                "action_class": task["action_class"], "control_lease_id": control["control_lease_id"],
                "control_generation": control["generation"]}

    async def authorize_call(self, *, principal: str, caller_common_name: str, operation: str,
                             session_id: str, target_id: str, lease_id: str,
                             lease_generation: int, task_id: str, params: dict | None = None,
                             now_ms: int | None = None) -> dict[str, Any]:
        return await self._resolve_control_call(principal=principal, caller_common_name=caller_common_name,
            operation=operation, session_id=session_id, target_id=target_id, lease_id=lease_id,
            lease_generation=lease_generation, task_id=task_id, params=params, now_ms=now_ms, consume_step=True)

    async def validate_call(self, *, principal: str, caller_common_name: str, operation: str,
                            session_id: str, target_id: str, lease_id: str,
                            lease_generation: int, task_id: str, params: dict | None = None,
                            now_ms: int | None = None) -> dict[str, Any]:
        """Check current authority before observations without spending a task step."""
        return await self._resolve_control_call(principal=principal, caller_common_name=caller_common_name,
            operation=operation, session_id=session_id, target_id=target_id, lease_id=lease_id,
            lease_generation=lease_generation, task_id=task_id, params=params, now_ms=now_ms, consume_step=False)

    async def validate_result(self, *, principal: str, caller_common_name: str, operation: str,
                              session_id: str, target_id: str, lease_id: str,
                              lease_generation: int, task_id: str, params: dict | None = None,
                              now_ms: int | None = None) -> dict[str, Any]:
        """Fence a spent call's result; this neither admits nor pays for another call."""
        return await self._resolve_control_call(principal=principal, caller_common_name=caller_common_name,
            operation=operation, session_id=session_id, target_id=target_id, lease_id=lease_id,
            lease_generation=lease_generation, task_id=task_id, params=params, now_ms=now_ms,
            consume_step=False, result_validation=True)

    async def _resolve_control_call(self, *, principal: str, caller_common_name: str, operation: str,
                                    session_id: str, target_id: str, lease_id: str,
                                    lease_generation: int, task_id: str, consume_step: bool,
                                    now_ms: int | None = None, result_validation: bool = False, params: dict | None = None) -> dict[str, Any]:
        """Resolve one current proxy-attested call and optionally spend its step.

        This is explicitly a proxy attestation. The gateway does not claim it saw
        the caller certificate, and a stream credential cannot mint this grant.
        """
        if caller_common_name not in self.proxy_bindings.get(principal, frozenset()):
            raise ProducerError("control_proxy_caller_not_admitted")
        operations = {
            "browser.observe": {"attach", "query_dom", "query_accessibility", "observe_navigation", "observe_download"},
            # An actuator on a canonical Mission may also capture the evidence that
            # verifies its result. It spends the same immutable task budget.
            "browser.actuate": {"attach", "navigate", "dispatch_input", "query_dom", "query_accessibility", "observe_navigation", "observe_download", "capture_evidence", "click_element", "fill_element", "observe_effect"},
            "browser.evidence": {"attach", "query_dom", "query_accessibility", "observe_navigation", "capture_evidence"},
        }
        now = self._now(now_ms)
        async with self.store.connection() as db:
            await db.execute("BEGIN IMMEDIATE" if consume_step else "BEGIN")
            row = await self._one(db, "SELECT * FROM browser_control_producer_grants WHERE task_id=? AND session_id=? AND caller_common_name=? AND proxy_principal_sha256=?", (task_id, session_id, caller_common_name, principal))
            if row is None:
                raise ProducerError("control_grant_unknown")
            if row["revoked_at_ms"] is not None or int(row["deadline_ms"]) <= now:
                raise ProducerError("control_grant_expired_or_revoked")
            if operation not in operations[row["scope"]]:
                raise ProducerError("control_operation_out_of_scope")
            session, profile = await self._live(db, session_id, now, binding=row)
            task = await self._task_binding(db, session, task_id)
            # A scope name cannot turn a read task into a mutating browser task.
            # The current canonical task schema carries no immutable mutation or
            # domain-write admission. Owner input has its separate proved lease.
            if operation == "dispatch_input":
                raise ProducerError("control_task_mutation_admission_unavailable")
            if target_id != row["target_id"] or target_id != session["active_target_id"]:
                raise ProducerError("control_target_not_bound")
            target = await self._one(db, "SELECT 1 FROM browser_session_targets WHERE session_id=? AND target_id=? AND closed_at_ms IS NULL", (session_id, target_id))
            if target is None:
                raise ProducerError("control_target_not_bound")
            if lease_id != row["control_lease_id"] or lease_generation != row["control_generation"]:
                raise ProducerError("control_grant_lease_mismatch")
            await self._check_control(db, session, lease_id, lease_generation, now, issued_for=caller_common_name)
            if session["state"] != "AGENT_CONTROLLED" or session["control_holder"] not in {"HERMES_DETERMINISTIC", "HERMES_STAGEHAND"}:
                raise ProducerError("control_owner_delegation_required")
            if operation in {"attach", "navigate", "dispatch_input", "click_element", "fill_element"} and session["acked_viewport_revision"] != session["viewport_revision"]:
                raise ProducerError("interactive_viewport_not_acknowledged")
            if result_validation and row["steps_used"] < 1:
                raise ProducerError("control_result_has_no_authorized_step")
            if not result_validation and row["steps_used"] >= row["step_budget"]:
                raise ProducerError("control_step_budget_exhausted")
            planned = {}
            from van_gateway.mission.control import require_mission_dispatch
            from van_gateway.mission.control import MissionControlError
            try:
                await require_mission_dispatch(self.store, session["mission_id"], db=db)
            except MissionControlError as exc:
                raise ProducerError(exc.reason) from exc
            if operation in {"click_element", "fill_element", "observe_effect"}:
                plans = getattr(self, "action_plans", None)
                if plans is None:
                    raise ProducerError("control_task_mutation_admission_unavailable")
                from van_gateway.browser.action_plans import PlanError
                try:
                    planned = await plans.resolve_step(db, params=params or {}, operation=operation,
                        session=session, profile=profile, task_id=task_id, consume=consume_step,
                        result_validation=result_validation, now=now)
                except PlanError as exc:
                    raise ProducerError(str(exc)) from exc
            if consume_step:
                await db.execute("UPDATE browser_control_producer_grants SET steps_used=steps_used+1 WHERE grant_id=?", (row["grant_id"],))
            authority = await self._authority(db, session, profile)
            download_observation = {}
            if operation == "observe_download":
                # Only actual authenticated producer reports cross this surface.
                # Legacy metadata without producer provenance cannot become a
                # claimed native observation, and no file bytes are returned.
                cur = await db.execute("""SELECT d.download_id,d.session_id,d.target_id,
                    d.state,d.suggested_name,d.mime_type,d.byte_size,d.content_sha256,
                    d.producer_session_id,d.host_deleted_at_ms
                    FROM browser_downloads d JOIN browser_stream_producers p
                    ON p.producer_session_id=d.producer_session_id AND p.session_id=d.session_id
                    WHERE d.session_id=? AND d.target_id=?
                    ORDER BY d.created_at_ms DESC,d.download_id LIMIT 64""", (session_id, target_id))
                reports = [dict(report) for report in await cur.fetchall()]
                download_observation = {"observed_downloads": reports,
                    "observation_available": bool(reports), "complete_snapshot": False,
                    "observation_source": "AUTHENTICATED_STREAM_PRODUCER_REPORTS"}
            await db.commit()
        used = int(row["steps_used"]) + (1 if consume_step else 0)
        return {"task_id": task_id, "session_id": session_id, "target_id": target_id,
                "scope": row["scope"], "step_budget": row["step_budget"], "steps_used": used,
                "steps_remaining": int(row["step_budget"]) - used, "deadline_ms": row["deadline_ms"],
                "allowed_domains": [task["target_domain"]], "action_class": task["action_class"],
                "authority": authority, "authorization_consumed": consume_step,
                "result_validation": result_validation,
                "authenticated_principal_kind": "TRUSTED_PROXY_TLS_PEER_ATTESTATION",
                **download_observation, **planned}
