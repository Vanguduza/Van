"""Rev 1.5 §18 — a file the owner's browser fetched, and what VAN is allowed to do with it.

Downloads happen on the Stream Host, not on the phone and not here. What the Gateway owns
is the *record* and the *decision*: which state a download is in, whether it may be handed
to anything, and what the owner is offered.

§18.2's rule is the one the whole module is arranged around: **downloaded executable,
script or archive content is not automatically executed.** The pipeline it names —
quarantine, hash, MIME validation, then an owner-visible completed state — is a sequence in
which the file is untrusted until each step has run, and the failure this prevents is not
subtle: a browser session driven by an agent, on a host with the owner's credentials,
fetching something that runs.

So `QUARANTINED` is not an error state here. It is where a dangerous-by-type file stops,
permanently, unless the owner says otherwise — and `COMPLETED` is reachable only for
content that is not dangerous by type. A design where quarantine were a transient step on
the way to completion would mean the dangerous case eventually reaches the same place as
the safe one.
"""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from enum import Enum


class DownloadState(str, Enum):
    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    #: Held. Reachable by the owner, never by an agent, and never automatically.
    QUARANTINED = "QUARANTINED"
    DELETED = "DELETED"

    @property
    def terminal(self) -> bool:
        return self in {DownloadState.COMPLETED, DownloadState.FAILED, DownloadState.DELETED}

    @property
    def owner_may_act(self) -> bool:
        """Whether the owner is offered anything. A quarantined file still is."""
        return self in {DownloadState.COMPLETED, DownloadState.QUARANTINED}


#: §18.1's legal moves. Absent from this table: anything out of QUARANTINED except by an
#: owner decision, which is `release_from_quarantine` and is a separate method for that
#: reason — a transition table that allowed QUARANTINED → COMPLETED would let any code path
#: that advances state do the releasing.
_TRANSITIONS: dict[DownloadState, frozenset[DownloadState]] = {
    DownloadState.CREATED: frozenset({DownloadState.IN_PROGRESS, DownloadState.FAILED}),
    DownloadState.IN_PROGRESS: frozenset(
        {DownloadState.COMPLETED, DownloadState.FAILED, DownloadState.QUARANTINED}
    ),
    DownloadState.COMPLETED: frozenset({DownloadState.DELETED}),
    DownloadState.QUARANTINED: frozenset({DownloadState.DELETED}),
    DownloadState.FAILED: frozenset({DownloadState.DELETED}),
    DownloadState.DELETED: frozenset(),
}


#: §18.2 — content that is dangerous by type. Matched on the *name*, because the declared
#: MIME type comes from the server that served the file and is therefore the attacker's
#: field to fill in.
_DANGEROUS_SUFFIXES = frozenset(
    {
        "exe", "dll", "scr", "com", "bat", "cmd", "ps1", "psm1", "vbs", "js", "jse",
        "wsf", "wsh", "hta", "msi", "msp", "cpl", "jar", "apk", "app", "dmg", "pkg",
        "deb", "rpm", "sh", "bash", "zsh", "py", "pyc", "rb", "pl", "php",
        "zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso", "img", "cab",
        "lnk", "url", "desktop", "reg",
    }
)

#: MIME types that mean the same thing, whatever the extension says.
_DANGEROUS_MIME_PREFIXES = (
    "application/x-msdownload",
    "application/x-executable",
    "application/x-sh",
    "application/x-shellscript",
    "application/vnd.microsoft.portable-executable",
    "application/java-archive",
    "application/vnd.android.package-archive",
    "application/zip",
    "application/x-tar",
    "application/gzip",
)

#: A name that is not a name. Path separators and traversal, matched before anything else.
_UNSAFE_NAME = re.compile(r"(^\.\.?$)|(\.\.[/\\])|([/\\])|(^\s*$)|([\x00-\x1f])")


class DownloadError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class DownloadClassification:
    """What the pipeline concluded, and why."""

    dangerous: bool
    reason: str
    #: The name VAN will show. Never the raw one from the server.
    safe_name: str


