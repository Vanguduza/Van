from __future__ import annotations

import pytest

from van_gateway.artifacts.models import ArtifactKind, ArtifactSensitivity
from van_gateway.artifacts.service import ArtifactService, ArtifactServiceError
from van_gateway.storage.db import Store


@pytest.mark.asyncio
async def test_artifact_projection_is_digest_bound_and_queryable(tmp_path):
    store=Store(str(tmp_path/"van.sqlite3"))
    await store.migrate()
    service=ArtifactService(store)
    digest="a"*64
    artifact=await service.create(
        kind=ArtifactKind.REPORT,title="Result",
        canonical_source_type="mission.outcome",canonical_source_id="m1",
        canonical_source_digest=digest,mission_id="m1",
        evidence_refs=["ev:1"],
    )
    assert artifact.canonical_source_digest==digest
    assert (await service.get(artifact.artifact_id))==artifact
    assert [x.artifact_id for x in await service.list(mission_id="m1")]==[artifact.artifact_id]


@pytest.mark.asyncio
async def test_secret_ref_artifact_cannot_expose_content(tmp_path):
    store=Store(str(tmp_path/"van.sqlite3"))
    await store.migrate()
    service=ArtifactService(store)
    with pytest.raises(ArtifactServiceError,match="secret_ref_only_cannot_expose_content"):
        await service.create(
            kind=ArtifactKind.FILE,title="Secret",
            canonical_source_type="secret",canonical_source_id="s1",
            canonical_source_digest="b"*64,content_ref="file:/secret",
            sensitivity=ArtifactSensitivity.SECRET_REF_ONLY,
        )
