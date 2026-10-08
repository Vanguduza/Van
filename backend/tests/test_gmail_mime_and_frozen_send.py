"""Owner plain replies and approved sends exercise independent MIME/effect readback."""
from __future__ import annotations

import base64
import copy
import json
from email import policy
from email.parser import BytesParser

import httpx
import pytest
from cryptography.fernet import Fernet

from conftest_automation import enroll_device, make_action_runtime, make_store
from van_gateway.action.models import ExecutionStatus
from van_gateway.google.mail import encode_snapshot, message_snapshot
from van_gateway.google.service import GoogleAuthError, GoogleService
from van_gateway.google.transport import GoogleHttpTransport
from van_gateway.models import PrincipalType


def _thread():
    return {"id": "thread-1", "messages": [{
        "id": "incoming-1", "threadId": "thread-1", "internalDate": "1000", "labelIds": ["INBOX"],
        "payload": {"headers": [
            {"name": "From", "value": "Supplier <sender@example.invalid>"},
            {"name": "Reply-To", "value": "Orders <orders@example.invalid>"},
            {"name": "Subject", "value": "Delivery résumé"},
            {"name": "Message-ID", "value": "<message-1@example.invalid>"},
            {"name": "References", "value": "<previous@example.invalid>"},
        ]},
    }]}


def _decode(raw):
    return BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


class BoundHttpTransport(GoogleHttpTransport):
    requires_access_token = False


async def _runtime(tmp_path, client):
    store = await make_store(tmp_path)
    await enroll_device(store)
    actions = await make_action_runtime(store)
    google = GoogleService(store, Fernet.generate_key().decode(), BoundHttpTransport(client))
    await google.store_refresh_token("owner", "synthetic-token", ["https://www.googleapis.com/auth/gmail.compose", "https://www.googleapis.com/auth/gmail.send"])
    return store, actions, google


async def _begin(actions, action, parameters):
    return await actions.begin(
        execution_id="exec-gmail", command_id="cmd-gmail", turn_id="turn-gmail",
        action_id=action, principal_type=PrincipalType.OWNER_DEVICE, requested_by="dev-owner-1",
        idempotency_key="gmail-effect", parameters=parameters, snapshot_id=None, owner_approved=True,
    )


async def test_plain_reply_uses_authoritative_thread_and_independent_decoded_readback(tmp_path):
    seen, state = [], {}
    owner_body = "Please deliver on Friday.\r\nThank you, Zoë."

    def handler(request):
        seen.append((request.method, request.url.path))
        if request.url.path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": "owner@example.invalid"})
        if "/threads/" in request.url.path:
            assert request.url.params["format"] == "metadata"
            assert "Reply-To" in request.url.params.get_list("metadataHeaders")
            return httpx.Response(200, json=_thread())
        if request.method == "POST":
            state["draft"] = {"id": "draft-1", **json.loads(request.content)}
            mime = _decode(state["draft"]["message"]["raw"])
            assert str(mime["From"]) == "owner@example.invalid"
            assert str(mime["To"]) == "orders@example.invalid"
            assert str(mime["Subject"]) == "Delivery résumé"
            assert str(mime["In-Reply-To"]) == "<message-1@example.invalid>"
            assert str(mime["References"]) == "<previous@example.invalid> <message-1@example.invalid>"
            assert mime.get_content() == "Please deliver on Friday.\r\nThank you, Zoë.\r\n"
            return httpx.Response(200, json=state["draft"])
        assert request.url.params["format"] == "raw"
        observed = copy.deepcopy(state["draft"])
        # Raw spelling may differ; the verification must compare decoded semantics.
        raw = observed["message"]["raw"]
        observed["message"]["raw"] = raw + "=" * (-len(raw) % 4)
        return httpx.Response(200, json=observed)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        _, actions, google = await _runtime(tmp_path, client)
        parameters = {"thread_id": "thread-1", "body": owner_body}
        execution = await _begin(actions, "google.gmail.draft", parameters)
        result = await google.execute_authorized_action(actions, execution_id=execution.execution_id, parameters=parameters)
    assert result["verification"]["status"] == "VERIFIED_SUCCESS"
    assert seen == [("GET", "/gmail/v1/users/me/profile"), ("GET", "/gmail/v1/users/me/threads/thread-1"),
                    ("POST", "/gmail/v1/users/me/drafts"), ("GET", "/gmail/v1/users/me/drafts/draft-1")]