def sanitise_name(suggested: str) -> str:
    """The filename the owner sees, with everything a server chose removed.

    A download's suggested name is attacker-controlled. Path separators in it are an
    attempt to write outside the quarantine directory, and a leading dot is an attempt to
    be invisible. Neither is a filename.
    """
    name = (suggested or "").strip().replace("\x00", "")
    if _UNSAFE_NAME.search(name):
        # Refuse rather than repair. A "cleaned" version of `../../.bashrc` is a filename
        # nobody asked for, and the owner then sees a name that was never on the server.
        raise DownloadError("download_name_unsafe")
    if len(name) > 180:
        raise DownloadError("download_name_too_long")
    return name


def classify(*, suggested_name: str, declared_mime: str | None) -> DownloadClassification:
    """§18.2 — is this content dangerous by type?

    The name is checked first and the declared MIME second, and **either** one is enough.
    The server chooses both, so a file called `invoice.pdf` served as
    `application/x-msdownload` is dangerous, and so is `setup.exe` served as `text/plain`.
    Requiring agreement between them would mean the attacker only has to lie once.
    """
    safe_name = sanitise_name(suggested_name)
    suffix = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""

    if suffix in _DANGEROUS_SUFFIXES:
        return DownloadClassification(True, f"download_dangerous_extension:{suffix}", safe_name)

    mime = (declared_mime or "").split(";")[0].strip().lower()
    if any(mime.startswith(prefix) for prefix in _DANGEROUS_MIME_PREFIXES):
        return DownloadClassification(True, f"download_dangerous_mime:{mime}", safe_name)

    return DownloadClassification(False, "", safe_name)


#: §18.3 — what the owner is offered. Each is a decision, not an execution.
class OwnerAction(str, Enum):
    OPEN_IN_VAN = "OPEN_IN_VAN"
    ANALYSE = "ANALYSE"
    SAVE_ON_ORACLE = "SAVE_ON_ORACLE"
    SEND_TO_PHONE = "SEND_TO_PHONE"
    ADD_TO_VEKL = "ADD_TO_VEKL"
    DELETE = "DELETE"


def owner_actions(state: DownloadState, *, dangerous: bool) -> list[OwnerAction]:
    """Which actions a download in this state is offered.

    A quarantined file is offered fewer, and the ones it loses are the ones that would put
    it somewhere it could run or be opened by something else: `OPEN_IN_VAN` and
    `SEND_TO_PHONE`. `ANALYSE` stays, because looking at a file is the whole point of
    having quarantined it, and `DELETE` always stays.
    """
    if state is DownloadState.DELETED:
        return []
    if not state.owner_may_act:
        return [OwnerAction.DELETE]
    if dangerous or state is DownloadState.QUARANTINED:
        return [OwnerAction.ANALYSE, OwnerAction.SAVE_ON_ORACLE, OwnerAction.DELETE]
    return list(OwnerAction)


