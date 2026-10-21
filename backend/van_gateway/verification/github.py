"""Bounded independent GitHub observations, configured by repository allowlist only.

Worker receipts, local worktrees and DIAL projection caches are not remote Git/CI
truth. These adapters ask GitHub afresh about a sealed branch/head or exact run.
Nothing is configured by default and no Android credential is accepted upstream.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,38}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
_SHA = re.compile(r"[0-9a-f]{40}")
MAX_RESPONSE_BYTES = 512 * 1024


class RepositoryHeadPostconditions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    repository: str
    branch: str
    commit_sha: str
    repository_head_matches: StrictBool

    @field_validator("repository")
    @classmethod
    def repository_valid(cls, value: str) -> str:
        if not _REPOSITORY.fullmatch(value) or value.split("/")[1] in {".", ".."}:
            raise ValueError("invalid repository identity")
        return value

    @field_validator("branch")
    @classmethod
    def branch_valid(cls, value: str) -> str:
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", value)
            or ".." in value or "//" in value or value.endswith(("/", ".", ".lock"))):
            raise ValueError("invalid branch identity")
        return value

    @field_validator("commit_sha")
    @classmethod
    def sha_valid(cls, value: str) -> str:
        if not _SHA.fullmatch(value):
            raise ValueError("full immutable SHA required")
        return value

    @field_validator("repository_head_matches")
    @classmethod
    def positive_claim(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("remote head claim must require a match")
        return value


class CiRunPostconditions(RepositoryHeadPostconditions):
    run_id: str
    workflow_id: str
    run_attempt: StrictInt = Field(ge=1, le=1000000)
    ci_requested_after_unix_ms: StrictInt = Field(ge=0)
    ci_run_matches: StrictBool
    ci_completed: StrictBool
    ci_success: StrictBool

    @field_validator("run_id", "workflow_id")
    @classmethod
    def numeric_identity(cls, value: str) -> str:
        if not re.fullmatch(r"[1-9][0-9]{0,19}", value):
            raise ValueError("exact numeric run/workflow identity required")
        return value

    @field_validator("ci_run_matches", "ci_completed", "ci_success")
    @classmethod
    def positive_ci_claim(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("CI contract must require exact completed success")
        return value


class GithubObservationUnavailable(Exception):
    """Fixed safe failure vocabulary; remote bodies and credentials are never surfaced."""


@dataclass(frozen=True)
class GithubVerificationConfig:
    repositories: frozenset[str] = frozenset()
    token_file: str = ""

    @classmethod
    def from_env(cls) -> "GithubVerificationConfig":
        repositories = frozenset(item.strip().casefold() for item in os.environ.get("VAN_GITHUB_VERIFICATION_REPOSITORIES", "").split(",") if item.strip())
        if len(repositories) > 100 or any(not _REPOSITORY.fullmatch(item) for item in repositories):
            # A malformed configured allowlist grants no origin; startup stays observable.
            return cls()
        return cls(repositories, os.environ.get("VAN_GITHUB_VERIFICATION_TOKEN_FILE", "").strip())


class GithubVerificationSource:
    API_ORIGIN = "https://api.github.com"

    def __init__(self, config: GithubVerificationConfig, *, transport: httpx.AsyncBaseTransport | None = None):
        self.config = config
        self.transport = transport

    def _headers(self) -> tuple[dict[str, str], str | None]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "van-gateway/independent-verification"}
        token = None
        if self.config.token_file:
            try:
                path = Path(self.config.token_file)
                metadata = path.lstat()
                if not path.is_absolute() or not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077 or metadata.st_size > 8192:
                    raise ValueError("invalid token binding")
                token = path.read_text(encoding="utf-8").strip()
                if len(token) < 32 or len(token) > 4096 or any(ch.isspace() for ch in token):
                    raise ValueError("invalid token binding")
            except (OSError, UnicodeError, ValueError) as exc:
                raise GithubObservationUnavailable("credential_unconfigured") from exc
            headers["Authorization"] = "Bearer " + token
        return headers, token

    async def _get(self, repository: str, suffix: str) -> dict[str, Any]:
        if repository.casefold() not in self.config.repositories:
            raise GithubObservationUnavailable("repository_not_configured")
        headers, token = self._headers()
        try:
            async with asyncio.timeout(8):
                async with httpx.AsyncClient(base_url=self.API_ORIGIN, transport=self.transport, timeout=5,
                    follow_redirects=False, trust_env=False) as client:
                    async with client.stream("GET", f"/repos/{repository}/{suffix}", headers=headers) as response:
                        if 300 <= response.status_code < 400:
                            raise GithubObservationUnavailable("upstream_redirect")
                        if not 200 <= response.status_code < 300:
                            raise GithubObservationUnavailable("upstream_unavailable")
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > MAX_RESPONSE_BYTES:
                                raise GithubObservationUnavailable("upstream_too_large")
            if token and token.encode() in data:
                raise GithubObservationUnavailable("upstream_echoed_credential")
            result = json.loads(data)
            if not isinstance(result, dict):
                raise ValueError("object required")
            return result
        except GithubObservationUnavailable:
            raise
        except (httpx.HTTPError, TimeoutError, ValueError) as exc:
            raise GithubObservationUnavailable("upstream_unavailable") from exc

    async def repository_head(self, context: dict[str, Any]) -> dict[str, Any]:
        spec = RepositoryHeadPostconditions.model_validate(context.get("postconditions") or {})
        remote = await self._get(spec.repository, "git/ref/heads/" + quote(spec.branch, safe=""))
        remote_sha = (remote.get("object") or {}).get("sha")
        matches = (remote.get("ref") == "refs/heads/" + spec.branch and (remote.get("object") or {}).get("type") == "commit"
            and isinstance(remote_sha, str) and _SHA.fullmatch(remote_sha) is not None and remote_sha == spec.commit_sha)
        return {"repository": spec.repository, "branch": spec.branch, "commit_sha": remote_sha,
            "repository_head_matches": bool(matches), "evidence_ref": f"https://github.com/{spec.repository}/commit/{remote_sha}" if matches else None}

    async def ci_run(self, context: dict[str, Any]) -> dict[str, Any]:
        spec = CiRunPostconditions.model_validate(context.get("postconditions") or {})
        # Attempt-specific endpoint prevents a rerun silently replacing the approved run.
        run = await self._get(spec.repository, f"actions/runs/{spec.run_id}/attempts/{spec.run_attempt}")
        def timestamp_ms(value):
            if not isinstance(value, str):
                raise ValueError("CI timestamp missing")
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("CI timezone missing")
            return int(parsed.timestamp() * 1000)
        created = timestamp_ms(run.get("created_at"))
        started = timestamp_ms(run.get("run_started_at"))
        updated = timestamp_ms(run.get("updated_at"))
        now = int(datetime.now(timezone.utc).timestamp() * 1000)
        remote_repository = (run.get("repository") or {}).get("full_name")
        identity_matches = (type(run.get("id")) is int and str(run["id"]) == spec.run_id
            and type(run.get("workflow_id")) is int and str(run["workflow_id"]) == spec.workflow_id
            and type(run.get("run_attempt")) is int and run["run_attempt"] == spec.run_attempt
            and isinstance(remote_repository, str) and remote_repository.casefold() == spec.repository.casefold()
            and run.get("head_sha") == spec.commit_sha and run.get("head_branch") == spec.branch
            and started >= spec.ci_requested_after_unix_ms and created <= started <= updated and updated <= now + 60000)
        completed, success = run.get("status") == "completed", run.get("conclusion") == "success"
        # CI head binding does not imply the branch still points at that SHA. Observe it too.
        head = await self.repository_head({"postconditions": {name: getattr(spec, name) for name in RepositoryHeadPostconditions.model_fields}})
        return {**head, "run_id": str(run.get("id")), "workflow_id": str(run.get("workflow_id")),
            "run_attempt": run.get("run_attempt"), "ci_requested_after_unix_ms": started,
            "ci_run_matches": identity_matches, "ci_completed": completed, "ci_success": success,
            "evidence_ref": f"https://github.com/{spec.repository}/actions/runs/{spec.run_id}/attempts/{spec.run_attempt}" if identity_matches and completed and success else None}


__all__ = ["RepositoryHeadPostconditions", "CiRunPostconditions", "GithubVerificationConfig", "GithubVerificationSource"]
