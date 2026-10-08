"""Plain reply preparation and semantic Gmail MIME readback binding.

Header metadata is external input, not owner truth. A reply target must be a
single address from a real incoming message; missing metadata is never guessed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser, Parser
from email.utils import formatdate
from typing import Any

MAX_MESSAGE_BYTES = 2 * 1024 * 1024
_MESSAGE_ID = re.compile(r"^<[^<>\s@]+@[^<>\s@]+>$")


def _header(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 8192 or any(ch in value for ch in "\r\n\x00"):
        raise RuntimeError("gmail_reply_header_invalid")
    return value


def _addresses(value: str, *, single: bool = False) -> list[str]:
    value = _header(value)
    parsed = Parser(policy=policy.default).parsestr(f"To: {value}\n\n")["To"]
    addresses = list(parsed.addresses)
    if parsed.defects or not addresses or (single and len(addresses) != 1):
        raise RuntimeError("gmail_reply_address_ambiguous")
    result = []
    for address in addresses:
        if not address.username or not address.domain or any(ch.isspace() for ch in address.addr_spec):
            raise RuntimeError("gmail_reply_address_invalid")
        try:
            address.addr_spec.encode("ascii")
        except UnicodeEncodeError as exc:
            raise RuntimeError("gmail_reply_address_invalid") from exc
        result.append(f"{address.username}@{address.domain.lower()}")
    return result


def _normal_body(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def decode_message(raw: str) -> EmailMessage:
    if not isinstance(raw, str) or len(raw) > MAX_MESSAGE_BYTES * 2 or re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", raw) is None:
        raise RuntimeError("gmail_raw_message_invalid")
    try:
        data = base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True)
        if len(data) > MAX_MESSAGE_BYTES:
            raise ValueError("message too large")
        message = BytesParser(policy=policy.default).parsebytes(data)
        if message.defects:
            raise ValueError("malformed MIME")
        return message
    except (ValueError, TypeError) as exc:
        raise RuntimeError("gmail_raw_message_invalid") from exc


def message_snapshot(raw: str) -> dict[str, Any]:
    """Bind meaning, not Base64 padding or SMTP line-ending spelling."""
    message = decode_message(raw)
    for name in ("From", "To", "Cc", "Bcc", "Subject", "In-Reply-To", "References", "Reply-To"):
        if len(message.get_all(name, [])) > 1:
            raise RuntimeError("gmail_raw_message_duplicate_header")
    if message.is_multipart() or message.get_content_type() != "text/plain" or message.get_content_disposition() == "attachment":
        raise RuntimeError("gmail_raw_message_plain_text_required")
    if "From" not in message or "To" not in message or "Subject" not in message:
        raise RuntimeError("gmail_raw_message_required_header_missing")
    try:
        body = message.get_content(errors="strict")
    except (LookupError, UnicodeError, ValueError) as exc:
        raise RuntimeError("gmail_raw_message_invalid") from exc
    in_reply_to = _header(str(message.get("In-Reply-To", "")))
    references = _header(str(message.get("References", ""))).split()
    if (in_reply_to and _MESSAGE_ID.fullmatch(in_reply_to) is None) or any(_MESSAGE_ID.fullmatch(item) is None for item in references):
        raise RuntimeError("gmail_reply_message_id_invalid")
    return {
        "from": _addresses(str(message["From"]), single=True)[0],
        "to": _addresses(str(message["To"])),
        "cc": _addresses(str(message["Cc"])) if message.get("Cc") else [],
        "bcc": _addresses(str(message["Bcc"])) if message.get("Bcc") else [],
        "reply_to": _addresses(str(message["Reply-To"])) if message.get("Reply-To") else [],
        "subject": _header(str(message["Subject"])),
        "in_reply_to": in_reply_to,
        "references": references,
        "body": _normal_body(body),
    }


def content_digest(snapshot: dict[str, Any], thread_id: str) -> str:
    material = json.dumps({"thread_id": thread_id, "message": snapshot}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(material.encode()).hexdigest()


def encode_snapshot(snapshot: dict[str, Any]) -> str:
    """Serialize only approved fields; discard unrelated provider/raw headers."""
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = snapshot["from"]
    message["To"] = ", ".join(snapshot["to"])
    for name, key in (("Cc", "cc"), ("Bcc", "bcc"), ("Reply-To", "reply_to")):
        if snapshot[key]:
            message[name] = ", ".join(snapshot[key])
    message["Subject"] = snapshot["subject"]
    if snapshot["in_reply_to"]:
        message["In-Reply-To"] = snapshot["in_reply_to"]
    if snapshot["references"]:
        message["References"] = " ".join(snapshot["references"])
    message["Date"] = formatdate(localtime=False, usegmt=True)
    message.set_content(snapshot["body"], charset="utf-8")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
    if message_snapshot(raw) != snapshot:
        raise RuntimeError("gmail_frozen_message_mismatch")
    return raw


@dataclass(frozen=True)
class PreparedReply:
    raw: str
    snapshot: dict[str, Any]
    source_message_id: str


def prepare_reply(profile: dict[str, Any], thread: dict[str, Any], thread_id: str, body: str) -> PreparedReply:
    if not isinstance(body, str) or len(body.encode("utf-8")) > MAX_MESSAGE_BYTES // 2 or "\x00" in body:
        raise RuntimeError("gmail_reply_body_invalid")
    if not isinstance(profile, dict) or not isinstance(thread, dict):
        raise RuntimeError("gmail_reply_thread_metadata_missing")
    owner = _addresses(profile.get("emailAddress"), single=True)[0]
    if thread.get("id") != thread_id:
        raise RuntimeError("gmail_reply_thread_mismatch")
    messages = thread.get("messages")
    if not isinstance(messages, list) or not messages or any(not isinstance(item, dict) for item in messages):
        raise RuntimeError("gmail_reply_thread_metadata_missing")
    try:
        dated = [(int(item["internalDate"]), item) for item in messages]
    except (ValueError, TypeError, KeyError) as exc:
        raise RuntimeError("gmail_reply_thread_metadata_missing") from exc
    latest_time = max(item[0] for item in dated)
    latest = [item[1] for item in dated if item[0] == latest_time]
    if len(latest) != 1:
        raise RuntimeError("gmail_reply_target_ambiguous")
    source = latest[0]
    if source.get("threadId") != thread_id or not source.get("id"):
        raise RuntimeError("gmail_reply_thread_mismatch")
    labels = source.get("labelIds")
    if not isinstance(labels, list) or any(item in labels for item in ("SENT", "DRAFT", "TRASH", "SPAM")):
        raise RuntimeError("gmail_reply_target_not_incoming")
    payload = source.get("payload")
    if not isinstance(payload, dict):
        raise RuntimeError("gmail_reply_thread_metadata_missing")
    headers = payload.get("headers")
    if not isinstance(headers, list):
        raise RuntimeError("gmail_reply_thread_metadata_missing")
    values = {}
    for item in headers:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise RuntimeError("gmail_reply_thread_metadata_missing")
        key = item["name"].casefold()
        if key in {"from", "reply-to", "subject", "message-id", "references"}:
            if key in values:
                raise RuntimeError("gmail_reply_header_ambiguous")
            values[key] = _header(item.get("value"))
    if any(key not in values for key in ("from", "subject", "message-id")):
        raise RuntimeError("gmail_reply_thread_metadata_missing")
    sender = _addresses(values["from"], single=True)[0]
    if sender.casefold() == owner.casefold():
        raise RuntimeError("gmail_reply_target_not_incoming")
    recipient = _addresses(values.get("reply-to", values["from"]), single=True)[0]
    if recipient.casefold() == owner.casefold():
        raise RuntimeError("gmail_reply_target_not_incoming")
    message_id = values["message-id"].strip()
    references = values.get("references", "").split()
    if _MESSAGE_ID.fullmatch(message_id) is None or any(_MESSAGE_ID.fullmatch(item) is None for item in references):
        raise RuntimeError("gmail_reply_message_id_invalid")
    if not references or references[-1] != message_id:
        references.append(message_id)
    reply = EmailMessage(policy=policy.SMTP)
    reply["From"] = owner
    reply["To"] = recipient
    # Keep the exact thread subject. Gmail's threading contract requires a
    # matching Subject and valid In-Reply-To/References, not a guessed subject.
    reply["Subject"] = values["subject"]
    reply["In-Reply-To"] = message_id
    reply["References"] = " ".join(references)
    reply["Date"] = formatdate(localtime=False, usegmt=True)
    reply.set_content(_normal_body(body), charset="utf-8")
    raw = base64.urlsafe_b64encode(reply.as_bytes()).decode("ascii").rstrip("=")
    return PreparedReply(raw=raw, snapshot=message_snapshot(raw), source_message_id=str(source["id"]))