class DownloadBroker:
    """§18 — the record and the decisions. Never the bytes.

    The Gateway does not hold, copy or serve the file. It is on the Stream Host's
    quarantine volume, and `local_server_ref` is a pointer the host understands. A broker
    that moved bytes would put the owner's downloads through the control plane, which is
    the same mistake §6.4 keeps media out of.
    """

    def __init__(self, store) -> None:
        self.store = store

    async def create(
        self,
        *,
        download_id: str,
        session_id: str,
        target_id: str | None,
        suggested_name: str,
        declared_mime: str | None,
        url_digest: str,
        now_ms: int | None = None,
    ) -> DownloadClassification:
        """Record a download the host has started. Classification happens here, not later.

        Classifying at creation means the record carries the verdict from the first moment
        it exists, so there is no window in which something reads the row and sees a file
        that has not been judged yet.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        verdict = classify(suggested_name=suggested_name, declared_mime=declared_mime)
        try:
            await self._insert(download_id, session_id, target_id, verdict, declared_mime,
                               url_digest, now)
        except sqlite3.IntegrityError as exc:
            # The host retried a report it never got an answer to. Refused rather than
            # inserted again, and refused with its own reason: the caller can then read
            # the record's real state instead of being told the download is starting when
            # it may already have been quarantined.
            raise DownloadError("download_already_reported") from exc
        return verdict

    async def _insert(self, download_id, session_id, target_id, verdict, declared_mime,
                      url_digest, now) -> None:
        await self.store.execute(
            """
            INSERT INTO browser_downloads (
              download_id, session_id, target_id, suggested_name, mime_type,
              byte_size, content_sha256, url_digest, state, failure_reason,
              evidence_ref, created_at_ms, completed_at_ms
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, NULL, ?, NULL)
            """,
            (
                download_id, session_id, target_id, verdict.safe_name, declared_mime,
                url_digest, DownloadState.CREATED.value,
                verdict.reason or None, now,
            ),
        )

    async def state_of(self, download_id: str) -> DownloadState:
        return DownloadState((await self._row(download_id))["state"])

    async def start(self, download_id: str) -> None:
        await self._transition(download_id, DownloadState.IN_PROGRESS)

    async def finish(
        self,
        *,
        download_id: str,
        byte_size: int,
        content_sha256: str,
        observed_mime: str | None = None,
        now_ms: int | None = None,
    ) -> DownloadState:
        """The host finished writing it. The pipeline decides where it stops.

        §18.2's order, and it matters: hash first, then MIME validation, then the state.
        Hashing before classification means the record can identify the file even when the
        answer is "this is quarantined" — an unidentifiable quarantined file is one nobody
        can look up later.

        `observed_mime` is what the host sniffed from the content, as opposed to what the
        server declared. When they disagree, the stricter answer wins: a server that
        declared `text/plain` for an ELF binary is not a server to take a hint from.
        """
        now = int(time.time() * 1000) if now_ms is None else now_ms
        row = await self._row(download_id)
        current = DownloadState(row["state"])
        if current is not DownloadState.IN_PROGRESS:
            raise DownloadError(f"download_not_in_progress:{current.value}")

        verdict = classify(
            suggested_name=row["suggested_name"],
            declared_mime=observed_mime or row["mime_type"],
        )
        # Either the name or either MIME reading is enough. The declared one was already
        # checked at creation and its verdict is in failure_reason.
        dangerous = verdict.dangerous or bool(row["failure_reason"])
        target = DownloadState.QUARANTINED if dangerous else DownloadState.COMPLETED

        await self.store.execute(
            """
            UPDATE browser_downloads
               SET state = ?, byte_size = ?, content_sha256 = ?, mime_type = ?,
                   failure_reason = ?, completed_at_ms = ?
             WHERE download_id = ?
            """,
            (
                target.value, byte_size, content_sha256,
                observed_mime or row["mime_type"],
                verdict.reason or row["failure_reason"], now, download_id,
            ),
        )
        return target

    async def fail(self, download_id: str, reason: str, *, now_ms: int | None = None) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self._transition(download_id, DownloadState.FAILED, reason=reason, at_ms=now)

    async def delete(self, download_id: str, *, now_ms: int | None = None) -> None:
        now = int(time.time() * 1000) if now_ms is None else now_ms
        await self._transition(download_id, DownloadState.DELETED, at_ms=now)

    async def actions_for(self, download_id: str) -> list[OwnerAction]:
        row = await self._row(download_id)
        return owner_actions(
            DownloadState(row["state"]), dangerous=bool(row["failure_reason"])
        )

    async def _row(self, download_id: str):
        row = await self.store.fetchone(
            "SELECT * FROM browser_downloads WHERE download_id = ?", (download_id,)
        )
        if row is None:
            raise DownloadError("download_unknown")
        return row

    async def _transition(
        self,
        download_id: str,
        target: DownloadState,
        *,
        reason: str | None = None,
        at_ms: int | None = None,
    ) -> None:
        row = await self._row(download_id)
        current = DownloadState(row["state"])
        if target not in _TRANSITIONS[current]:
            raise DownloadError(f"download_transition_refused:{current.value}->{target.value}")
        await self.store.execute(
            """
            UPDATE browser_downloads
               SET state = ?,
                   failure_reason = COALESCE(?, failure_reason),
                   completed_at_ms = COALESCE(?, completed_at_ms)
             WHERE download_id = ?
            """,
            (target.value, reason, at_ms if target.terminal else None, download_id),
        )