@pytest.mark.parametrize("fault,reason", [
    ("missing", "gmail_reply_thread_metadata_missing"),
    ("ambiguous", "gmail_reply_address_ambiguous"),
    ("duplicate", "gmail_reply_header_ambiguous"),
    ("sent", "gmail_reply_target_not_incoming"),
    ("tied_latest", "gmail_reply_target_ambiguous"),
    ("wrong_thread", "gmail_reply_thread_mismatch"),
    ("invalid_payload", "gmail_reply_thread_metadata_missing"),
])
async def test_reply_refuses_missing_or_ambiguous_recipient_before_write(tmp_path, fault, reason):
    thread, methods = _thread(), []
    source = thread["messages"][0]
    if fault == "missing":
        source["payload"]["headers"] = []
    elif fault == "ambiguous":
        source["payload"]["headers"][1]["value"] = "one@example.invalid, two@example.invalid"
    elif fault == "duplicate":
        source["payload"]["headers"].append({"name": "Reply-To", "value": "other@example.invalid"})
    elif fault == "sent":
        source["labelIds"] = ["SENT"]
    elif fault == "tied_latest":
        thread["messages"].append(copy.deepcopy(source))
    elif fault == "wrong_thread":
        source["threadId"] = "other-thread"
    else:
        source["payload"] = "bad-shape"

    def handler(request):
        methods.append(request.method)
        return httpx.Response(200, json={"emailAddress": "owner@example.invalid"} if request.url.path.endswith("/profile") else thread)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        _, actions, google = await _runtime(tmp_path, client)
        parameters = {"thread_id": "thread-1", "body": "Owner text"}
        execution = await _begin(actions, "google.gmail.draft", parameters)
        with pytest.raises(GoogleAuthError, match=reason):
            await google.execute_authorized_action(actions, execution_id=execution.execution_id, parameters=parameters)
        assert (await actions.get_execution(execution.execution_id)).status is ExecutionStatus.PRECONDITION_FAILED
    assert methods == ["GET", "GET"]


def _approved_draft():
    snapshot = {"from": "owner@example.invalid", "to": ["supplier@example.invalid"], "cc": [], "bcc": [],
                "reply_to": [], "subject": "Supplier update", "in_reply_to": "<incoming@example.invalid>",
                "references": ["<incoming@example.invalid>"], "body": "Approved reply\n"}
    return {"id": "draft-1", "message": {"id": "draft-message-1", "threadId": "thread-1", "raw": encode_snapshot(snapshot)}}


