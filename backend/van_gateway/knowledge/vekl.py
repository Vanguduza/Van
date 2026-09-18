from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any

import httpx

from van_gateway.context.models import SourceTrust
from van_gateway.knowledge.evidence import KnowledgeEvidenceStore
from van_gateway.knowledge.models import (
    KnowledgeProvider,
    ProviderState,
    ProviderStatus,
    VeklQueryRequest,
    VeklQueryResult,
)


class VeklProviderError(RuntimeError):
    pass


class VeklKnowledgeProvider:
    """Read-only adapter over DDE's canonical mission VEKL projection."""

    def __init__(
        self,
        evidence: KnowledgeEvidenceStore,
        *,
        enabled: bool,
        base_url: str,
        session_id: str,
        principal_id: str,
        bearer_token: str = "",
        timeout_seconds: float = 8.0,
        read_retries: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.evidence = evidence
        self.enabled = enabled
        self.base_url = base_url.rstrip("/")
        self.session_id = session_id.strip()
        self.principal_id = principal_id.strip()
        self._bearer_token = bearer_token.strip()
        self.timeout_seconds = timeout_seconds
        self.read_retries = max(0, min(read_retries, 5))
        self.transport = transport

    def _configured(self) -> bool:
        return bool(self.base_url and self.session_id and self.principal_id)

    async def status(self) -> ProviderStatus:
        certification = await self.evidence.certification(KnowledgeProvider.VEKL)
        if not self.enabled:
            state = ProviderState.DISABLED
        elif not self._configured():
            state = ProviderState.UNCONFIGURED
        elif certification and certification["state"] == ProviderState.READY.value:
            state = ProviderState.READY
        else:
            state = ProviderState.CONFIGURED
        return ProviderStatus(
            provider=KnowledgeProvider.VEKL,
            state=state,
            credential_locus="gateway",
            evidence_pointer=certification["evidence_pointer"] if certification else None,
            details={
                "read_only": True,
                "endpoint_contract": "/v1/missions/{mission_id}/vekl",
                "source_authority": "DDE_VEKL_PROJECTION",
                "automatic_owner_truth_promotion": False,
            },
        )

    def _headers(self) -> dict[str, str]:
        headers = {
            "X-Session-Id": self.session_id,
            "X-Principal-Id": self.principal_id,
            "Accept": "application/json",
        }
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers

    async def _get_projection(self, mission_id: str) -> dict[str, Any]:
        if not self.enabled:
            raise VeklProviderError("vekl_disabled")
        if not self._configured():
            raise VeklProviderError("vekl_unconfigured")
        path = f"/v1/missions/{mission_id}/vekl"
        last_error: Exception | None = None
        for attempt in range(self.read_retries + 1):
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout_seconds,
                    transport=self.transport,
                ) as client:
                    response = await client.get(path, headers=self._headers())
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.read_retries:
                    await asyncio.sleep(0.1 * (2**attempt))
                    continue
                if response.status_code == 403:
                    raise VeklProviderError("vekl_scope_or_source_denied")
                if response.status_code == 404:
                    raise VeklProviderError("vekl_mission_not_found")
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise VeklProviderError("vekl_projection_malformed")
                return payload
            except VeklProviderError:
                raise
            except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
                last_error = exc
                if attempt < self.read_retries:
                    await asyncio.sleep(0.1 * (2**attempt))
                    continue
                raise VeklProviderError("vekl_upstream_unavailable") from exc
            except (ValueError, httpx.HTTPStatusError) as exc:
                last_error = exc
                break
        raise VeklProviderError("vekl_upstream_error") from last_error

    @staticmethod
    def _flatten(value: Any, *, max_leaves: int = 4096) -> list[tuple[str, str]]:
        leaves: list[tuple[str, str]] = []

        def walk(item: Any, path: str) -> None:
            if len(leaves) >= max_leaves:
                return
            if isinstance(item, dict):
                for key in sorted(item, key=lambda x: str(x)):
                    child = f"{path}.{key}" if path else str(key)
                    walk(item[key], child)
            elif isinstance(item, list):
                for idx, child_item in enumerate(item):
                    walk(child_item, f"{path}[{idx}]")
            elif item is not None:
                rendered = str(item)
                if len(rendered) > 12000:
                    rendered = rendered[:12000]
                leaves.append((path or "$", rendered))

        walk(value, "")
        return leaves

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {part.casefold() for part in re.findall(r"[\w-]+", value, flags=re.UNICODE) if len(part) > 1}

    @classmethod
    def _score(cls, query: str, path: str, value: str) -> int:
        if not query:
            return 1
        q = cls._tokens(query)
        if not q:
            return 1
        path_tokens = cls._tokens(path)
        value_tokens = cls._tokens(value)
        score = len(q & path_tokens) * 5 + len(q & value_tokens) * 2
        folded_query = query.casefold()
        if folded_query in path.casefold():
            score += 8
        if folded_query in value.casefold():
            score += 4
        return score

    async def query(self, request: VeklQueryRequest) -> VeklQueryResult:
        projection = await self._get_projection(request.mission_id)
        query_id = str(uuid.uuid4())
        flattened = self._flatten(projection)
        ranked = [
            (self._score(request.query, path, value), path, value)
            for path, value in flattened
        ]
        if request.query:
            ranked = [item for item in ranked if item[0] > 0]
        ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
        selected = ranked[: request.max_results]
        items = []
        for score, path, value in selected:
            item = await self.evidence.persist(
                provider=KnowledgeProvider.VEKL,
                query_id=query_id,
                source_ref=f"vekl://mission/{request.mission_id}#{path}",
                title=path,
                source_trust=SourceTrust.VERIFIED_SYSTEM,
                scope=request.scope,
                content={"path": path, "value": value},
                snippet=value,
                metadata={"mission_id": request.mission_id, "path": path, "score": score},
            )
            items.append(item)
        pointer = f"gateway://knowledge/vekl/{query_id}"
        return VeklQueryResult(
            query_id=query_id,
            mission_id=request.mission_id,
            query=request.query,
            evidence=items,
            evidence_pointer=pointer,
            truncated=len(ranked) > len(selected) or len(flattened) >= 4096,
        )

    async def certify(self, request: VeklQueryRequest) -> ProviderStatus:
        result = await self.query(request)
        if not result.evidence:
            raise VeklProviderError("vekl_canary_returned_no_evidence")
        await self.evidence.certify(
            KnowledgeProvider.VEKL,
            ProviderState.READY,
            evidence_pointer=result.evidence_pointer,
            details={"mission_id": request.mission_id, "query_id": result.query_id, "contains_secrets": False},
        )
        return await self.status()