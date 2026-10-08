"""Current producer fences, quarantine separation, and durable analysis receipts."""
import hashlib
import pytest
from test_browser_producer_api import fabric, ready, PID, PRINCIPAL, NOW
from van_gateway.browser.producer_service import ProducerError


async def file(f, name="owner.txt"):
    await ready(f)
    await f.producers.observe(producer_session_id=PID, principal=PRINCIPAL, event="target", target_id="tab", url="https://example.org", now_ms=NOW)
    await f.producers.report_download(producer_session_id=PID, principal=PRINCIPAL, event="started",
        download_id="file", target_id="tab", suggested_name=name, url_digest="0"*64, now_ms=NOW)
    await f.producers.report_download(producer_session_id=PID, principal=PRINCIPAL, event="finished",
        download_id="file", target_id="tab", byte_size=5, content_sha256="a"*64, observed_mime="text/plain", now_ms=NOW)


async def grant(f, operation="analyse", **extra):
    return await f.producers.issue_transfer_grant(session_id=f.session.session_id, owner_device_id="phone",
        operation=operation, target_id="tab", download_id="file", now_ms=NOW, **extra)


async def consumed(f, issued):
    return await f.producers.consume_transfer_grant(producer_session_id=PID, principal=PRINCIPAL,
        transfer_grant=issued["transfer_grant"], operation=issued["operation"], resource_id=issued["resource_id"], now_ms=NOW)


async def test_quarantine_can_be_statically_analysed_but_never_downloaded(fabric):
    await file(fabric, "untrusted.py")
    issued = await grant(fabric)
    result = await consumed(fabric, issued)
    assert result["operation"] == "analyse" and result["state"] == "QUARANTINED"
    with pytest.raises(ProducerError, match="transfer_not_permitted"): await grant(fabric, "download")
    with pytest.raises(ProducerError, match="consumed"): await consumed(fabric, issued)


async def test_static_analysis_receipt_requires_consumed_exact_current_grant(fabric):
    await file(fabric)
    issued = await grant(fabric)
    result = await consumed(fabric, issued)
    receipt = {"download_id":"file", "byte_size":5,"content_sha256":"a"*64,
        "observed_mime":"text/plain", "analysis_kind":"BOUNDED_STATIC_INSPECTION",
        "content_authority":"UNTRUSTED_FILE_EVIDENCE", "executed_content":False,
        "truncated":False, "analysis_sha256":"b"*64}
    kwargs = dict(producer_session_id=PID, principal=PRINCIPAL, transfer_id=result["transfer_id"],
        operation="analyse", resource_id="file", receipt=receipt, now_ms=NOW)
    stored = await fabric.producers.report_file_result(**kwargs)
    assert stored["status"] == "VERIFIED_SUCCESS"
    assert await fabric.producers.report_file_result(**kwargs) == stored
    with pytest.raises(ProducerError, match="content_mismatch"):
        await fabric.producers.report_file_result(**{**kwargs,"receipt":{**receipt,"content_sha256":"c"*64}})
    await fabric.store.execute("UPDATE devices SET revoked_at_unix=1 WHERE device_id='phone'")
    with pytest.raises(ProducerError, match="device_not_active"): await fabric.producers.report_file_result(**kwargs)


async def test_general_import_server_generates_resource_and_binds_exact_bytes(fabric):
    await file(fabric)
    issued = await grant(fabric, "file_import", byte_size=7, content_sha256="f"*64, suggested_name="owner.txt", mime_type="text/plain")
    assert issued["resource_id"].startswith("import_") and issued["resource_id"] != "tab"
    with pytest.raises(ProducerError, match="content_mismatch"):
        await fabric.producers.consume_transfer_grant(producer_session_id=PID, principal=PRINCIPAL,
            transfer_grant=issued["transfer_grant"], operation="file_import", resource_id=issued["resource_id"],
            byte_size=7, content_sha256="0"*64, now_ms=NOW)
    result = await fabric.producers.consume_transfer_grant(producer_session_id=PID, principal=PRINCIPAL,
        transfer_grant=issued["transfer_grant"], operation="file_import", resource_id=issued["resource_id"],
        byte_size=7, content_sha256="f"*64, now_ms=NOW)
    assert result["resource_id"] == issued["resource_id"] and result["content_sha256"] == "f"*64