@pytest.mark.parametrize("readback_fault", [None, "body", "recipient", "subject", "reference", "thread", "unsent"])
async def test_send_uses_frozen_approved_mime_and_independent_content_verification(tmp_path, readback_fault):
    state = {"draft": _approved_draft()}
    requests = []

    def handler(request):
        requests.append(request)
        if "/drafts/" in request.url.path:
            return httpx.Response(200, json=copy.deepcopy(state["draft"]))
        if request.method == "POST":
            assert request.url.path == "/gmail/v1/users/me/messages/send"
            submitted = json.loads(request.content)
            assert _decode(submitted["raw"]).get_content() == "Approved reply\r\n"
            # Concurrent Gmail edits cannot change the immutable payload already sent.
            edited = message_snapshot(state["draft"]["message"]["raw"])
            edited["body"] = "Changed after approval\n"
            edited["to"] = ["changed@example.invalid"]
            state["draft"]["message"]["raw"] = encode_snapshot(edited)
            state["sent"] = {"id": "message-1", "labelIds": ["SENT"], **submitted}
            return httpx.Response(200, json={"id": "message-1", "threadId": "thread-1", "labelIds": ["SENT"]})
        assert request.url.params["format"] == "raw"
        observed = copy.deepcopy(state["sent"])
        if readback_fault in {"body", "recipient", "subject", "reference"}:
            snapshot = message_snapshot(observed["raw"])
            if readback_fault == "recipient":
                snapshot["to"] = ["other@example.invalid"]
            elif readback_fault == "reference":
                snapshot["in_reply_to"] = "<other@example.invalid>"
            else:
                snapshot[readback_fault] = "Other value\n" if readback_fault == "body" else "Other subject"
            observed["raw"] = encode_snapshot(snapshot)
        elif readback_fault == "thread":
            observed["threadId"] = "wrong-thread"
        elif readback_fault == "unsent":
            observed["labelIds"] = ["DRAFT"]
        return httpx.Response(200, json=observed)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        _, actions, google = await _runtime(tmp_path, client)
        preview = await google.gmail_draft_preview("draft-1")
        parameters = {"draft_id": "draft-1", "draft_content_sha256": preview["draft_content_sha256"]}
        execution = await _begin(actions, "google.gmail.send", parameters)
        result = await google.execute_authorized_action(actions, execution_id=execution.execution_id, parameters=parameters)
    assert result["verification"]["status"] == ("VERIFIED_SUCCESS" if readback_fault is None else "PARTIAL_SUCCESS")
    observed = result["verification"]["observed_postcondition"]
    assert observed["source_draft_cleanup"] == "NOT_ATTEMPTED" and observed["source_draft_state"] == "UNOBSERVED"
    assert observed["immutable_payload_send_supported"] is True
    assert sum(request.method == "POST" for request in requests) == 1
    assert state["draft"]["id"] == "draft-1"


async def test_edit_before_send_conflicts_and_never_submits(tmp_path):
    draft, requests = _approved_draft(), []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=copy.deepcopy(draft))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        _, actions, google = await _runtime(tmp_path, client)
        preview = await google.gmail_draft_preview("draft-1")
        parameters = {"draft_id": "draft-1", "draft_content_sha256": preview["draft_content_sha256"]}
        execution = await _begin(actions, "google.gmail.send", parameters)
        changed = message_snapshot(draft["message"]["raw"])
        changed["body"] = "Unapproved text\n"
        draft["message"]["raw"] = encode_snapshot(changed)
        with pytest.raises(GoogleAuthError, match="gmail_send_draft_changed_since_approval"):
            await google.execute_authorized_action(actions, execution_id=execution.execution_id, parameters=parameters)
        assert (await actions.get_execution(execution.execution_id)).status is ExecutionStatus.CONFLICTED_STATE
    assert all(request.method == "GET" for request in requests)


async def test_ambiguous_send_timeout_never_retries_or_claims_success(tmp_path):
    posts = []

    def handler(request):
        if request.method == "POST":
            posts.append(request)
            raise httpx.ReadTimeout("private transport detail")
        return httpx.Response(200, json=_approved_draft())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        _, actions, google = await _runtime(tmp_path, client)
        preview = await google.gmail_draft_preview("draft-1")
        parameters = {"draft_id": "draft-1", "draft_content_sha256": preview["draft_content_sha256"]}
        execution = await _begin(actions, "google.gmail.send", parameters)
        with pytest.raises(GoogleAuthError, match="google_timeout"):
            await google.execute_authorized_action(actions, execution_id=execution.execution_id, parameters=parameters)
        failed = await actions.get_execution(execution.execution_id)
        assert failed.status is ExecutionStatus.EXECUTION_FAILED and failed.error_code == "google_timeout"
        with pytest.raises(Exception, match="execution_not_authorized"):
            await google.execute_authorized_action(actions, execution_id=execution.execution_id, parameters=parameters)
    assert len(posts) == 1
