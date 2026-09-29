from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


class JevJudgmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class JevAnnotation:
    module_id: str
    provider: str
    apply_effect: bool
    answers: dict[str, Any]
    result_fingerprint: str | None
    fallback_reason: str | None

    @property
    def available(self) -> bool:
        return self.provider == "jev"


class JevVanAdvisor:
    """Optional VAN consumer of the shared DIAL Jev judgment service.

    This class carries the consumer-scoped service credential, never the TypeSafe
    provider credential and never the Jev admin/control credential. It may ask for
    registered VAN judgments and return evidence. It cannot transition a module,
    change the global switch, execute a VAN action, or touch VATI execution.

    The owning deterministic subsystem decides whether an annotation is usable.
    In SHADOW the service returns apply_effect=false and callers preserve their
    pre-Jev behaviour exactly.
    """

    ATTENTION_MODULE = "van.attention.fields.v1"
    CRITIC_MODULE = "van.reasoning.critic.v1"

    def __init__(
        self,
        *,
        base_url: str,
        token_file: str,
        enabled: bool,
        timeout_seconds: float = 1.2,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token_file = token_file
        self._enabled = enabled
        self._timeout = timeout_seconds

    @property
    def configured(self) -> bool:
        return self._enabled and bool(self._base_url) and bool(self._token_file)

    def _token(self) -> str:
        if not self._token_file:
            raise JevJudgmentError("jev_consumer_token_file_unconfigured")
        token = Path(self._token_file).read_text(encoding="utf-8").strip()
        if not token:
            raise JevJudgmentError("jev_consumer_token_empty")
        return token

    async def _batch(self, module_id: str, state: dict[str, Any]) -> JevAnnotation | None:
        if not self.configured:
            return None
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/v1/judgments/batch",
                    json={
                        "project_id": "van",
                        "module_ids": [module_id],
                        "state": state,
                        "data_class": "INTERNAL_SANITIZED",
                        "purpose": "production",
                    },
                    headers={"X-Dial-Jev-Token": self._token()},
                )
        except (httpx.HTTPError, OSError) as exc:
            raise JevJudgmentError("jev_consumer_unavailable") from exc
        if response.status_code >= 400:
            raise JevJudgmentError(f"jev_consumer_http_{response.status_code}")
        body = response.json()
        if not isinstance(body, dict):
            raise JevJudgmentError("jev_consumer_invalid_payload")
        rows = body.get("results")
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
            raise JevJudgmentError("jev_consumer_invalid_batch")
        row = rows[0]
        return JevAnnotation(
            module_id=str(row.get("module_id") or module_id),
            provider=str(row.get("provider") or "fallback"),
            apply_effect=row.get("apply_effect") is True,
            answers=dict(row.get("answers") or {}),
            result_fingerprint=(
                str(row["result_fingerprint"]) if row.get("result_fingerprint") else None
            ),
            fallback_reason=(
                str(row["fallback_reason"]) if row.get("fallback_reason") else None
            ),
        )

    async def attention_fields(self, state: dict[str, Any]) -> JevAnnotation | None:
        return await self._batch(self.ATTENTION_MODULE, state)

    async def critic(self, state: dict[str, Any]) -> JevAnnotation | None:
        return await self._batch(self.CRITIC_MODULE, state)


def score01(answer: Any) -> float | None:
    """Map Jev's registered four-level Score primitive onto VAN's [0,1] field scale."""
    if not isinstance(answer, dict):
        return None
    raw = answer.get("score")
    if not isinstance(raw, (int, float)):
        return None
    return max(0.0, min(1.0, float(raw) / 3.0))


def noul_probability(answer: Any) -> float | None:
    if not isinstance(answer, dict):
        return None
    raw = answer.get("noul")
    if not isinstance(raw, (int, float)):
        return None
    return max(0.0, min(1.0, float(raw)))


__all__ = [
    "JevAnnotation",
    "JevJudgmentError",
    "JevVanAdvisor",
    "noul_probability",
    "score01",
]
